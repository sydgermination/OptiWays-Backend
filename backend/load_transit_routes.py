"""
load_transit_routes.py
──────────────────────
Ingests data/transit_routes.json (produced by fetch_transit_routes.py)
into the OptiWays transit network.

Handles ALL modes:
  JEEPNEY, BUS, UV_EXPRESS, MRT, LRT, PNR

Called automatically by osm_loader.py after OSM PBF parse.
"""

import json
import math
import os
from typing import Dict, List, Optional

TRANSIT_ROUTES_FILE = "data/transit_routes.json"

# ── FARE TABLE ────────────────────────────────────────────────────────────────
FARE = {
    "JEEPNEY":    (13.0, 1.80, 4.0,  50.0),
    "BUS":        (15.0, 2.20, 5.0,  80.0),
    "UV_EXPRESS": (20.0, 2.50, 5.0,  80.0),
    "MRT":        (13.0, 1.00, 2.0,  28.0),
    "LRT":        (12.0, 1.00, 2.0,  30.0),
    "PNR":        (15.0, 1.00, 5.0, 100.0),
}

# ── SERVICE SCHEDULE ──────────────────────────────────────────────────────────
# (start_hr, end_hr, freq_min, speed_kmh, is_24hr)
SERVICE = {
    "JEEPNEY":    (5, 22, 10,  20, False),
    "BUS":        (5, 23, 15,  25, False),
    "UV_EXPRESS": (5, 23,  8,  35, False),
    "MRT":        (5, 22,  5,  45, False),
    "LRT":        (5, 22,  5,  40, False),
    "PNR":        (5, 21, 30,  60, False),
}


def _fare(mode: str, distance_m: float) -> float:
    base, per_km, base_km, max_f = FARE.get(mode, FARE["BUS"])
    km  = distance_m / 1000
    raw = base if km <= base_km else base + (km - base_km) * per_km
    return round(min(raw, max_f), 2)


def _haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def _closest_idx(geometry: list, lat: float, lng: float) -> int:
    best_i, best_d = 0, float("inf")
    for i, pt in enumerate(geometry):
        d = (pt["lat"]-lat)**2 + (pt["lng"]-lng)**2
        if d < best_d:
            best_d, best_i = d, i
    return best_i


def _slice_geometry(geometry: list, i_from: int, i_to: int) -> list:
    if i_from <= i_to:
        return geometry[i_from:i_to + 1]
    return list(reversed(geometry[i_to:i_from + 1]))


def inject_transit_routes(stops_dict: dict, Connection_class) -> list:
    """
    Load data/transit_routes.json and generate Connection objects for
    every stop-to-stop leg on every route, for every departure time.

    Args:
        stops_dict:        STOPS dict from osm_loader (id -> Stop)
        Connection_class:  Connection dataclass from osm_loader

    Returns:
        Sorted list of Connection objects.
    """
    if not os.path.exists(TRANSIT_ROUTES_FILE):
        print(f"⚠️  {TRANSIT_ROUTES_FILE} not found — skipping OSM route injection.")
        print(   "   Run: python3 fetch_transit_routes.py")
        return []

    with open(TRANSIT_ROUTES_FILE, encoding="utf-8") as f:
        data = json.load(f)

    routes = data.get("routes", [])
    by_mode = data.get("by_mode", {})
    print(f"📂 Loading transit_routes.json — {len(routes)} routes  {by_mode}")

    connections   = []
    new_stops     = 0
    skipped_routes = 0

    for route in routes:
        mode      = route.get("mode", "BUS")
        geometry  = route.get("geometry", [])
        osm_stops = route.get("stops", [])
        route_id  = route.get("relation_id", f"osm-{mode}")
        svc_info  = route.get("service", {})

        if len(osm_stops) < 2:
            skipped_routes += 1
            continue

        # Use service info from fetcher, fall back to defaults
        svc      = SERVICE.get(mode, SERVICE["BUS"])
        start_hr = svc_info.get("start_hr", svc[0])
        end_hr   = svc_info.get("end_hr",   svc[1])
        freq_min = svc_info.get("freq_min",  svc[2])
        speed    = svc_info.get("speed_kmh", svc[3])
        is_24hr  = svc[4]

        start_sec = start_hr * 3600
        end_sec   = end_hr   * 3600
        freq_sec  = freq_min * 60

        # ── Ensure stops exist in stops_dict ──────────────────────────────
        for s in osm_stops:
            sid = s["id"]
            if sid not in stops_dict:
                try:
                    from osm_loader import Stop
                    stops_dict[sid] = Stop(
                        id=sid,
                        name=s.get("name", f"{mode} Stop {sid}"),
                        lat=s["lat"],
                        lng=s["lng"],
                        modes=[mode],
                        is_accessible=True,
                        is_lit=True,
                        is_24hr=is_24hr,
                        has_elevator=(mode in ("MRT", "LRT"))
                    )
                    new_stops += 1
                except Exception:
                    pass  # Stop class unavailable — skip

        # ── Build per-leg geometry slices ─────────────────────────────────
        leg_geo: Dict[int, list] = {}
        if len(geometry) >= 2:
            for i in range(len(osm_stops) - 1):
                sf = osm_stops[i]
                st = osm_stops[i+1]
                i_f = _closest_idx(geometry, sf["lat"], sf["lng"])
                i_t = _closest_idx(geometry, st["lat"], st["lng"])
                sliced = _slice_geometry(geometry, i_f, i_t)
                if len(sliced) >= 2:
                    leg_geo[i] = sliced

        # ── Generate timetable ────────────────────────────────────────────
        current_time = start_sec
        while current_time <= end_sec:
            t = current_time
            for i in range(len(osm_stops) - 1):
                sf = osm_stops[i]
                st = osm_stops[i+1]

                dist_m     = _haversine(sf["lat"], sf["lng"], st["lat"], st["lng"])
                travel_sec = max(60, int((dist_m / 1000) / speed * 3600))
                fare       = _fare(mode, dist_m)

                connections.append(Connection_class(
                    from_stop    = sf["id"],
                    to_stop      = st["id"],
                    dep_time     = t,
                    arr_time     = t + travel_sec,
                    mode         = mode,
                    route_id     = route_id,
                    fare         = fare,
                    is_accessible= (mode in ("MRT", "LRT")),
                    is_lit       = True,
                    is_24hr      = is_24hr,
                    from_lat     = sf["lat"],
                    from_lng     = sf["lng"],
                    to_lat       = st["lat"],
                    to_lng       = st["lng"],
                    distance_m   = dist_m,
                    geometry     = leg_geo.get(i, [])
                ))
                t += travel_sec

            current_time += freq_sec

    connections.sort(key=lambda c: c.dep_time)

    mode_counts = {}
    for c in connections:
        mode_counts[c.mode] = mode_counts.get(c.mode, 0) + 1

    print(f"✅ Injected {len(connections):,} connections from OSM routes")
    print(f"   By mode: {mode_counts}")
    if new_stops:
        print(f"   New stops added to network: {new_stops}")
    if skipped_routes:
        print(f"   Routes skipped (no stops): {skipped_routes}")

    return connections