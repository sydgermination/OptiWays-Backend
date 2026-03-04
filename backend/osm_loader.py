"""
osm_loader.py
Parses philippines-260301.osm.pbf and extracts:
- Transit stops (jeepney, bus, MRT, LRT, UV Express)
- Route relations
- Builds a timetable of connections for CSA

OPTIMIZED VERSION v2:
- Broader stop tag detection (captures Philippine OSM tagging patterns)
- Way-based stop support (MRT/LRT stations often mapped as polygons)
- Walking connections use hourly entries instead of per-minute (48 vs 2880 per pair)
- Spatial bucketing for fast nearest-stop lookup
- Route resolution diagnostics to catch missing stop refs
- Progress printing every 1M nodes
"""

import osmium
import math
import pickle
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

def download_osm_if_needed(pbf_path: str):
    """Download OSM file from URL if not present locally."""
    if os.path.exists(pbf_path):
        return
    url = os.environ.get("OSM_URL",
                         "https://download.geofabrik.de/asia/philippines-latest.osm.pbf")
    print(f"⬇️  Downloading OSM data from {url} ...")
    os.makedirs(os.path.dirname(pbf_path), exist_ok=True)
    import urllib.request
    urllib.request.urlretrieve(url, pbf_path)
    print("✅ Download complete")


@dataclass
class Stop:
    id: str
    name: str
    lat: float
    lng: float
    modes: List[str] = field(default_factory=list)
    is_accessible: bool = True
    is_lit: bool = True
    is_24hr: bool = False
    has_elevator: bool = False
    # Runtime only — not stored in cache
    _walk_dist_m: float = field(default=0.0, compare=False, repr=False)


@dataclass
class Connection:
    """A single transit connection between two stops."""
    from_stop: str
    to_stop: str
    dep_time: int        # seconds since midnight
    arr_time: int        # seconds since midnight
    mode: str            # JEEPNEY, BUS, MRT, LRT, UV_EXPRESS, WALK
    route_id: str
    fare: float
    is_accessible: bool = True
    is_lit: bool = True
    is_24hr: bool = False
    from_lat: float = 0.0
    from_lng: float = 0.0
    to_lat: float = 0.0
    to_lng: float = 0.0
    distance_m: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# FARE TABLES (Philippine fare matrix 2025)
# ─────────────────────────────────────────────────────────────────────────────

FARE_TABLES = {
    "JEEPNEY":    {"base_fare": 13.0, "per_km": 1.80, "base_km": 4.0},
    "BUS":        {"base_fare": 15.0, "per_km": 2.20, "base_km": 5.0},
    "UV_EXPRESS": {"base_fare": 20.0, "per_km": 2.50, "base_km": 5.0},
    "MRT":        {"base_fare": 13.0, "per_km": 1.50, "base_km": 2.0},
    "LRT":        {"base_fare": 12.0, "per_km": 1.50, "base_km": 2.0},
    "WALK":       {"base_fare": 0.0,  "per_km": 0.0,  "base_km": 0.0},
    "P2P":        {"base_fare": 100.0, "per_km": 0.0, "base_km": 999.0},
}


def calculate_fare(mode: str, distance_m: float) -> float:
    table = FARE_TABLES.get(mode, FARE_TABLES["JEEPNEY"])
    distance_km = distance_m / 1000
    if distance_km <= table["base_km"]:
        return table["base_fare"]
    return table["base_fare"] + (distance_km - table["base_km"]) * table["per_km"]


# ─────────────────────────────────────────────────────────────────────────────
# HAVERSINE DISTANCE
# ─────────────────────────────────────────────────────────────────────────────

def haversine(lat1, lng1, lat2, lng2) -> float:
    """Returns distance in meters."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────────────────────────────────────
# METRO MANILA BOUNDING BOX
# ─────────────────────────────────────────────────────────────────────────────

BBOX_LAT_MIN, BBOX_LAT_MAX = 14.0, 15.2
BBOX_LNG_MIN, BBOX_LNG_MAX = 120.5, 121.5


def _in_bbox(lat: float, lng: float) -> bool:
    return BBOX_LAT_MIN <= lat <= BBOX_LAT_MAX and BBOX_LNG_MIN <= lng <= BBOX_LNG_MAX


# ─────────────────────────────────────────────────────────────────────────────
# OSM HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class TransitHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.stops: Dict[str, Stop] = {}
        self.routes: List[dict] = []
        # Way centroids keyed by way ID — resolved later via relations
        # Format: {way_id: {"name": str, "lat": float, "lng": float, "tags": dict}}
        self._way_centroids: Dict[str, dict] = {}

        self._count = 0
        self._in_bbox_count = 0
        self._sample_logged = 0  # log first 3 stop tag sets for debugging

    # ── Node pass ────────────────────────────────────────────────────────────

    def node(self, n):
        self._count += 1
        if self._count % 1_000_000 == 0:
            print(f"   Processed {self._count:,} nodes | "
                  f"{self._in_bbox_count:,} in bbox | "
                  f"{len(self.stops):,} stops found")

        tags = dict(n.tags)

        # ── Broadened stop detection ──────────────────────────────────────────
        # Philippine OSM data uses many tagging patterns; we capture all of them.
        is_stop = (
            tags.get("highway") in ("bus_stop", "platform") or
            tags.get("public_transport") in (
                "stop_position", "platform", "stop_area"
            ) or
            tags.get("railway") in (
                "station", "halt", "tram_stop", "subway_entrance"
            ) or
            tags.get("amenity") in ("bus_station", "ferry_terminal") or
            # Jeepney stops in PH OSM are often only tagged with route_ref
            tags.get("route_ref") is not None or
            # Stops tagged with operator + public_transport (common in PH)
            (tags.get("operator") is not None and
             tags.get("public_transport") is not None)
        )
        if not is_stop:
            return

        try:
            lat = float(n.location.lat)
            lng = float(n.location.lon)
        except Exception:
            return

        if not _in_bbox(lat, lng):
            return

        self._in_bbox_count += 1

        # Log sample stop tags to help debug tagging patterns
        if self._sample_logged < 3:
            print(f"   SAMPLE STOP TAGS [{self._sample_logged + 1}/3]: {dict(tags)}")
            self._sample_logged += 1

        name = tags.get("name", tags.get("name:en", tags.get("name:fil", f"Stop_{n.id}")))
        modes = _infer_modes(tags)

        self.stops[str(n.id)] = Stop(
            id=str(n.id),
            name=name,
            lat=lat,
            lng=lng,
            modes=modes,
            is_accessible=tags.get("wheelchair") != "no",
            is_lit=tags.get("lit") != "no",
            has_elevator=tags.get("elevator") == "yes",
        )

    # ── Way pass — capture MRT/LRT stations mapped as polygons ───────────────

    def way(self, w):
        tags = dict(w.tags)
        is_transit_way = (
            tags.get("public_transport") in ("platform", "stop_area", "station") or
            tags.get("railway") in ("station", "platform", "subway_entrance") or
            tags.get("amenity") == "bus_station"
        )
        if not is_transit_way:
            return

        # Compute centroid from node refs — osmium gives us locations
        # only if we passed locations=True to apply_file
        lats, lngs = [], []
        try:
            for node_ref in w.nodes:
                lats.append(node_ref.location.lat)
                lngs.append(node_ref.location.lon)
        except Exception:
            return

        if not lats:
            return

        lat = sum(lats) / len(lats)
        lng = sum(lngs) / len(lngs)

        if not _in_bbox(lat, lng):
            return

        name = tags.get("name", tags.get("name:en", tags.get("name:fil", f"Station_w{w.id}")))
        way_id = f"w{w.id}"

        self._way_centroids[way_id] = {
            "name": name,
            "lat": lat,
            "lng": lng,
            "tags": tags,
        }

    # ── Relation pass ─────────────────────────────────────────────────────────

    def relation(self, r):
        tags = dict(r.tags)
        if tags.get("type") != "route":
            return

        route_type = tags.get("route", "")
        if route_type not in ("bus", "share_taxi", "subway", "light_rail",
                               "train", "tram", "monorail", "jeepney"):
            return

        mode_map = {
            "bus": "BUS",
            "share_taxi": "UV_EXPRESS",
            "jeepney": "JEEPNEY",
            "subway": "MRT",
            "light_rail": "LRT",
            "train": "LRT",
            "tram": "LRT",
        }
        mode = mode_map.get(route_type, "BUS")

        name = tags.get("name", tags.get("ref", ""))
        operator = tags.get("operator", "").lower()
        if route_type in ("bus", "share_taxi") and operator in ("jeepney", "paj", "ltfrb"):
            mode = "JEEPNEY"

        # Collect node AND way member stop refs
        stop_ids = []
        for m in r.members:
            role = m.role
            if role not in ("stop", "stop_entry_only", "stop_exit_only", "platform", ""):
                continue
            if m.type == "n":
                stop_ids.append(str(m.ref))
            elif m.type == "w":
                stop_ids.append(f"w{m.ref}")

        if len(stop_ids) < 2:
            return

        self.routes.append({
            "id": str(r.id),
            "name": name,
            "mode": mode,
            "stop_ids": stop_ids,
            "is_accessible": tags.get("wheelchair") != "no",
            "is_24hr": tags.get("opening_hours", "") in ("24/7", "24/7;24/7"),
            "operator": operator,
        })


# ─────────────────────────────────────────────────────────────────────────────
# MODE INFERENCE
# ─────────────────────────────────────────────────────────────────────────────

def _infer_modes(tags: dict) -> List[str]:
    modes = []
    if tags.get("railway") in ("station", "halt", "subway_entrance"):
        line = tags.get("line", tags.get("network", "")).upper()
        if "MRT" in line or "3" in line:
            modes.append("MRT")
        elif "LRT" in line or "1" in line or "2" in line:
            modes.append("LRT")
        else:
            modes.extend(["MRT", "LRT"])
    if tags.get("highway") in ("bus_stop", "platform"):
        modes.extend(["JEEPNEY", "BUS", "UV_EXPRESS"])
    if tags.get("amenity") == "bus_station":
        modes.extend(["BUS", "UV_EXPRESS"])
    if not modes:
        modes = ["JEEPNEY", "BUS"]
    return list(dict.fromkeys(modes))  # dedupe while preserving order


# ─────────────────────────────────────────────────────────────────────────────
# SPEEDS & SERVICE HOURS
# ─────────────────────────────────────────────────────────────────────────────

SPEEDS = {
    "JEEPNEY": 20, "BUS": 25, "UV_EXPRESS": 35,
    "MRT": 45, "LRT": 40, "WALK": 5, "P2P": 60
}

# (start_hour, end_hour, frequency_minutes)
SERVICE_HOURS = {
    "JEEPNEY":    (5, 22, 10),
    "BUS":        (5, 23, 15),
    "UV_EXPRESS": (5, 23, 8),
    "MRT":        (5, 22, 5),
    "LRT":        (5, 22, 5),
    "P2P":        (5, 21, 30),
}


# ─────────────────────────────────────────────────────────────────────────────
# TIMETABLE BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_timetable(stops: Dict[str, Stop], routes: List[dict]) -> List[Connection]:
    connections = []

    # ── Diagnostic: count how many route stop refs can't be resolved ──────────
    missing_refs = sum(
        1 for route in routes
        for sid in route["stop_ids"]
        if sid not in stops
    )
    total_refs = sum(len(r["stop_ids"]) for r in routes)
    if missing_refs:
        pct = 100 * missing_refs / max(total_refs, 1)
        print(f"⚠️  {missing_refs:,} / {total_refs:,} stop refs in routes "
              f"not found in stops dict ({pct:.1f}% unresolved) — "
              f"these legs will be skipped")

    for route in routes:
        mode = route["mode"]
        stop_ids = route["stop_ids"]
        speed_kmh = SPEEDS.get(mode, 20)
        start_hour, end_hour, freq_min = SERVICE_HOURS.get(mode, (5, 22, 15))
        is_24hr = route.get("is_24hr", False)
        if is_24hr:
            start_hour, end_hour = 0, 24

        freq_sec = freq_min * 60
        current_time = start_hour * 3600
        end_time = end_hour * 3600

        while current_time <= end_time:
            time_cursor = current_time
            for i in range(len(stop_ids) - 1):
                from_stop = stops.get(stop_ids[i])
                to_stop = stops.get(stop_ids[i + 1])
                if not from_stop or not to_stop:
                    time_cursor += 120
                    continue

                dist_m = haversine(from_stop.lat, from_stop.lng,
                                   to_stop.lat, to_stop.lng)
                travel_sec = max(60, int((dist_m / 1000) / speed_kmh * 3600))
                fare = calculate_fare(mode, dist_m)

                connections.append(Connection(
                    from_stop=stop_ids[i],
                    to_stop=stop_ids[i + 1],
                    dep_time=time_cursor,
                    arr_time=time_cursor + travel_sec,
                    mode=mode,
                    route_id=route["id"],
                    fare=fare,
                    is_accessible=route.get("is_accessible", True) and from_stop.is_accessible,
                    is_lit=from_stop.is_lit,
                    is_24hr=is_24hr,
                    from_lat=from_stop.lat,
                    from_lng=from_stop.lng,
                    to_lat=to_stop.lat,
                    to_lng=to_stop.lng,
                    distance_m=dist_m,
                ))
                time_cursor += travel_sec
            current_time += freq_sec

    connections.sort(key=lambda c: c.dep_time)
    print(f"✅ Built {len(connections):,} transit connections from {len(routes)} routes")
    return connections


# ─────────────────────────────────────────────────────────────────────────────
# WALKING CONNECTIONS
# Hourly entries per pair: 48 entries vs the old 2880 per pair
# ─────────────────────────────────────────────────────────────────────────────

def build_walking_connections(stops: Dict[str, Stop],
                               max_walk_m: float = 500) -> List[Connection]:
    """
    Build walking connections between nearby stops.

    KEY OPTIMIZATION: ONE entry per hour per direction (24 × 2 = 48 entries per pair)
    instead of per-minute (1440 × 2 = 2880). The CSA treats walking as always-
    available by checking: can_board = T[from_stop] <= conn.dep_time.
    Max wait with hourly entries is 1 hour, acceptable for transfer modelling.
    """
    walk_connections = []
    stop_list = list(stops.values())
    walk_speed = SPEEDS["WALK"]

    # Spatial grid bucketing — ~1km cells at Philippines latitude
    GRID_DEG = 0.009
    grid: Dict[Tuple[int, int], List[Stop]] = defaultdict(list)
    for stop in stop_list:
        cell = (int(stop.lat / GRID_DEG), int(stop.lng / GRID_DEG))
        grid[cell].append(stop)

    pair_count = 0
    for stop_a in stop_list:
        cell_a = (int(stop_a.lat / GRID_DEG), int(stop_a.lng / GRID_DEG))
        neighbors = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                neighbors.extend(grid[(cell_a[0] + dr, cell_a[1] + dc)])

        for stop_b in neighbors:
            if stop_b.id <= stop_a.id:
                continue
            dist = haversine(stop_a.lat, stop_a.lng, stop_b.lat, stop_b.lng)
            if dist > max_walk_m:
                continue

            travel_sec = max(30, int((dist / 1000) / walk_speed * 3600))
            pair_count += 1

            for hour in range(24):
                dep = hour * 3600
                for (frm, to, flat, flng, tlat, tlng) in [
                    (stop_a.id, stop_b.id,
                     stop_a.lat, stop_a.lng, stop_b.lat, stop_b.lng),
                    (stop_b.id, stop_a.id,
                     stop_b.lat, stop_b.lng, stop_a.lat, stop_a.lng),
                ]:
                    walk_connections.append(Connection(
                        from_stop=frm,
                        to_stop=to,
                        dep_time=dep,
                        arr_time=dep + travel_sec,
                        mode="WALK",
                        route_id="walk",
                        fare=0.0,
                        is_accessible=True,
                        is_lit=stop_a.is_lit and stop_b.is_lit,
                        is_24hr=True,
                        from_lat=flat, from_lng=flng,
                        to_lat=tlat, to_lng=tlng,
                        distance_m=dist,
                    ))

    print(f"✅ Built {len(walk_connections):,} walking connections "
          f"({pair_count:,} nearby pairs)")
    return walk_connections


# ─────────────────────────────────────────────────────────────────────────────
# NEAREST STOP FINDER
# ─────────────────────────────────────────────────────────────────────────────

def find_nearest_stops(lat: float, lng: float,
                        stops: Dict[str, Stop],
                        n: int = 3,
                        max_dist_m: float = 1000) -> List[Stop]:
    distances = []
    for stop in stops.values():
        dist = haversine(lat, lng, stop.lat, stop.lng)
        if dist <= max_dist_m:
            distances.append((dist, stop))
    distances.sort(key=lambda x: x[0])
    return [s for _, s in distances[:n]]


# ─────────────────────────────────────────────────────────────────────────────
# WAY-CENTROID STOP MERGER
# Promote way_centroids to full Stop objects so route relations can resolve them
# ─────────────────────────────────────────────────────────────────────────────

def _merge_way_stops(stops: Dict[str, Stop],
                     way_centroids: Dict[str, dict]) -> int:
    """
    Adds way-based stops (e.g. MRT/LRT station polygons) into the stops dict.
    Returns the number of new stops added.
    """
    added = 0
    for way_id, data in way_centroids.items():
        if way_id in stops:
            continue
        if not _in_bbox(data["lat"], data["lng"]):
            continue
        tags = data["tags"]
        modes = _infer_modes(tags)
        stops[way_id] = Stop(
            id=way_id,
            name=data["name"],
            lat=data["lat"],
            lng=data["lng"],
            modes=modes,
            is_accessible=tags.get("wheelchair") != "no",
            is_lit=tags.get("lit") != "no",
            has_elevator=tags.get("elevator") == "yes",
        )
        added += 1
    return added


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOADER
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FILE = "data/ph_transit_cache.pkl"

# Semaphore flag — prevents concurrent rebuild attempts at runtime
_loading = False


def load_or_build_network(pbf_path: str, force_rebuild: bool = False):
    """
    Load from cache or parse OSM file.
    First build: ~3-6 min.  Cache load: ~3 sec.

    Pass force_rebuild=True during Docker image build to pre-bake the cache.
    """
    global _loading

    if not force_rebuild and os.path.exists(CACHE_FILE):
        print("📦 Loading transit network from cache...")
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        stops = data["stops"]
        connections = data["connections"]
        print(f"✅ Loaded {len(stops):,} stops, {len(connections):,} connections")
        return stops, connections

    if _loading:
        raise RuntimeError("Network build already in progress")
    _loading = True

    try:
        print(f"🗺️  Parsing {pbf_path}")
        print(f"   Bounding box: lat {BBOX_LAT_MIN}–{BBOX_LAT_MAX}, "
              f"lng {BBOX_LNG_MIN}–{BBOX_LNG_MAX} (Metro Manila + provinces)")
        print("   Progress prints every 1M nodes...\n")

        handler = TransitHandler()
        # locations=True required to resolve way node coordinates
        handler.apply_file(pbf_path, locations=True)

        stops = handler.stops
        routes = handler.routes

        # Merge way-based stations (MRT/LRT polygons) into stops
        way_added = _merge_way_stops(stops, handler._way_centroids)

        print(f"\n📍 Found {len(stops):,} stops "
              f"({way_added:,} from ways) and {len(routes):,} routes")

        transit_connections = build_timetable(stops, routes)
        walk_connections = build_walking_connections(stops)

        all_connections = transit_connections + walk_connections
        all_connections.sort(key=lambda c: c.dep_time)
        print(f"✅ Total connections: {len(all_connections):,}")

        os.makedirs("data", exist_ok=True)
        with open(CACHE_FILE, "wb") as f:
            pickle.dump({"stops": stops, "connections": all_connections}, f)
        print(f"💾 Saved cache → {CACHE_FILE}")
        print("   Next startup will load in ~3 seconds ⚡")

        return stops, all_connections

    finally:
        _loading = False
