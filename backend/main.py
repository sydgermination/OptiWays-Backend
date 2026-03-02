"""
OptiWays CSA Routing Backend
Deploy to Railway.app — https://railway.app
Data: philippines-260301.osm.pbf
"""

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from enum import Enum
from typing import Optional
import uvicorn
import os

app = FastAPI(
    title="OptiWays CSA Backend",
    description="Connection Scan Algorithm routing for Philippine transit",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)

class CommuterProfile(str, Enum):
    default     = "default"
    night_shift = "night_shift"
    student     = "student"
    accessible  = "accessible"


def build_filters(profile: CommuterProfile, is_student: bool, is_pwd: bool) -> dict:
    """Build profile-specific routing constraints for CSA."""
    base = {"max_walk_km": 0.5}

    if profile == CommuterProfile.night_shift:
        return {**base,
            "require_24hr_terminals": True,
            "require_lit_paths": True,
            "service_cutoff_time": "02:00",
            "prefer_routes": ["UV_EXPRESS", "P2P"],
            "exclude_routes_after_cutoff": True
        }
    elif profile == CommuterProfile.student:
        return {**base,
            "optimize_for": "fare",
            "student_discount": 0.20 if is_student else 0.0,
            "prefer_university_stops": True,
            "exclude_modes": ["P2P"],  # P2P doesn't honor student discount
            "max_fare_php": 50.0
        }
    elif profile == CommuterProfile.accessible or is_pwd:
        return {**base,
            "no_stairs": True,
            "elevator_only": True,
            "accessible_stations_only": True,
            "no_footbridges_without_elevator": True,
            "prefer_ground_level_stops": True,
            "max_walk_km": 0.3  # shorter walks for PWD
        }
    else:
        return {**base, "optimize_for": "time"}


def calculate_fare_with_discount(base_fare: float, profile: CommuterProfile,
                                  is_student: bool, is_pwd: bool) -> tuple[float, float]:
    """Returns (final_fare, discount_amount)"""
    discount = 0.0
    if profile == CommuterProfile.student and is_student:
        discount = base_fare * 0.20
    elif is_pwd:
        discount = base_fare * 0.20  # PWD discount per RA 10754
    return base_fare - discount, discount


def mock_route_response(origin_lat, origin_lng, dest_lat, dest_lng,
                         profile, is_student, is_pwd):
    """
    MOCK RESPONSE — Replace with actual CSA algorithm output.
    The CSA algorithm should parse philippines-260301.osm.pbf and
    GTFS data to produce real routing results.
    """
    base_fare = 45.0
    final_fare, discount = calculate_fare_with_discount(
        base_fare, profile, is_student, is_pwd
    )

    tags = []
    if profile == CommuterProfile.accessible or is_pwd:
        tags.append("♿ Accessible Route")
    if profile == CommuterProfile.night_shift:
        tags.append("🌙 24-hr Verified")
    if profile == CommuterProfile.student and is_student:
        tags.append("🎓 Student Discount Applied")

    return {
        "route_id": f"mock-{profile}-001",
        "total_duration": 45,
        "total_fare": round(final_fare, 2),
        "original_fare": base_fare,
        "discount_applied": round(discount, 2),
        "currency": "PHP",
        "transfers": 2,
        "tags": tags,
        "localized_tips": get_localized_tips(profile),
        "polyline_points": [
            {"lat": origin_lat, "lng": origin_lng},
            {"lat": (origin_lat + dest_lat) / 2, "lng": (origin_lng + dest_lng) / 2},
            {"lat": dest_lat, "lng": dest_lng}
        ],
        "legs": [
            {
                "step_number": 1,
                "instruction": "Walk to Jeepney stop at Taft Avenue",
                "mode": "WALK",
                "duration_min": 5,
                "fare": 0.0,
                "from_stop": "Origin",
                "to_stop": "Taft Ave Jeepney Stop",
                "distance_m": 250,
                "is_accessible": True,
                "is_lit": True,
                "is_24hr": True,
                "from_lat": origin_lat, "from_lng": origin_lng,
                "to_lat": origin_lat + 0.002, "to_lng": origin_lng + 0.001
            },
            {
                "step_number": 2,
                "instruction": "Board Jeepney: Baclaran → Divisoria",
                "mode": "JEEPNEY",
                "duration_min": 20,
                "fare": round(final_fare * 0.5, 2),
                "from_stop": "Taft Ave Jeepney Stop",
                "to_stop": "Quiapo",
                "distance_m": 3200,
                "is_accessible": profile != CommuterProfile.ACCESSIBLE,
                "is_lit": True,
                "is_24hr": profile == CommuterProfile.NIGHT_SHIFT,
                "from_lat": origin_lat + 0.002, "from_lng": origin_lng + 0.001,
                "to_lat": dest_lat - 0.002, "to_lng": dest_lng - 0.001
            },
            {
                "step_number": 3,
                "instruction": "Walk to destination",
                "mode": "WALK",
                "duration_min": 5,
                "fare": 0.0,
                "from_stop": "Quiapo",
                "to_stop": "Destination",
                "distance_m": 300,
                "is_accessible": True,
                "is_lit": True,
                "is_24hr": True,
                "from_lat": dest_lat - 0.002, "from_lng": dest_lng - 0.001,
                "to_lat": dest_lat, "to_lng": dest_lng
            }
        ]
    }


def get_localized_tips(profile: CommuterProfile) -> list[str]:
    tips = {
        CommuterProfile.default: [
            "Avoid EDSA during rush hours (7-9AM, 5-8PM)",
            "Use Beep card for faster MRT/LRT boarding"
        ],
        CommuterProfile.night_shift: [
            "UV Express terminals at Cubao, Ayala, and Ortigas operate 24/7",
            "Keep emergency contacts saved — text MMDA 1-3-6 for incidents",
            "Grab and Angkas are available for late-night first/last mile"
        ],
        CommuterProfile.student: [
            "Show valid school ID for student discount — up to 20% off",
            "LRT/MRT student discount stored rates require separate application",
            "Jeepney flag-down rate is ₱13 for first 4km"
        ],
        CommuterProfile.accessible: [
            "MRT-3 Accessible gates are at North Avenue, Ayala, and Taft",
            "LRT-1 has elevators at EDSA, Gil Puyat, and Baclaran stations",
            "Call ahead: 1-800-MMDA for accessible transport assistance"
        ]
    }
    return tips.get(profile, [])


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "OptiWays CSA Backend running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok", "osm_data": os.path.exists("data/philippines-260301.osm.pbf")}


@app.get("/route")
def get_route(
    origin_lat:       float = Query(..., description="Origin latitude"),
    origin_lng:       float = Query(..., description="Origin longitude"),
    dest_lat:         float = Query(..., description="Destination latitude"),
    dest_lng:         float = Query(..., description="Destination longitude"),
    profile:          CommuterProfile = Query(CommuterProfile.default),
    departure_time:   Optional[str] = Query(None, description="ISO 8601 departure time"),
    is_student:       bool = Query(False),
    is_pwd:           bool = Query(False)
):
    # Validate Philippines bounding box
    if not (4.5 <= origin_lat <= 21.5 and 116.0 <= origin_lng <= 127.0):
        raise HTTPException(status_code=400, detail="Origin must be within the Philippines")
    if not (4.5 <= dest_lat <= 21.5 and 116.0 <= dest_lng <= 127.0):
        raise HTTPException(status_code=400, detail="Destination must be within the Philippines")

    filters = build_filters(profile, is_student, is_pwd)

    # TODO: Replace mock_route_response with actual CSA call:
    # result = run_csa(
    #     osm_file="data/philippines-260301.osm.pbf",
    #     origin=(origin_lat, origin_lng),
    #     destination=(dest_lat, dest_lng),
    #     departure_time=departure_time,
    #     filters=filters
    # )

    result = mock_route_response(
        origin_lat, origin_lng, dest_lat, dest_lng,
        profile, is_student, is_pwd
    )
    return result


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
