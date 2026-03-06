"""
main.py — OptiWays CSA Backend
Deploy to Railway.app
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from enum import Enum
from typing import Optional
import uvicorn
import os
import asyncio
import json
import urllib.request
from datetime import datetime

# Safe imports — app still runs in mock mode if these fail
try:
    from osm_loader import load_or_build_network, find_nearest_stops, haversine
    from csa_algorithm import run_csa, apply_fare_discount
    IMPORTS_OK = True
except Exception as e:
    print(f"⚠️  Import error: {e} — running in mock mode")
    IMPORTS_OK = False

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL STATE
# ─────────────────────────────────────────────────────────────────────────────

STOPS = {}
CONNECTIONS = []
NETWORK_LOADED = False
OSM_PATH = os.environ.get("OSM_PATH", "data/philippines-latest.osm.pbf")
MAPS_API_KEY = os.environ.get("MAPS_API_KEY", "")


def load_network_thread():
    global STOPS, CONNECTIONS, NETWORK_LOADED
    if not IMPORTS_OK:
        print("⚠️  Imports failed — staying in mock mode")
        return
    try:
        print("🗺️  Loading Philippine transit network in background thread...")
        stops, connections = load_or_build_network(OSM_PATH)
        STOPS = stops
        CONNECTIONS = connections
        NETWORK_LOADED = True
        print(f"✅ Ready — {len(STOPS):,} stops, {len(CONNECTIONS):,} connections")
    except Exception as e:
        print(f"⚠️  Failed to load network: {e} — staying in mock mode")


@asynccontextmanager
async def lifespan(app: FastAPI):
    import threading
    t = threading.Thread(target=load_network_thread, daemon=True)
    t.start()
    yield


app = FastAPI(
    title="OptiWays CSA Backend",
    description="Connection Scan Algorithm routing for Philippine transit",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)


# ─────────────────────────────────────────────────────────────────────────────
# PROFILE DEFINITIONS
# ─────────────────────────────────────────────────────────────────────────────

class CommuterProfile(str, Enum):
    default     = "default"
    night_shift = "night_shift"
    student     = "student"
    accessible  = "accessible"


def build_filters(profile: CommuterProfile, is_student: bool, is_pwd: bool) -> dict:
    base = {"max_walk_km": 0.5}
    if profile == CommuterProfile.night_shift:
        return {**base, "require_24hr": True, "require_lit": True, "service_cutoff_time": "02:00"}
    elif profile == CommuterProfile.student:
        return {**base, "student_discount": 0.20, "optimize_for": "fare"}
    elif profile == CommuterProfile.accessible:
        return {**base, "no_stairs": True, "accessible_stations_only": True, "max_walk_km": 0.3}
    return base


def parse_departure_time(departure_time: Optional[str]) -> int:
    if not departure_time:
        now = datetime.now()
        return now.hour * 3600 + now.minute * 60 + now.second
    try:
        parts = departure_time.split(":")
        return int(parts[0]) * 3600 + int(parts[1]) * 60
    except Exception:
        now = datetime.now()
        return now.hour * 3600 + now.minute * 60 + now.second


def get_localized_tips(profile: CommuterProfile) -> list:
    tips = {
        CommuterProfile.default: [
            "Exact change appreciated by drivers 🪙",
            "Keep your belongings secure 🎒"
        ],
        CommuterProfile.night_shift: [
            "Stay near lit areas while waiting 💡",
            "UV Express runs 24/7 on EDSA 🌙"
        ],
        CommuterProfile.student: [
            "Show your valid school ID for discount 🎓",
            "Student fare applies on all PUVs"
        ],
        CommuterProfile.accessible: [
            "MRT/LRT have priority lanes ♿",
            "Ask staff for ramp assistance"
        ]
    }
    return tips.get(profile, tips[CommuterProfile.default])


# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DIRECTIONS POLYLINE
# ─────────────────────────────────────────────────────────────────────────────

def _decode_polyline(encoded: str) -> list:
    """Decode Google's encoded polyline format into lat/lng list."""
    points = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        result, shift = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1
        result, shift = 0, 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1F) << shift
            shift += 5
            if b < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1
        points.append({"lat": lat / 1e5, "lng": lng / 1e5})
    return points


def get_directions_polyline(from_lat: float, from_lng: float,
                             to_lat: float, to_lng: float,
                             mode: str = "driving") -> list:
    """
    Fetch road-following polyline from Google Directions API for a single leg.
    Uses 'driving' mode to follow roads (not transit — we use CSA for routing).
    Falls back to straight line if API unavailable.
    """
    # Straight line fallback
    def straight_line():
        return [
            {"lat": from_lat, "lng": from_lng},
            {"lat": to_lat,   "lng": to_lng}
        ]

    if not MAPS_API_KEY:
        return straight_line()

    # Use walking for short walk legs, driving for transit legs
    directions_mode = "walking" if mode == "WALK" else "driving"

    try:
        url = (
            f"https://maps.googleapis.com/maps/api/directions/json"
            f"?origin={from_lat},{from_lng}"
            f"&destination={to_lat},{to_lng}"
            f"&mode={directions_mode}"
            f"&key={MAPS_API_KEY}"
        )
        with urllib.request.urlopen(url, timeout=5) as resp:
            data = json.loads(resp.read())

        if data.get("status") != "OK":
            print(f"Directions API status: {data.get('status')} — using straight line")
            return straight_line()

        encoded = data["routes"][0]["overview_polyline"]["points"]
        return _decode_polyline(encoded)

    except Exception as e:
        print(f"Directions API error: {e} — using straight line")
        return straight_line()


def enrich_polyline_with_directions(result: dict) -> dict:
    """
    Build accurate commuter polyline per leg:

    1. Transit legs (JEEPNEY/BUS/MRT/LRT/UV_EXPRESS):
       → Use OSM route way geometry stored in leg["osm_geometry"]
         This is the actual road/path the jeepney/bus follows, not a car route.
       → Falls back to straight line if no OSM geometry available.

    2. WALK legs:
       → Google Directions API in walking mode (follows footpaths/sidewalks).
       → Falls back to straight line if API key missing.

    CSA routing decisions (stops, fares, transfers) are never changed here.
    """
    full_polyline = []

    for leg in result.get("legs", []):
        from_lat = leg.get("from_lat", 0.0)
        from_lng = leg.get("from_lng", 0.0)
        to_lat   = leg.get("to_lat",   0.0)
        to_lng   = leg.get("to_lng",   0.0)

        if from_lat == 0.0 or to_lat == 0.0:
            continue

        mode = leg.get("mode", "WALK")

        # ── TRANSIT: use OSM way geometry ──────────────────────────────────
        if mode != "WALK":
            osm_pts = leg.get("osm_geometry", [])
            if len(osm_pts) >= 2:
                full_polyline.extend(osm_pts)
                continue
            # No OSM geometry — fall through to straight line below

        # ── WALK: Google Directions walking mode ───────────────────────────
        elif MAPS_API_KEY:
            walk_pts = get_directions_polyline(from_lat, from_lng, to_lat, to_lng, "WALK")
            if walk_pts:
                full_polyline.extend(walk_pts)
                continue

        # ── FALLBACK: straight line ────────────────────────────────────────
        full_polyline.append({"lat": from_lat, "lng": from_lng})
        full_polyline.append({"lat": to_lat,   "lng": to_lng})

    if full_polyline:
        result["polyline_points"] = full_polyline

    return result


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "osm_data": NETWORK_LOADED,
        "network_loaded": NETWORK_LOADED,
        "stops": len(STOPS),
        "connections": len(CONNECTIONS),
        "directions_api": bool(MAPS_API_KEY)
    }


@app.get("/route")
def get_route(
    origin_lat:     float = Query(...),
    origin_lng:     float = Query(...),
    dest_lat:       float = Query(...),
    dest_lng:       float = Query(...),
    profile:        CommuterProfile = Query(CommuterProfile.default),
    departure_time: Optional[str] = Query(None),
    is_student:     bool = Query(False),
    is_pwd:         bool = Query(False)
):
    if not (4.5 <= origin_lat <= 21.5 and 116.0 <= origin_lng <= 127.0):
        raise HTTPException(400, "Origin must be within the Philippines")
    if not (4.5 <= dest_lat <= 21.5 and 116.0 <= dest_lng <= 127.0):
        raise HTTPException(400, "Destination must be within the Philippines")

    filters      = build_filters(profile, is_student, is_pwd)
    dep_time_sec = parse_departure_time(departure_time)

    # ── Real CSA routing ──────────────────────────────────────────────────────
    if NETWORK_LOADED and STOPS and CONNECTIONS and IMPORTS_OK:
        try:
            origin_stops = find_nearest_stops(origin_lat, origin_lng, STOPS, n=3, max_dist_m=1000)
            dest_stops   = find_nearest_stops(dest_lat,   dest_lng,   STOPS, n=3, max_dist_m=1000)

            if not origin_stops:
                raise HTTPException(404, "No transit stops found near origin.")
            if not dest_stops:
                raise HTTPException(404, "No transit stops found near destination.")

            for stop in origin_stops:
                stop._walk_dist_m = haversine(origin_lat, origin_lng, stop.lat, stop.lng)
            for stop in dest_stops:
                stop._walk_dist_m = haversine(dest_lat, dest_lng, stop.lat, stop.lng)

            result = run_csa(
                connections=CONNECTIONS,
                origin_stops=origin_stops,
                dest_stops=dest_stops,
                departure_time_sec=dep_time_sec,
                filters=filters,
                stops_dict=STOPS
            )
            if result is None:
                raise HTTPException(404, "No route found for this departure time.")

            result["localized_tips"] = get_localized_tips(profile)

            # Enrich polyline with Google Directions road geometry
            result = enrich_polyline_with_directions(result)
            return result

        except HTTPException:
            raise
        except Exception as e:
            print(f"CSA error: {e}")
            # Fall through to mock

    # ── Mock fallback ─────────────────────────────────────────────────────────
    return _mock_route(origin_lat, origin_lng, dest_lat, dest_lng,
                       profile, is_student, is_pwd)


# ─────────────────────────────────────────────────────────────────────────────
# MOCK ROUTE
# ─────────────────────────────────────────────────────────────────────────────

def _fare_for_distance(mode: str, distance_m: float, filters: dict) -> tuple:
    """Compute fare and discount for a given mode and distance."""
    FARE_TABLE = {
        "JEEPNEY":    {"base": 13.0, "per_km": 1.80, "base_km": 4.0, "max": 50.0},
        "BUS":        {"base": 15.0, "per_km": 2.20, "base_km": 5.0, "max": 80.0},
        "UV_EXPRESS": {"base": 20.0, "per_km": 2.50, "base_km": 5.0, "max": 80.0},
        "MRT":        {"base": 13.0, "per_km": 1.00, "base_km": 2.0, "max": 28.0},
        "LRT":        {"base": 12.0, "per_km": 1.00, "base_km": 2.0, "max": 30.0},
    }
    t = FARE_TABLE.get(mode, FARE_TABLE["JEEPNEY"])
    km = distance_m / 1000
    raw = t["base"] if km <= t["base_km"] else t["base"] + (km - t["base_km"]) * t["per_km"]
    raw = min(raw, t["max"])
    discount_rate = filters.get("student_discount", 0.0) or filters.get("pwd_discount", 0.0)
    discount = raw * discount_rate
    return round(raw - discount, 2), round(discount, 2)


def _mock_route(origin_lat, origin_lng, dest_lat, dest_lng,
                profile, is_student, is_pwd):
    import math

    filters = build_filters(profile, is_student, is_pwd)

    # Compute real straight-line distance between origin and destination
    R = 6371000
    dlat = math.radians(dest_lat - origin_lat)
    dlng = math.radians(dest_lng - origin_lng)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(origin_lat)) *         math.cos(math.radians(dest_lat)) * math.sin(dlng/2)**2
    total_dist_m = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    # Walk distances: 250m to first stop, 200m from last stop to dest
    walk1_m = 250
    walk2_m = 200
    ride_dist_m = max(200, total_dist_m - walk1_m - walk2_m)

    # Choose transit mode based on distance
    if total_dist_m > 15000:
        mode = "UV_EXPRESS"
        mode_label = "UV Express"
        speed_kmh = 35
    elif total_dist_m > 8000:
        mode = "BUS"
        mode_label = "Bus"
        speed_kmh = 25
    else:
        mode = "JEEPNEY"
        mode_label = "Jeepney"
        speed_kmh = 20

    # Override if night shift (UV Express runs 24/7 on EDSA)
    if profile == CommuterProfile.night_shift:
        mode = "UV_EXPRESS"
        mode_label = "UV Express (24hr)"
        speed_kmh = 35

    # Compute realistic fare
    ride_fare, discount = _fare_for_distance(mode, ride_dist_m, filters)
    original_ride_fare = ride_fare + discount

    # Compute realistic durations
    walk_speed = 5  # km/h
    walk1_min = max(1, int((walk1_m / 1000) / walk_speed * 60))
    walk2_min = max(1, int((walk2_m / 1000) / walk_speed * 60))
    ride_min  = max(2, int((ride_dist_m / 1000) / speed_kmh * 60))
    total_min = walk1_min + ride_min + walk2_min

    # Intermediate coordinates
    frac1 = walk1_m / max(total_dist_m, 1)
    frac2 = 1 - (walk2_m / max(total_dist_m, 1))
    stop1_lat = origin_lat + (dest_lat - origin_lat) * frac1
    stop1_lng = origin_lng + (dest_lng - origin_lng) * frac1
    stop2_lat = origin_lat + (dest_lat - origin_lat) * frac2
    stop2_lng = origin_lng + (dest_lng - origin_lng) * frac2

    tags = []
    if profile == CommuterProfile.accessible or is_pwd:
        tags.append("♿ Accessible Route")
    if profile == CommuterProfile.night_shift:
        tags.append("🌙 24-hr Verified")
    if discount > 0:
        tags.append(f"🎓 Discount Applied (₱{discount:.2f} off)")
    if total_dist_m < 5000:
        tags.append("✅ Direct Route")

    legs = [
        {
            "step_number": 1,
            "instruction": f"Walk {walk1_m}m to {mode_label} stop",
            "mode": "WALK",
            "duration_min": walk1_min,
            "fare": 0.0,
            "from_stop": "Your location",
            "to_stop": f"Nearest {mode_label} stop",
            "distance_m": walk1_m,
            "is_accessible": True, "is_lit": True, "is_24hr": True,
            "from_lat": origin_lat, "from_lng": origin_lng,
            "to_lat": stop1_lat, "to_lng": stop1_lng,
            "osm_geometry": []
        },
        {
            "step_number": 2,
            "instruction": f"Board {mode_label} → ride {round(ride_dist_m/1000, 1)} km to destination area",
            "mode": mode,
            "duration_min": ride_min,
            "fare": ride_fare,
            "from_stop": f"Nearest {mode_label} stop",
            "to_stop": "Nearest stop to destination",
            "distance_m": round(ride_dist_m),
            "is_accessible": True,
            "is_lit": True,
            "is_24hr": profile == CommuterProfile.night_shift,
            "from_lat": stop1_lat, "from_lng": stop1_lng,
            "to_lat": stop2_lat, "to_lng": stop2_lng,
            "osm_geometry": []
        },
        {
            "step_number": 3,
            "instruction": f"Walk {walk2_m}m to your destination",
            "mode": "WALK",
            "duration_min": walk2_min,
            "fare": 0.0,
            "from_stop": "Nearest stop to destination",
            "to_stop": "Your destination",
            "distance_m": walk2_m,
            "is_accessible": True, "is_lit": True, "is_24hr": True,
            "from_lat": stop2_lat, "from_lng": stop2_lng,
            "to_lat": dest_lat, "to_lng": dest_lng,
            "osm_geometry": []
        }
    ]

    result = {
        "route_id":         f"mock-{profile}-001",
        "total_duration":   total_min,
        "total_fare":       ride_fare,
        "original_fare":    original_ride_fare,
        "discount_applied": discount,
        "currency":         "PHP",
        "transfers":        0,
        "tags":             tags,
        "localized_tips":   get_localized_tips(profile),
        "polyline_points":  [],
        "legs":             legs
    }

    result = enrich_polyline_with_directions(result)
    return result


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
