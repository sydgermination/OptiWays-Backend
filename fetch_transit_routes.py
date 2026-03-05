"""
fetch_transit_routes.py
───────────────────────
Fetches ALL public transit route relations from OpenStreetMap
for Metro Manila via the Overpass API:

  • JEEPNEY / PUJ   (route=share_taxi, network~PUJ)
  • BUS / LTFRB PUB (route=bus, network~PUB)
  • UV EXPRESS       (route=bus, vehicle~UV)
  • P2P BUS          (route=bus, network~P2P)
  • MRT-3            (route=light_rail, ref~MRT)
  • LRT-1 / LRT-2    (route=light_rail or subway)
  • PNR              (route=train)

Output files (in data/):
  data/transit_routes.json   ← combined all-modes file for OptiWays backend
  data/routes_jeepney.json   ← per-mode breakdown (optional, for inspection)
  data/routes_bus.json
  data/routes_rail.json

USAGE
─────
  # Fetch live from Overpass API (needs internet):
  python3 fetch_transit_routes.py

  # Use a local Overpass Turbo GeoJSON export:
  python3 fetch_transit_routes.py --local overpass_export.json

  # Fetch only specific modes:
  python3 fetch_transit_routes.py --modes jeepney,bus,rail

OVERPASS TURBO MANUAL OPTION
─────────────────────────────
  1. Go to https://overpass-turbo.eu/
  2. Paste the query from overpass_transit_query.txt
  3. Run → Export → Download as GeoJSON
  4. python3 fetch_transit_routes.py --local overpass_export.json
"""

import urllib.request
import urllib.parse
import json
import math
import sys
import os
import time
from typing import List, Dict, Tuple, Optional

# ── CONFIG ────────────────────────────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
BBOX         = "14.0,120.5,15.2,121.5"   # Metro Manila bounding box
OUTPUT_FILE  = "data/transit_routes.json"
TIMEOUT_SEC  = 180

# Mode classification rules applied to OSM tags
MODE_RULES = [
    # (mode_name, display_name, color, match_fn)
    ("MRT",        "MRT-3",          "#FFD700", lambda t: (
        t.get("route") in ("light_rail", "subway") and
        any(x in t.get("ref","").upper() + t.get("name","").upper() + t.get("network","").upper()
            for x in ("MRT", "METRO"))
    )),
    ("LRT",        "LRT",            "#008000", lambda t: (
        t.get("route") in ("light_rail", "subway", "tram") and
        any(x in t.get("ref","").upper() + t.get("name","").upper() + t.get("network","").upper()
            for x in ("LRT", "LIGHT RAIL"))
    )),
    ("PNR",        "PNR Train",      "#800080", lambda t: (
        t.get("route") == "train"
    )),
    ("UV_EXPRESS", "UV Express",     "#0000FF", lambda t: (
        t.get("route") in ("bus", "share_taxi") and
        any(x in t.get("name","").upper() + t.get("ref","").upper() +
                 t.get("operator","").upper() + t.get("network","").upper()
            for x in ("UV", "P2P", "POINT TO POINT", "PREMIUM"))
    )),
    ("JEEPNEY",    "Jeepney / PUJ",  "#FF6600", lambda t: (
        t.get("route") == "share_taxi" or
        "PUJ" in t.get("network","").upper() or
        t.get("passenger") == "jeepney"
    )),
    ("BUS",        "Bus / PUB",      "#FF0000", lambda t: (
        t.get("route") == "bus"
    )),
]

# Service schedule per mode: (start_hr, end_hr, freq_min, speed_kmh)
SERVICE = {
    "JEEPNEY":    (5, 22, 10,  20),
    "BUS":        (5, 23, 15,  25),
    "UV_EXPRESS": (5, 23,  8,  35),
    "MRT":        (5, 22,  5,  45),
    "LRT":        (5, 22,  5,  40),
    "PNR":        (5, 21, 30,  60),
}

# LTFRB fare table: base_fare, per_km, base_km, max_fare
FARE = {
    "JEEPNEY":    (13.0, 1.80, 4.0,  50.0),
    "BUS":        (15.0, 2.20, 5.0,  80.0),
    "UV_EXPRESS": (20.0, 2.50, 5.0,  80.0),
    "MRT":        (13.0, 1.00, 2.0,  28.0),
    "LRT":        (12.0, 1.00, 2.0,  30.0),
    "PNR":        (15.0, 1.00, 5.0, 100.0),
}


# ── OVERPASS QUERIES (one per mode group to avoid timeout) ────────────────────

QUERIES = {
    "jeepney": f"""
[out:json][timeout:{TIMEOUT_SEC}];
(
  relation["type"="route"]["route"="share_taxi"]({BBOX});
  relation["type"="route"]["route"="bus"]["network"="LTFRB PUJ"]({BBOX});
  relation["type"="route"]["route"="bus"]["network"~"PUJ",i]({BBOX});
  relation["type"="route"]["route"="bus"]["passenger"="jeepney"]({BBOX});
);
out geom;
""",
    "bus": f"""
[out:json][timeout:{TIMEOUT_SEC}];
(
  relation["type"="route"]["route"="bus"]["network"="LTFRB PUB"]({BBOX});
  relation["type"="route"]["route"="bus"]["network"~"PUB",i]({BBOX});
  relation["type"="route"]["route"="bus"]["operator"~"LTFRB",i]({BBOX});
  relation["type"="route"]["route"="bus"]["network"~"UV",i]({BBOX});
  relation["type"="route"]["route"="bus"]["network"~"P2P",i]({BBOX});
);
out geom;
""",
    "rail": f"""
[out:json][timeout:{TIMEOUT_SEC}];
(
  relation["type"="route"]["route"="light_rail"]({BBOX});
  relation["type"="route"]["route"="subway"]({BBOX});
  relation["type"="route"]["route"="train"]({BBOX});
  relation["type"="route"]["route"="tram"]({BBOX});
  relation["type"="route"]["route"="monorail"]({BBOX});
);
out geom;
""",
}

# Combined single query (use if server allows large responses)
QUERY_ALL = f"""
[out:json][timeout:{TIMEOUT_SEC}];
(
  relation["type"="route"]["route"="share_taxi"]({BBOX});
  relation["type"="route"]["route"="bus"]({BBOX});
  relation["type"="route"]["route"="light_rail"]({BBOX});
  relation["type"="route"]["route"="subway"]({BBOX});
  relation["type"="route"]["route"="train"]({BBOX});
  relation["type"="route"]["route"="tram"]({BBOX});
  relation["type"="route"]["route"="monorail"]({BBOX});
);
out geom;
"""


# ── HELPERS ───────────────────────────────────────────────────────────────────

def haversine(lat1, lng1, lat2, lng2) -> float:
    R = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a  = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def classify_mode(tags: dict) -> str:
    """Return OptiWays mode string based on OSM tags."""
    for mode, _, _, match in MODE_RULES:
        if match(tags):
            return mode
    # Generic fallback
    route = tags.get("route", "")
    if route in ("light_rail", "subway", "tram", "monorail"):
        return "LRT"
    if route == "train":
        return "PNR"
    if route == "bus":
        return "BUS"
    return "BUS"


def calc_fare(mode: str, distance_m: float) -> float:
    base, per_km, base_km, max_f = FARE.get(mode, FARE["BUS"])
    km  = distance_m / 1000
    raw = base if km <= base_km else base + (km - base_km) * per_km
    return round(min(raw, max_f), 2)


def stitch_ways(members: list) -> list:
    """
    Chain-stitch way geometries from relation members into a single
    ordered list of {lat, lng} points following the route path.
    """
    ways = []
    for m in members:
        if m.get("type") != "way":
            continue
        geom = m.get("geometry", [])
        if not geom:
            continue
        ways.append([{"lat": g["lat"], "lng": g["lon"]} for g in geom])

    if not ways:
        return []
    if len(ways) == 1:
        return ways[0]

    def d2(a, b):
        return (a["lat"]-b["lat"])**2 + (a["lng"]-b["lng"])**2

    result = list(ways[0])
    for way in ways[1:]:
        tail = result[-1]
        if d2(tail, way[0]) <= d2(tail, way[-1]):
            result.extend(way[1:])
        else:
            result.extend(reversed(way[:-1]))

    # Deduplicate consecutive identical points
    deduped = [result[0]]
    for pt in result[1:]:
        if pt["lat"] != deduped[-1]["lat"] or pt["lng"] != deduped[-1]["lng"]:
            deduped.append(pt)
    return deduped


def extract_stops(members: list) -> list:
    """Extract stop node members as {id, lat, lng, name} dicts."""
    stops = []
    seen  = set()
    for m in members:
        if m.get("type") != "node":
            continue
        role = m.get("role", "")
        if role not in ("stop","stop_entry_only","stop_exit_only","platform",""):
            continue
        if "lat" not in m or "lon" not in m:
            continue
        sid = str(m["ref"])
        if sid in seen:
            continue
        seen.add(sid)
        stops.append({
            "id":   sid,
            "lat":  m["lat"],
            "lng":  m["lon"],
            "name": m.get("tags", {}).get("name", f"Stop_{sid}"),
        })
    return stops


def route_distance(geometry: list) -> float:
    if len(geometry) < 2:
        return 0.0
    return round(sum(
        haversine(geometry[i]["lat"], geometry[i]["lng"],
                  geometry[i+1]["lat"], geometry[i+1]["lng"])
        for i in range(len(geometry)-1)
    ))


def parse_element(el: dict) -> Optional[dict]:
    if el.get("type") != "relation":
        return None
    tags     = el.get("tags", {})
    members  = el.get("members", [])
    mode     = classify_mode(tags)
    geometry = stitch_ways(members)
    stops    = extract_stops(members)

    if not stops and not geometry:
        return None

    name  = tags.get("name", tags.get("ref", f"Route {el['id']}"))
    dist  = route_distance(geometry)
    svc   = SERVICE.get(mode, SERVICE["BUS"])

    return {
        "relation_id":  str(el["id"]),
        "name":         name,
        "ref":          tags.get("ref", ""),
        "from":         tags.get("from", ""),
        "to":           tags.get("to", ""),
        "via":          tags.get("via", ""),
        "direction":    f"{tags.get('from','')} → {tags.get('to','')}".strip(" →") or name,
        "operator":     tags.get("operator", ""),
        "network":      tags.get("network", ""),
        "mode":         mode,
        "route_type":   tags.get("route", ""),
        "colour":       tags.get("colour", next(
            (c for m,_,c,fn in MODE_RULES if m==mode), "#888888")),
        "distance_m":   dist,
        "stop_count":   len(stops),
        "stops":        stops,
        "geometry":     geometry,
        "service": {
            "start_hr":  svc[0],
            "end_hr":    svc[1],
            "freq_min":  svc[2],
            "speed_kmh": svc[3],
        },
        "osm_tags":     tags,
    }


# ── FETCH ─────────────────────────────────────────────────────────────────────

def fetch_overpass(query: str, label: str) -> list:
    print(f"  ⏳ Fetching {label}...")
    data = urllib.parse.urlencode({"data": query}).encode()
    req  = urllib.request.Request(
        OVERPASS_URL, data=data,
        headers={"User-Agent": "OptiWays-ThesisProject/1.0"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SEC + 60) as resp:
        raw = resp.read().decode("utf-8")
    result = json.loads(raw)
    return result.get("elements", [])


def fetch_all_modes(modes: list) -> list:
    """Fetch each mode group separately, merge, deduplicate by relation_id."""
    all_elements = []
    seen_ids     = set()

    for mode_key in modes:
        query = QUERIES.get(mode_key)
        if not query:
            continue
        try:
            elements = fetch_overpass(query, mode_key)
            new = [e for e in elements if str(e.get("id","")) not in seen_ids]
            for e in new:
                seen_ids.add(str(e.get("id","")))
            all_elements.extend(new)
            print(f"     → {len(new)} relations fetched")
            time.sleep(2)   # be polite to Overpass server
        except Exception as e:
            print(f"  ⚠️  {mode_key} fetch failed: {e}")

    return all_elements


# ── GEOJSON LOCAL FILE LOADER ─────────────────────────────────────────────────

def load_geojson(path: str) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    elements = []
    if "elements" in data:
        return data["elements"]

    if "features" in data:
        for feat in data["features"]:
            props  = feat.get("properties", {})
            geom   = feat.get("geometry", {})
            coords = geom.get("coordinates", [])

            flat = []
            gtype = geom.get("type","")
            if gtype == "LineString":
                flat = [{"lat": c[1], "lng": c[0]} for c in coords]
            elif gtype == "MultiLineString":
                for line in coords:
                    flat.extend({"lat": c[1], "lng": c[0]} for c in line)

            fake_way = {
                "type": "way",
                "geometry": [{"lat": p["lat"], "lon": p["lng"]} for p in flat]
            }
            elements.append({
                "type":    "relation",
                "id":      props.get("@id","0").replace("relation/",""),
                "tags":    {k:v for k,v in props.items() if not k.startswith("@")},
                "members": [fake_way],
            })

    return elements


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    # Parse CLI args
    mode_filter = None
    local_file  = None

    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--local" and i < len(sys.argv)-1:
            local_file = sys.argv[i+1]
        if arg == "--modes" and i < len(sys.argv)-1:
            mode_filter = sys.argv[i+1].split(",")

    modes_to_fetch = mode_filter or ["jeepney", "bus", "rail"]

    print("╔══════════════════════════════════════════════════╗")
    print("║   OptiWays — Transit Route Fetcher               ║")
    print("║   Source: OpenStreetMap via Overpass API         ║")
    print("╚══════════════════════════════════════════════════╝")
    print(f"  Modes: {', '.join(modes_to_fetch)}")
    print(f"  BBox:  {BBOX}")
    print()

    # ── Fetch elements
    if local_file:
        print(f"📂 Loading local file: {local_file}")
        elements = load_geojson(local_file)
        print(f"   Loaded {len(elements)} elements")
    else:
        try:
            elements = fetch_all_modes(modes_to_fetch)
        except Exception as e:
            print(f"\n❌ Fetch failed: {e}")
            print("\n── MANUAL OPTION ──────────────────────────────────────")
            print("1. Go to https://overpass-turbo.eu/")
            print("2. Paste the query below and click Run:")
            print()
            print(QUERY_ALL)
            print("3. Export → Download as GeoJSON")
            print("4. Re-run: python3 fetch_transit_routes.py --local export.geojson")
            sys.exit(1)

    print(f"\n✅ Total elements fetched: {len(elements)}")

    # ── Parse routes
    routes     = []
    skipped    = 0
    by_mode: Dict[str, list] = {}

    for el in elements:
        parsed = parse_element(el)
        if parsed:
            routes.append(parsed)
            m = parsed["mode"]
            by_mode.setdefault(m, []).append(parsed)
        else:
            skipped += 1

    print(f"✅ Parsed {len(routes)} routes  ({skipped} skipped)\n")

    # ── Print summary table
    print("  Mode         Routes   With Geom   With Stops   Total km")
    print("  ─────────────────────────────────────────────────────────")
    total_km = 0
    for mode, _, color, _ in MODE_RULES:
        rs = by_mode.get(mode, [])
        if not rs:
            continue
        wg  = sum(1 for r in rs if len(r["geometry"]) >= 2)
        ws  = sum(1 for r in rs if r["stop_count"]    >= 2)
        km  = sum(r["distance_m"] for r in rs) / 1000
        total_km += km
        print(f"  {mode:<12} {len(rs):>6}   {wg:>9}   {ws:>10}   {km:>8.1f} km")
    print(f"  {'TOTAL':<12} {len(routes):>6}{'':>23}   {total_km:>8.1f} km\n")

    # ── Sample routes per mode
    for mode, label, _, _ in MODE_RULES:
        rs = by_mode.get(mode, [])
        if not rs:
            continue
        print(f"  {label} samples:")
        for r in rs[:3]:
            g = len(r["geometry"])
            s = r["stop_count"]
            print(f"    [{r['relation_id']}] {r['direction'][:55]:<55} "
                  f"{r['distance_m']/1000:.1f}km  {s}stops  {g}pts")
        print()

    # ── Save combined file
    os.makedirs("data", exist_ok=True)

    combined = {
        "source":       "OpenStreetMap via Overpass API",
        "bbox":         BBOX,
        "fetched_modes": modes_to_fetch,
        "route_count":  len(routes),
        "by_mode": {m: len(v) for m, v in by_mode.items()},
        "note": (
            "geometry[] = road-following path (stitch of OSM way members). "
            "stops[] = boarding/alighting points. "
            "Use relation_id as route_id in OptiWays CSA backend."
        ),
        "routes": routes
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, ensure_ascii=False, indent=2)

    size_mb = os.path.getsize(OUTPUT_FILE) / 1_048_576
    print(f"💾 Saved → {OUTPUT_FILE}  ({size_mb:.2f} MB)")

    # ── Save per-mode files for inspection
    for mode_key, mode_name, _, _ in [
        ("JEEPNEY","jeepney"), ("BUS","bus"),
        ("UV_EXPRESS","uv_express"), ("MRT","mrt"),
        ("LRT","lrt"), ("PNR","pnr")
    ]:
        rs = by_mode.get(mode_key, [])
        if not rs:
            continue
        path = f"data/routes_{mode_name}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mode": mode_key, "count": len(rs), "routes": rs},
                      f, ensure_ascii=False, indent=2)

    print(f"\n✅ Done! Upload data/transit_routes.json to backend/data/ on GitHub.")
    print(   "   Delete data/ph_transit_cache.pkl so the server rebuilds with new routes.")


if __name__ == "__main__":
    main()