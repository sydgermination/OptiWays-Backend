"""
test_csa.py
Run this locally to verify your CSA is working before deploying.

Usage:
    python test_csa.py
"""

import sys
import json
from osm_loader import load_or_build_network, find_nearest_stops, haversine
from csa_algorithm import run_csa

# ── TEST ROUTES ───────────────────────────────────────────────────────────────
# Real Manila coordinates for testing

TEST_CASES = [
    {
        "name": "LRT Baclaran → Cubao (MRT transfer)",
        "origin": (14.5328, 120.9992),   # Baclaran
        "dest":   (14.6196, 121.0530),   # Cubao
        "profile": "default",
        "dep_time": "08:00"
    },
    {
        "name": "Taft Ave → BGC (Student)",
        "origin": (14.5514, 121.0000),   # Taft Ave / DLSU
        "dest":   (14.5481, 121.0440),   # BGC High Street
        "profile": "student",
        "dep_time": "07:30"
    },
    {
        "name": "Ortigas → Makati (Night Shift)",
        "origin": (14.5863, 121.0581),   # Ortigas
        "dest":   (14.5547, 121.0244),   # Ayala Makati
        "profile": "night_shift",
        "dep_time": "02:30"
    },
    {
        "name": "Quezon Ave → Divisoria (Accessible)",
        "origin": (14.6420, 121.0131),   # Quezon Ave MRT
        "dest":   (14.5990, 120.9740),   # Divisoria
        "profile": "accessible",
        "dep_time": "10:00"
    }
]


def parse_time(t: str) -> int:
    h, m = t.split(":")
    return int(h) * 3600 + int(m) * 60


def main():
    pbf = "data/philippines-260301.osm.pbf"
    print(f"Loading network from {pbf}...")
    stops, connections = load_or_build_network(pbf)
    print(f"✅ {len(stops):,} stops | {len(connections):,} connections\n")

    for test in TEST_CASES:
        print(f"{'='*60}")
        print(f"🧪 TEST: {test['name']}")
        print(f"   Profile: {test['profile']} | Departure: {test['dep_time']}")

        olat, olng = test["origin"]
        dlat, dlng = test["dest"]

        origin_stops = find_nearest_stops(olat, olng, stops, n=3, max_dist_m=1000)
        dest_stops   = find_nearest_stops(dlat, dlng, stops, n=3, max_dist_m=1000)

        if not origin_stops:
            print("   ❌ No stops near origin")
            continue
        if not dest_stops:
            print("   ❌ No stops near destination")
            continue

        # Attach walk distances
        for s in origin_stops:
            s._walk_dist_m = haversine(olat, olng, s.lat, s.lng)
        for s in dest_stops:
            s._walk_dist_m = haversine(dlat, dlng, s.lat, s.lng)

        print(f"   Origin stops: {[s.name for s in origin_stops]}")
        print(f"   Dest stops:   {[s.name for s in dest_stops]}")

        # Build filters
        filters = {}
        if test["profile"] == "night_shift":
            filters = {"require_24hr": True, "require_lit": True, "max_walk_km": 0.5}
        elif test["profile"] == "student":
            filters = {"student_discount": 0.20, "max_walk_km": 0.5}
        elif test["profile"] == "accessible":
            filters = {"no_stairs": True, "accessible_stations_only": True, "max_walk_km": 0.3}
        else:
            filters = {"max_walk_km": 0.5}

        dep_time = parse_time(test["dep_time"])
        result = run_csa(connections, origin_stops, dest_stops, dep_time, filters)

        if result is None:
            print("   ❌ No route found")
        else:
            print(f"   ✅ Route found!")
            print(f"   ⏱  Duration: {result['total_duration']} min")
            print(f"   💰 Fare: ₱{result['total_fare']} (saved ₱{result['discount_applied']})")
            print(f"   🔄 Transfers: {result['transfers']}")
            print(f"   🏷  Tags: {result['tags']}")
            print(f"   📍 Steps:")
            for leg in result["legs"]:
                print(f"      {leg['step_number']}. [{leg['mode']}] {leg['instruction']}")
                print(f"         ⏱ {leg['duration_min']}min | 💰 ₱{leg['fare']} | 📏 {leg['distance_m']:.0f}m")
        print()


if __name__ == "__main__":
    main()