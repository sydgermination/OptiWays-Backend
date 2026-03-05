"""
osm_loader.py
Parses philippines-260301.osm.pbf and extracts:
- Transit stops (jeepney, bus, MRT, LRT, UV Express)
- Route relations
- Builds a timetable of connections for CSA
"""

import osmium
import json
import math
import pickle
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
from collections import defaultdict


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

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
    # OSM road geometry for this leg — list of {lat, lng} dicts
    # Populated from route way nodes so polyline follows actual roads
    geometry: List[dict] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# FARE TABLES (Philippine fare matrix as of 2025)
# ─────────────────────────────────────────────────────────────────────────────

FARE_TABLES = {
    "JEEPNEY": {
        "base_fare": 13.0,          # first 4km
        "per_km": 1.80,             # per km after 4km
        "base_km": 4.0
    },
    "BUS": {
        "base_fare": 15.0,
        "per_km": 2.20,
        "base_km": 5.0
    },
    "UV_EXPRESS": {
        "base_fare": 20.0,
        "per_km": 2.50,
        "base_km": 5.0
    },
    "MRT": {
        # Fixed fare by station distance
        "base_fare": 13.0,
        "per_km": 1.50,
        "base_km": 2.0
    },
    "LRT": {
        "base_fare": 12.0,
        "per_km": 1.50,
        "base_km": 2.0
    },
    "WALK": {
        "base_fare": 0.0,
        "per_km": 0.0,
        "base_km": 0.0
    },
    "P2P": {
        "base_fare": 100.0,
        "per_km": 0.0,
        "base_km": 999.0
    }
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
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


# ─────────────────────────────────────────────────────────────────────────────
# OSM HANDLER — Extracts nodes and route relations
# ─────────────────────────────────────────────────────────────────────────────

class TransitHandler(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.stops: Dict[str, Stop] = {}
        self.routes: List[dict] = []
        self._node_coords: Dict[int, Tuple[float, float]] = {}
        self._way_nodes: Dict[int, List[int]] = {}   # way_id -> ordered node ids
        self._bbox_ways: set = set()                 # way ids within bounding box

    def node(self, n):
        """Store all node coordinates and identify transit stops."""
        self._node_coords[n.id] = (float(n.location.lat), float(n.location.lon))

        tags = dict(n.tags)
        is_stop = (
            tags.get("highway") == "bus_stop" or
            tags.get("public_transport") in ("stop_position", "platform") or
            tags.get("railway") in ("station", "halt", "tram_stop") or
            tags.get("amenity") == "bus_station"
        )

        if not is_stop:
            return

        name = tags.get("name", tags.get("name:en", f"Stop_{n.id}"))
        lat = float(n.location.lat)
        lng = float(n.location.lon)

        # Determine modes served
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

        # Accessibility
        is_accessible = tags.get("wheelchair") != "no"
        has_elevator = tags.get("elevator") == "yes"
        is_lit = tags.get("lit") != "no"

        stop = Stop(
            id=str(n.id),
            name=name,
            lat=lat,
            lng=lng,
            modes=modes,
            is_accessible=is_accessible,
            is_lit=is_lit,
            has_elevator=has_elevator
        )
        self.stops[str(n.id)] = stop

    def way(self, w):
        """Store way node sequences for route geometry reconstruction."""
        # Only store ways that have at least one node in bbox — avoids memory bloat
        nodes = [n.ref for n in w.nodes]
        self._way_nodes[w.id] = nodes

    def relation(self, r):
        """Extract route relations (jeepney lines, bus routes, MRT/LRT)."""
        tags = dict(r.tags)
        if tags.get("type") != "route":
            return

        route_type = tags.get("route", "")
        if route_type not in ("bus", "share_taxi", "subway", "light_rail",
                              "train", "tram", "monorail"):
            return

        # Map OSM route type to our mode
        mode_map = {
            "bus": "BUS",
            "share_taxi": "UV_EXPRESS",
            "subway": "MRT",
            "light_rail": "LRT",
            "train": "LRT",
            "tram": "LRT",
        }
        mode = mode_map.get(route_type, "BUS")

        # Jeepney heuristic — short share_taxi or bus routes in PH
        name = tags.get("name", tags.get("ref", ""))
        if route_type in ("bus", "share_taxi") and tags.get("operator", "").lower() in (
            "jeepney", "paj", "ltfrb"
        ):
            mode = "JEEPNEY"

        stop_ids = []
        way_ids = []
        for member in r.members:
            if member.type == "n" and member.role in ("stop", "stop_entry_only",
                                                        "stop_exit_only", "platform", ""):
                stop_ids.append(str(member.ref))
            elif member.type == "w":
                way_ids.append(member.ref)

        if len(stop_ids) < 2:
            return

        route = {
            "id": str(r.id),
            "name": name,
            "mode": mode,
            "stop_ids": stop_ids,
            "way_ids": way_ids,   # ordered way members for geometry
            "is_accessible": tags.get("wheelchair") != "no",
            "is_24hr": tags.get("opening_hours", "") in ("24/7", "24/7;24/7"),
            "operator": tags.get("operator", "")
        }
        self.routes.append(route)


# ─────────────────────────────────────────────────────────────────────────────
# TIMETABLE BUILDER
# Generates synthetic departure times since PH has no public GTFS
# ─────────────────────────────────────────────────────────────────────────────

# Average speeds in km/h per mode
SPEEDS = {
    "JEEPNEY": 20,
    "BUS": 25,
    "UV_EXPRESS": 35,
    "MRT": 45,
    "LRT": 40,
    "WALK": 5,
    "P2P": 60
}

# Service hours per mode [start_hour, end_hour, frequency_minutes]
SERVICE_HOURS = {
    "JEEPNEY":    (5, 22, 10),
    "BUS":        (5, 23, 15),
    "UV_EXPRESS": (5, 23, 8),
    "MRT":        (5, 22, 5),
    "LRT":        (5, 22, 5),
    "P2P":        (5, 21, 30)
}

def build_leg_geometries(
    route: dict,
    stop_ids: List[str],
    stops: Dict[str, Stop],
    way_nodes: Dict[int, List[int]],
    node_coords: Dict[int, Tuple[float, float]] = None
) -> Dict[int, List[dict]]:
    """
    Build per-leg geometry lists from OSM way members.
    Returns a dict: leg_index -> list of {lat, lng} points.
    Falls back to straight line if way geometry not available.
    """
    if node_coords is None:
        node_coords = {}

    # Collect all node coords from the route's ways in order
    all_pts = []
    for way_id in route.get("way_ids", []):
        nodes = way_nodes.get(way_id, [])
        for nid in nodes:
            coord = node_coords.get(nid)
            if coord:
                all_pts.append({"lat": coord[0], "lng": coord[1]})

    # Remove consecutive duplicates
    deduped = []
    for pt in all_pts:
        if not deduped or (pt["lat"] != deduped[-1]["lat"] or pt["lng"] != deduped[-1]["lng"]):
            deduped.append(pt)

    leg_geometries: Dict[int, List[dict]] = {}

    if len(deduped) < 2:
        # No geometry available — caller will fall back to straight line
        return leg_geometries

    # Assign geometry slices to each leg by finding closest waypoints to stops
    def closest_idx(pts, lat, lng):
        best_i, best_d = 0, float("inf")
        for i, p in enumerate(pts):
            d = (p["lat"] - lat) ** 2 + (p["lng"] - lng) ** 2
            if d < best_d:
                best_d, best_i = d, i
        return best_i

    for i in range(len(stop_ids) - 1):
        from_stop = stops.get(stop_ids[i])
        to_stop = stops.get(stop_ids[i + 1])
        if not from_stop or not to_stop:
            continue

        i_from = closest_idx(deduped, from_stop.lat, from_stop.lng)
        i_to = closest_idx(deduped, to_stop.lat, to_stop.lng)

        if i_from <= i_to:
            slice_pts = deduped[i_from:i_to + 1]
        else:
            # Reverse route direction
            slice_pts = list(reversed(deduped[i_to:i_from + 1]))

        if len(slice_pts) >= 2:
            leg_geometries[i] = slice_pts

    return leg_geometries


def build_timetable(
    stops: Dict[str, Stop],
    routes: List[dict],
    handler_way_nodes: Dict[int, List[int]] = None,
    handler_node_coords: Dict[int, Tuple[float, float]] = None
) -> List[Connection]:
    """
    Build a list of connections from routes.
    Since PH has no public GTFS data, we generate synthetic timetables
    based on known service hours and frequencies.
    """
    connections = []

    for route in routes:
        mode = route["mode"]
        stop_ids = route["stop_ids"]
        speed_kmh = SPEEDS.get(mode, 20)
        service = SERVICE_HOURS.get(mode, (5, 22, 15))
        start_hour, end_hour, freq_min = service

        # Mark 24hr routes
        is_24hr = route.get("is_24hr", False)
        if is_24hr:
            start_hour, end_hour = 0, 24

        # Generate departures throughout the day
        current_time = start_hour * 3600  # seconds since midnight
        end_time = end_hour * 3600
        freq_sec = freq_min * 60

        # Build per-leg geometry from way nodes once (reused for all departures)
        leg_geometries = build_leg_geometries(
            route, stop_ids, stops,
            handler_way_nodes or {},
            handler_node_coords or {}
        )

        while current_time <= end_time:
            time_cursor = current_time

            # Build connections leg by leg along the route
            for i in range(len(stop_ids) - 1):
                from_id = stop_ids[i]
                to_id = stop_ids[i + 1]

                from_stop = stops.get(from_id)
                to_stop = stops.get(to_id)

                # Skip if stops not in our data
                if not from_stop or not to_stop:
                    # Estimate 2 min per missing segment
                    time_cursor += 120
                    continue

                distance_m = haversine(
                    from_stop.lat, from_stop.lng,
                    to_stop.lat, to_stop.lng
                )

                # Travel time in seconds
                travel_sec = max(60, int((distance_m / 1000) / speed_kmh * 3600))
                fare = calculate_fare(mode, distance_m)

                conn = Connection(
                    from_stop=from_id,
                    to_stop=to_id,
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
                    distance_m=distance_m,
                    geometry=leg_geometries.get(i, [])
                )
                connections.append(conn)
                time_cursor += travel_sec

            current_time += freq_sec

    # Sort by departure time — REQUIRED for CSA
    connections.sort(key=lambda c: c.dep_time)
    print(f"✅ Built {len(connections):,} connections from {len(routes)} routes")
    return connections


# ─────────────────────────────────────────────────────────────────────────────
# WALKING CONNECTIONS
# Add walking connections between nearby stops (within 500m)
# ─────────────────────────────────────────────────────────────────────────────

def build_walking_connections(stops: Dict[str, Stop], max_walk_m=500) -> List[Connection]:
    """Generate walking connections between stops within max_walk_m."""
    walk_connections = []
    stop_list = list(stops.values())
    walk_speed = SPEEDS["WALK"]  # km/h

    print(f"Building walking connections for {len(stop_list)} stops...")
    for i, stop_a in enumerate(stop_list):
        for stop_b in stop_list[i+1:]:
            dist = haversine(stop_a.lat, stop_a.lng, stop_b.lat, stop_b.lng)
            if dist > max_walk_m:
                continue

            travel_sec = max(30, int((dist / 1000) / walk_speed * 3600))

            # Walking is available all day at any time
            # We generate walks every 1 minute throughout the day
            for dep_time in range(0, 86400, 60):  # every minute
                walk_connections.append(Connection(
                    from_stop=stop_a.id,
                    to_stop=stop_b.id,
                    dep_time=dep_time,
                    arr_time=dep_time + travel_sec,
                    mode="WALK",
                    route_id="walk",
                    fare=0.0,
                    is_accessible=True,
                    is_lit=stop_a.is_lit and stop_b.is_lit,
                    is_24hr=True,
                    from_lat=stop_a.lat,
                    from_lng=stop_a.lng,
                    to_lat=stop_b.lat,
                    to_lng=stop_b.lng,
                    distance_m=dist
                ))
                # Also reverse direction
                walk_connections.append(Connection(
                    from_stop=stop_b.id,
                    to_stop=stop_a.id,
                    dep_time=dep_time,
                    arr_time=dep_time + travel_sec,
                    mode="WALK",
                    route_id="walk",
                    fare=0.0,
                    is_accessible=True,
                    is_lit=stop_a.is_lit and stop_b.is_lit,
                    is_24hr=True,
                    from_lat=stop_b.lat,
                    from_lng=stop_b.lng,
                    to_lat=stop_a.lat,
                    to_lng=stop_a.lng,
                    distance_m=dist
                ))

    print(f"✅ Built {len(walk_connections):,} walking connections")
    return walk_connections


# ─────────────────────────────────────────────────────────────────────────────
# NEAREST STOP FINDER
# ─────────────────────────────────────────────────────────────────────────────

def find_nearest_stops(
    lat: float,
    lng: float,
    stops: Dict[str, Stop],
    n: int = 3,
    max_dist_m: float = 1000
) -> List[Stop]:
    """Find the N nearest stops to a GPS coordinate."""
    distances = []
    for stop in stops.values():
        dist = haversine(lat, lng, stop.lat, stop.lng)
        if dist <= max_dist_m:
            distances.append((dist, stop))

    distances.sort(key=lambda x: x[0])
    return [s for _, s in distances[:n]]


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOADER — Call this once at startup, cache results
# ─────────────────────────────────────────────────────────────────────────────

CACHE_FILE = "data/ph_transit_cache.pkl"

def load_or_build_network(pbf_path: str, force_rebuild: bool = False):
    """
    Load transit network from cache or rebuild from OSM.
    First build takes 2-5 minutes. Subsequent loads take ~2 seconds.
    """
    if not force_rebuild and os.path.exists(CACHE_FILE):
        print("📦 Loading transit network from cache...")
        with open(CACHE_FILE, "rb") as f:
            data = pickle.load(f)
        print(f"✅ Loaded {len(data['stops']):,} stops, {len(data['connections']):,} connections")
        return data["stops"], data["connections"]

    print(f"🗺️  Parsing {pbf_path} — this takes 2-5 minutes on first run...")

    handler = TransitHandler()
    handler.apply_file(pbf_path, locations=True)

    stops = handler.stops
    routes = handler.routes
    print(f"📍 Found {len(stops):,} stops and {len(routes):,} routes")

    # Build timetable connections (pass way geometry for real route polylines)
    transit_connections = build_timetable(
        stops, routes,
        handler_way_nodes=handler._way_nodes,
        handler_node_coords=handler._node_coords
    )

    # Inject OSM-fetched routes (jeepney, bus, UV express, MRT, LRT, PNR)
    # from data/transit_routes.json — produced by fetch_transit_routes.py
    # These have real road-following geometry from OSM way members.
    try:
        from load_transit_routes import inject_transit_routes
        osm_connections = inject_transit_routes(stops, Connection)
        transit_connections = transit_connections + osm_connections
        print(f"✅ OSM route injection complete: {len(osm_connections):,} connections added")
    except Exception as e:
        print(f"⚠️  OSM route injection skipped: {e}")

    # Build walking connections
    walk_connections = build_walking_connections(stops)

    # Merge and sort
    all_connections = transit_connections + walk_connections
    all_connections.sort(key=lambda c: c.dep_time)

    print(f"✅ Total connections: {len(all_connections):,}")

    # Cache for fast startup
    os.makedirs("data", exist_ok=True)
    with open(CACHE_FILE, "wb") as f:
        pickle.dump({"stops": stops, "connections": all_connections}, f)
    print(f"💾 Cached to {CACHE_FILE}")

    return stops, all_connections
