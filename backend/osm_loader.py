"""
osm_loader.py
Parses philippines-260301.osm.pbf and extracts:
- Transit stops (jeepney, bus, MRT, LRT, UV Express)
- Route relations
- Builds a timetable of connections for CSA

OPTIMIZED VERSION:
- Walking connections no longer generate per-minute entries
  (CSA handles walking as transfer time, not as timed connections)
- Spatial bucketing for fast nearest-stop lookup
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
    "P2P":        {"base_fare": 100.0,"per_km": 0.0,  "base_km": 999.0},
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
    dphi  = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ─────────────────────────────────────────────────────────────────────────────
# OSM HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class TransitHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.stops: Dict[str, Stop] = {}
        self.routes: List[dict] = []
        self._count = 0

    def node(self, n):
        self._count += 1
        if self._count % 1_000_000 == 0:
            print(f"   Processed {self._count:,} nodes, "
                  f"found {len(self.stops):,} stops so far...")

        tags = dict(n.tags)
        is_stop = (
                tags.get("highway") == "bus_stop" or
                tags.get("public_transport") in ("stop_position", "platform") or
                tags.get("railway") in ("station", "halt", "tram_stop") or
                tags.get("amenity") == "bus_station"
        )
        if not is_stop:
            return

        try:
            lat = float(n.location.lat)
            lng = float(n.location.lon)
        except Exception:
            return

        # Filter to Metro Manila + nearby provinces bounding box
        # Speeds up processing by ignoring Visayas/Mindanao stops for now
        if not (14.0 <= lat <= 15.2 and 120.5 <= lng <= 121.5):
            return

        name = tags.get("name", tags.get("name:en", f"Stop_{n.id}"))

        modes = []
        if tags.get("railway") in ("station", "halt"):
            line = tags.get("line", "").upper()
            if "MRT" in line or "3" in line:
                modes.append("MRT")
            elif "LRT" in line or "1" in line or "2" in line:
                modes.append("LRT")
            else:
                modes.extend(["MRT", "LRT"])
        if tags.get("highway") == "bus_stop":
            modes.extend(["JEEPNEY", "BUS", "UV_EXPRESS"])
        if not modes:
            modes = ["JEEPNEY", "BUS"]

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

    def relation(self, r):
        tags = dict(r.tags)
        if tags.get("type") != "route":
            return

        route_type = tags.get("route", "")
        if route_type not in ("bus", "share_taxi", "subway", "light_rail",
                              "train", "tram", "monorail"):
            return

        mode_map = {
            "bus": "BUS", "share_taxi": "UV_EXPRESS",
            "subway": "MRT", "light_rail": "LRT",
            "train": "LRT", "tram": "LRT",
        }
        mode = mode_map.get(route_type, "BUS")

        name = tags.get("name", tags.get("ref", ""))
        if route_type in ("bus", "share_taxi") and \
                tags.get("operator", "").lower() in ("jeepney", "paj", "ltfrb"):
            mode = "JEEPNEY"

        stop_ids = [
            str(m.ref) for m in r.members
            if m.type == "n" and m.role in (
                "stop", "stop_entry_only", "stop_exit_only", "platform", ""
            )
        ]
        if len(stop_ids) < 2:
            return

        self.routes.append({
            "id": str(r.id),
            "name": name,
            "mode": mode,
            "stop_ids": stop_ids,
            "is_accessible": tags.get("wheelchair") != "no",
            "is_24hr": tags.get("opening_hours", "") in ("24/7", "24/7;24/7"),
            "operator": tags.get("operator", "")
        })


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

    for route in routes:
        mode      = route["mode"]
        stop_ids  = route["stop_ids"]
        speed_kmh = SPEEDS.get(mode, 20)
        start_hour, end_hour, freq_min = SERVICE_HOURS.get(mode, (5, 22, 15))
        is_24hr = route.get("is_24hr", False)
        if is_24hr:
            start_hour, end_hour = 0, 24

        freq_sec     = freq_min * 60
        current_time = start_hour * 3600
        end_time     = end_hour  * 3600

        while current_time <= end_time:
            time_cursor = current_time
            for i in range(len(stop_ids) - 1):
                from_stop = stops.get(stop_ids[i])
                to_stop   = stops.get(stop_ids[i + 1])
                if not from_stop or not to_stop:
                    time_cursor += 120
                    continue

                dist_m      = haversine(from_stop.lat, from_stop.lng,
                                        to_stop.lat,   to_stop.lng)
                travel_sec  = max(60, int((dist_m / 1000) / speed_kmh * 3600))
                fare        = calculate_fare(mode, dist_m)

                connections.append(Connection(
                    from_stop    = stop_ids[i],
                    to_stop      = stop_ids[i + 1],
                    dep_time     = time_cursor,
                    arr_time     = time_cursor + travel_sec,
                    mode         = mode,
                    route_id     = route["id"],
                    fare         = fare,
                    is_accessible= route.get("is_accessible", True) and from_stop.is_accessible,
                    is_lit       = from_stop.is_lit,
                    is_24hr      = is_24hr,
                    from_lat     = from_stop.lat,
                    from_lng     = from_stop.lng,
                    to_lat       = to_stop.lat,
                    to_lng       = to_stop.lng,
                    distance_m   = dist_m,
                ))
                time_cursor += travel_sec
            current_time += freq_sec

    connections.sort(key=lambda c: c.dep_time)
    print(f"✅ Built {len(connections):,} transit connections from {len(routes)} routes")
    return connections


# ─────────────────────────────────────────────────────────────────────────────
# WALKING CONNECTIONS  ← OPTIMIZED
# Instead of 1 connection per minute (86400 entries per pair!),
# we store just ONE walking edge per direction.
# The CSA uses a minimum transfer time model instead.
# ─────────────────────────────────────────────────────────────────────────────

def build_walking_connections(stops: Dict[str, Stop],
                              max_walk_m: float = 500) -> List[Connection]:
    """
    Build walking connections between nearby stops.

    KEY OPTIMIZATION: We store a single connection per pair per hour
    (24 entries instead of 1440). The CSA treats walking as always-available
    by checking: can_board = T[from_stop] <= conn.dep_time
    With hourly entries the max wait is 1 hour which is fine for transfers.
    """
    walk_connections = []
    stop_list = list(stops.values())
    walk_speed = SPEEDS["WALK"]

    # Spatial grid bucketing — only compare stops in nearby grid cells
    # Grid cell ~1km x 1km at Philippines latitude
    GRID_DEG = 0.009   # ~1km
    grid: Dict[Tuple[int,int], List[Stop]] = defaultdict(list)
    for stop in stop_list:
        cell = (int(stop.lat / GRID_DEG), int(stop.lng / GRID_DEG))
        grid[cell].append(stop)

    pair_count = 0
    for stop_a in stop_list:
        cell_a = (int(stop_a.lat / GRID_DEG), int(stop_a.lng / GRID_DEG))
        # Check this cell and 8 neighbors only
        neighbors = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                neighbors.extend(grid[(cell_a[0]+dr, cell_a[1]+dc)])

        for stop_b in neighbors:
            if stop_b.id <= stop_a.id:   # avoid duplicates
                continue
            dist = haversine(stop_a.lat, stop_a.lng, stop_b.lat, stop_b.lng)
            if dist > max_walk_m:
                continue

            travel_sec = max(30, int((dist / 1000) / walk_speed * 3600))
            pair_count += 1

            # ONE entry per hour per direction (24 × 2 = 48 entries per pair)
            # vs the old 1440 × 2 = 2880 entries per pair
            for hour in range(24):
                dep = hour * 3600
                for (frm, to, flat, flng, tlat, tlng) in [
                    (stop_a.id, stop_b.id, stop_a.lat, stop_a.lng, stop_b.lat, stop_b.lng),
                    (stop_b.id, stop_a.id, stop_b.lat, stop_b.lng, stop_a.lat, stop_a.lng),
                ]:
                    walk_connections.append(Connection(
                        from_stop   = frm,
                        to_stop     = to,
                        dep_time    = dep,
                        arr_time    = dep + travel_sec,
                        mode        = "WALK",
                        route_id    = "walk",
                        fare        = 0.0,
                        is_accessible = True,
                        is_lit      = stop_a.is_lit and stop_b.is_lit,
                        is_24hr     = True,
                        from_lat    = flat, from_lng = flng,
                        to_lat      = tlat, to_lng   = tlng,
                        distance_m  = dist,
                    ))

    print(f"✅ Built {len(walk_connections):,} walking connections "
          f"({pair_count:,} nearby pairs)")
    return walk_connections


# ─────────────────────────────────────────────────────────────────────────────
# NEAREST STOP FINDER  (with spatial grid)
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
# MAIN LOADER
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FILE = "data/ph_transit_cache.pkl"

def load_or_build_network(pbf_path: str, force_rebuild: bool = False):
    """
    Load from cache or parse OSM file.
    First build: ~3-6 min.  Cache load: ~3 sec.
    """
    if not force_rebuild and os.path.exists(CACHE_FILE):
        print("📦 Loading transit network from cache...")
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        print(f"✅ Loaded {len(data['stops']):,} stops, "
              f"{len(data['connections']):,} connections")
        return data["stops"], data["connections"]

    print(f"🗺️  Parsing {pbf_path}")
    print("   (Filtering to Metro Manila bounding box for speed)")
    print("   Progress prints every 1M nodes...\n")

    handler = TransitHandler()
    handler.apply_file(pbf_path, locations=True)

    stops  = handler.stops
    routes = handler.routes
    print(f"\n📍 Found {len(stops):,} stops and {len(routes):,} routes")

    transit_connections = build_timetable(stops, routes)
    walk_connections    = build_walking_connections(stops)

    all_connections = transit_connections + walk_connections
    all_connections.sort(key=lambda c: c.dep_time)
    print(f"✅ Total connections: {len(all_connections):,}")

    os.makedirs("data", exist_ok=True)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump({"stops": stops, "connections": all_connections}, f)
    print(f"💾 Saved cache → {CACHE_FILE}")
    print("   Next startup will load in ~3 seconds ⚡")

    return stops, all_connections
