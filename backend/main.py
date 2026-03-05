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
MAPS_API_KEY = os.environ.get("MAPS_API_KEY", "AIzaSyA193wrQDd49sT-gk2eoF1x2UwQFWpYQD4")


async def load_network_background():
    global STOPS, CONNECTIONS, NETWORK_LOADED
    if not IMPORTS_OK:
        print("⚠️  Imports failed — staying in mock mode")
        return
    try:
        loop = asyncio.get_event_loop()
        if not os.path.exists(OSM_PATH):
            print(f"⚠️  OSM file not found at {OSM_PATH} — staying in mock mode")
            return
        print("🗺️  Loading Philippine transit network in background...")
        STOPS, CONNECTIONS = await loop.run_in_executor(
            None, load_or_build_network, OSM_PATH
        )
        NETWORK_LOADED = True
        print(f"✅ Ready — {len(STOPS):,} stops, {len(CONNECTIONS):,} connections")
    except Exception as e:
        print(f"⚠️  Failed to load network: {e} — staying in mock mode")


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(load_network_background())
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
    Replace CSA straight-line polyline with road-following Google Directions
    polyline by fetching directions for each leg individually.
    CSA routing decisions are unchanged — only the drawn path improves.
    """
    if not MAPS_API_KEY or not result.get("legs"):
        return result

    full_polyline = []
    for leg in result["legs"]:
        from_lat = leg.get("from_lat", 0.0)
        from_lng = leg.get("from_lng", 0.0)
        to_lat   = leg.get("to_lat",   0.0)
        to_lng   = leg.get("to_lng",   0.0)

        # Skip legs with missing coordinates
        if from_lat == 0.0 or to_lat == 0.0:
            continue

        mode = leg.get("mode", "WALK")
        leg_points = get_directions_polyline(from_lat, from_lng, to_lat, to_lng, mode)
        full_polyline.extend(leg_points)

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
                filters=filters
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

def _mock_route(origin_lat, origin_lng, dest_lat, dest_lng,
                profile, is_student, is_pwd):
    base_fare = 45.0
    filters   = build_filters(profile, is_student, is_pwd)
    discount  = base_fare * filters.get("student_discount", 0.0)
    final_fare = base_fare - discount

    mid_lat = (origin_lat + dest_lat) / 2
    mid_lng = (origin_lng + dest_lng) / 2

    tags = []
    if profile == CommuterProfile.accessible or is_pwd:
        tags.append("♿ Accessible Route")
    if profile == CommuterProfile.night_shift:
        tags.append("🌙 24-hr Verified")
    if profile == CommuterProfile.student and is_student:
        tags.append("🎓 Student Discount Applied")

    legs = [
        {
            "step_number": 1,
            "instruction": "Walk to nearest Jeepney stop",
            "mode": "WALK",
            "duration_min": 5,
            "fare": 0.0,
            "from_stop": "Your location",
            "to_stop": "Jeepney Stop",
            "distance_m": 250,
            "is_accessible": True, "is_lit": True, "is_24hr": True,
            "from_lat": origin_lat, "from_lng": origin_lng,
            "to_lat": mid_lat - 0.002, "to_lng": mid_lng
        },
        {
            "step_number": 2,
            "instruction": "Board Jeepney → ride to destination area",
            "mode": "JEEPNEY",
            "duration_min": 35,
            "fare": round(final_fare, 2),
            "from_stop": "Jeepney Stop",
            "to_stop": "Near Destination",
            "distance_m": 3500,
            "is_accessible": True, "is_lit": True, "is_24hr": False,
            "from_lat": mid_lat - 0.002, "from_lng": mid_lng,
            "to_lat": dest_lat + 0.001, "to_lng": dest_lng
        },
        {
            "step_number": 3,
            "instruction": "Walk to your destination",
            "mode": "WALK",
            "duration_min": 5,
            "fare": 0.0,
            "from_stop": "Near Destination",
            "to_stop": "Your destination",
            "distance_m": 200,
            "is_accessible": True, "is_lit": True, "is_24hr": True,
            "from_lat": dest_lat + 0.001, "from_lng": dest_lng,
            "to_lat": dest_lat, "to_lng": dest_lng
        }
    ]

    result = {
        "route_id":         f"mock-{profile}-001",
        "total_duration":   45,
        "total_fare":       round(final_fare, 2),
        "original_fare":    base_fare,
        "discount_applied": round(discount, 2),
        "currency":         "PHP",
        "transfers":        1,
        "tags":             tags,
        "localized_tips":   get_localized_tips(profile),
        "polyline_points":  [],
        "legs":             legs
    }

    # Enrich mock polyline with Google Directions too
    result = enrich_polyline_with_directions(result)
    return result


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
