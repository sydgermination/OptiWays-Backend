"""
csa_algorithm.py
Connection Scan Algorithm (CSA) for OptiWays
Paper: https://i11www.iti.kit.edu/extra/publications/dpsw-isftr-13.pdf

The CSA works by scanning pre-sorted connections and tracking the
earliest arrival time at each stop.
"""

import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from osm_loader import Connection, Stop, find_nearest_stops, haversine, calculate_fare

INF = float("inf")


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE FILTERS
# ─────────────────────────────────────────────────────────────────────────────

def apply_profile_filter(conn: Connection, filters: dict) -> bool:
    """
    Returns True if this connection is allowed under the given profile.
    Returns False to skip/exclude this connection.
    """
    # Night shift: require 24hr service after 2AM
    if filters.get("require_24hr"):
        dep_hour = conn.dep_time // 3600
        if dep_hour >= 2 and not conn.is_24hr and conn.mode != "WALK":
            return False

    # Night shift: require lit paths for walking
    if filters.get("require_lit") and conn.mode == "WALK":
        if not conn.is_lit:
            return False

    # Accessible: no non-accessible connections
    if filters.get("no_stairs") or filters.get("accessible_stations_only"):
        if not conn.is_accessible:
            return False

    # Accessible: max walk distance shorter
    if filters.get("max_walk_km") and conn.mode == "WALK":
        if conn.distance_m > filters["max_walk_km"] * 1000:
            return False

    return True


def apply_fare_discount(fare: float, mode: str, filters: dict) -> Tuple[float, float]:
    """Returns (discounted_fare, discount_amount)."""
    discount_rate = 0.0

    if filters.get("student_discount") and mode != "WALK" and mode != "P2P":
        discount_rate = filters["student_discount"]  # 0.20
    elif filters.get("pwd_discount") and mode != "WALK":
        discount_rate = filters.get("pwd_discount", 0.20)

    discount = fare * discount_rate
    return fare - discount, discount


# ─────────────────────────────────────────────────────────────────────────────
# VIRTUAL STOP IDs for origin and destination
# ─────────────────────────────────────────────────────────────────────────────

ORIGIN_ID = "__ORIGIN__"
DEST_ID = "__DESTINATION__"


# ─────────────────────────────────────────────────────────────────────────────
# CORE CSA
# ─────────────────────────────────────────────────────────────────────────────

def run_csa(
    connections: List[Connection],
    origin_stops: List[Stop],
    dest_stops: List[Stop],
    departure_time_sec: int,
    filters: dict,
    max_walk_to_stop_m: float = 500
) -> Optional[dict]:
    """
    Run the Connection Scan Algorithm.

    Args:
        connections: All connections sorted by departure time
        origin_stops: Nearest stops to the user's origin
        dest_stops: Nearest stops to the user's destination
        departure_time_sec: Departure time in seconds since midnight
        filters: Profile-specific routing constraints
        max_walk_to_stop_m: Max walk distance to first/last stop

    Returns:
        Route dict with legs, fare, duration — or None if no route found
    """

    # Set global stops dict for name lookups during reconstruction
    global _STOPS_DICT
    _STOPS_DICT = stops_dict or {}

    # T[stop_id] = earliest known arrival time at that stop
    T: Dict[str, float] = {}

    # S[stop_id] = connection that got us to that stop (for reconstruction)
    S: Dict[str, Optional[Connection]] = {}

    # Initialize origin stops with walking time from actual origin
    for stop in origin_stops:
        walk_time = int((stop._walk_dist_m / 1000) / 5 * 3600)  # 5 km/h walk
        arrive_at_stop = departure_time_sec + walk_time
        T[stop.id] = arrive_at_stop
        S[stop.id] = None  # no connection needed — we walked here

    # Set of destination stop IDs for early exit
    dest_stop_ids = {s.id for s in dest_stops}

    # Find the binary search start index (first connection >= departure_time)
    start_idx = _binary_search_start(connections, departure_time_sec)

    # ── MAIN CSA SCAN LOOP ──────────────────────────────────────────────────
    for conn in connections[start_idx:]:

        # Early exit: if earliest possible departure is after best arrival at dest
        best_dest_arrival = min(
            (T[sid] for sid in dest_stop_ids if sid in T), default=INF
        )
        if conn.dep_time > best_dest_arrival:
            break

        # Can we board this connection?
        from_id = conn.from_stop
        if from_id not in T:
            continue  # we haven't reached this stop yet

        if T[from_id] > conn.dep_time:
            continue  # we arrive too late to board

        # Apply profile filter
        if not apply_profile_filter(conn, filters):
            continue

        # Is this arrival better than what we know?
        to_id = conn.to_stop
        if to_id not in T or conn.arr_time < T[to_id]:
            T[to_id] = conn.arr_time
            S[to_id] = conn

    # ── FIND BEST DESTINATION STOP ─────────────────────────────────────────
    best_dest_stop = None
    best_arrival = INF
    for stop in dest_stops:
        if stop.id in T and T[stop.id] < best_arrival:
            best_arrival = T[stop.id]
            best_dest_stop = stop

    if best_dest_stop is None:
        return None  # No route found

    # ── RECONSTRUCT JOURNEY ────────────────────────────────────────────────
    return reconstruct_journey(
        S=S,
        T=T,
        origin_stops=origin_stops,
        dest_stop=best_dest_stop,
        departure_time_sec=departure_time_sec,
        filters=filters,
        stops_dict=stops_dict or {}
    )


def _binary_search_start(connections: List[Connection], dep_time: int) -> int:
    """Find the first connection index with dep_time >= dep_time."""
    lo, hi = 0, len(connections)
    while lo < hi:
        mid = (lo + hi) // 2
        if connections[mid].dep_time < dep_time:
            lo = mid + 1
        else:
            hi = mid
    return lo


# ─────────────────────────────────────────────────────────────────────────────
# JOURNEY RECONSTRUCTION
# ─────────────────────────────────────────────────────────────────────────────

def reconstruct_journey(
    S: dict,
    T: dict,
    origin_stops: List[Stop],
    dest_stop: Stop,
    departure_time_sec: int,
    filters: dict
) -> dict:
    """Walk backwards through S to build the step-by-step leg list."""
    legs_raw = []
    current_id = dest_stop.id

    # Find which origin stop started our journey
    origin_stop_ids = {s.id for s in origin_stops}
    visited = set()

    while current_id not in origin_stop_ids:
        if current_id in visited:
            break  # cycle guard
        visited.add(current_id)

        conn = S.get(current_id)
        if conn is None:
            break

        legs_raw.append(conn)
        current_id = conn.from_stop

    legs_raw.reverse()

    if not legs_raw:
        return None

    # ── BUILD FORMATTED LEGS ───────────────────────────────────────────────
    legs = []
    total_fare = 0.0
    total_discount = 0.0
    step = 1

    # Add initial walk to first stop if needed
    first_conn = legs_raw[0]
    origin_stop = next((s for s in origin_stops if s.id == first_conn.from_stop), None)
    if origin_stop and hasattr(origin_stop, "_walk_dist_m") and origin_stop._walk_dist_m > 10:
        walk_dist = origin_stop._walk_dist_m
        walk_sec = int((walk_dist / 1000) / 5 * 3600)
        legs.append({
            "step_number": step,
            "instruction": f"Walk to {origin_stop.name}",
            "mode": "WALK",
            "duration_min": max(1, walk_sec // 60),
            "fare": 0.0,
            "from_stop": "Your location",
            "to_stop": origin_stop.name,
            "distance_m": walk_dist,
            "is_accessible": True,
            "is_lit": True,
            "is_24hr": True,
            "from_lat": 0.0, "from_lng": 0.0,
            "to_lat": origin_stop.lat, "to_lng": origin_stop.lng
        })
        step += 1

    # Merge consecutive connections of the same mode/route into one leg
    merged = _merge_connections(legs_raw)

    for conn_group in merged:
        first = conn_group[0]
        last = conn_group[-1]
        mode = first.mode
        distance_m = sum(c.distance_m for c in conn_group)
        base_fare = sum(c.fare for c in conn_group)
        final_fare, discount = apply_fare_discount(base_fare, mode, filters)
        duration_min = max(1, (last.arr_time - first.dep_time) // 60)

        total_fare += final_fare
        total_discount += discount

        instruction = _build_instruction(mode, first, last)

        legs.append({
            "step_number": step,
            "instruction": instruction,
            "mode": mode,
            "duration_min": duration_min,
            "fare": round(final_fare, 2),
            "from_stop": _stop_name_from_conn(first, "from"),
            "to_stop": _stop_name_from_conn(last, "to"),
            "distance_m": round(distance_m),
            "is_accessible": all(c.is_accessible for c in conn_group),
            "is_lit": all(c.is_lit for c in conn_group),
            "is_24hr": all(c.is_24hr for c in conn_group),
            "from_lat": first.from_lat,
            "from_lng": first.from_lng,
            "to_lat": last.to_lat,
            "to_lng": last.to_lng
        })
        step += 1

    # Add final walk to destination
    if hasattr(dest_stop, "_walk_dist_m") and dest_stop._walk_dist_m > 10:
        walk_dist = dest_stop._walk_dist_m
        walk_sec = int((walk_dist / 1000) / 5 * 3600)
        legs.append({
            "step_number": step,
            "instruction": "Walk to your destination",
            "mode": "WALK",
            "duration_min": max(1, walk_sec // 60),
            "fare": 0.0,
            "from_stop": dest_stop.name,
            "to_stop": "Your destination",
            "distance_m": walk_dist,
            "is_accessible": True,
            "is_lit": True,
            "is_24hr": True,
            "from_lat": dest_stop.lat, "from_lng": dest_stop.lng,
            "to_lat": 0.0, "to_lng": 0.0
        })

    # ── BUILD POLYLINE ─────────────────────────────────────────────────────
    polyline = []
    for leg in legs:
        if leg["from_lat"] != 0.0:
            polyline.append({"lat": leg["from_lat"], "lng": leg["from_lng"]})
    if legs:
        last_leg = legs[-1]
        if last_leg["to_lat"] != 0.0:
            polyline.append({"lat": last_leg["to_lat"], "lng": last_leg["to_lng"]})

    total_duration = sum(leg["duration_min"] for leg in legs)
    transfers = sum(1 for i in range(1, len(legs))
                    if legs[i]["mode"] != legs[i-1]["mode"] and legs[i]["mode"] != "WALK")

    # ── BUILD TAGS ─────────────────────────────────────────────────────────
    tags = []
    if all(leg["is_accessible"] for leg in legs):
        tags.append("♿ Fully Accessible")
    if all(leg.get("is_24hr", False) for leg in legs if leg["mode"] != "WALK"):
        tags.append("🌙 24-hr Service")
    if total_discount > 0:
        tags.append(f"🎓 Discount Applied")
    if transfers == 0:
        tags.append("✅ Direct Route")

    return {
        "route_id": f"csa-{departure_time_sec}",
        "total_duration": total_duration,
        "total_fare": round(total_fare, 2),
        "original_fare": round(total_fare + total_discount, 2),
        "discount_applied": round(total_discount, 2),
        "currency": "PHP",
        "transfers": transfers,
        "tags": tags,
        "localized_tips": [],
        "polyline_points": polyline,
        "legs": legs
    }


def _merge_connections(connections: List[Connection]) -> List[List[Connection]]:
    """Merge consecutive connections of the same route into groups."""
    if not connections:
        return []
    groups = [[connections[0]]]
    for conn in connections[1:]:
        last = groups[-1][-1]
        # Merge if same route and mode
        if conn.route_id == last.route_id and conn.mode == last.mode:
            groups[-1].append(conn)
        else:
            groups.append([conn])
    return groups


def _build_instruction(mode: str, first: Connection, last: Connection) -> str:
    from_name = _stop_name_from_conn(first, "from")
    to_name = _stop_name_from_conn(last, "to")

    instructions = {
        "WALK":       f"Walk from {from_name} to {to_name}",
        "JEEPNEY":    f"Board Jeepney at {from_name} → alight at {to_name}",
        "BUS":        f"Board Bus at {from_name} → alight at {to_name}",
        "UV_EXPRESS": f"Board UV Express at {from_name} → alight at {to_name}",
        "MRT":        f"Ride MRT from {from_name} → {to_name}",
        "LRT":        f"Ride LRT from {from_name} → {to_name}",
        "P2P":        f"Board P2P Bus at {from_name} → alight at {to_name}",
        "TRICYCLE":   f"Ride Tricycle from {from_name} to {to_name}"
    }
    return instructions.get(mode, f"Travel from {from_name} to {to_name}")


# Global stops dict for name lookup — set by run_csa
_STOPS_DICT: dict = {}

def _stop_name_from_conn(conn: Connection, which: str) -> str:
    stop_id = conn.from_stop if which == "from" else conn.to_stop
    stop = _STOPS_DICT.get(stop_id)
    if stop and stop.name and not stop.name.startswith("Stop_"):
        return stop.name
    return f"Stop {stop_id[:8]}"
