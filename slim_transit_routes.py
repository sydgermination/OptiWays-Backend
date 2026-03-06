"""
slim_transit_routes.py - Stream-parses transit_routes.json with minimal RAM.
Usage: python3 slim_transit_routes.py
Output: data/transit_routes_slim.json (~10MB)
"""
import json, os, gc

INPUT  = "data/transit_routes.json"
OUTPUT = "data/transit_routes_slim.json"
MAX_PTS   = 200
PRECISION = 4

def slim_geom(pts):
    if not pts: return []
    if len(pts) > MAX_PTS:
        step = len(pts) / MAX_PTS
        pts  = [pts[int(i * step)] for i in range(MAX_PTS)]
    return [{"lat": round(p["lat"], PRECISION), "lng": round(p["lng"], PRECISION)} for p in pts]

def slim_stops(stops):
    return [{"id": s["id"], "lat": round(s["lat"], PRECISION),
             "lng": round(s["lng"], PRECISION), "name": s.get("name","")} for s in stops]

def slim_route(r):
    stops = slim_stops(r.get("stops", []))
    geom  = slim_geom(r.get("geometry", []))
    if len(stops) < 2 and len(geom) < 2: return None
    return {"relation_id": r["relation_id"], "name": r.get("name",""),
            "from": r.get("from",""), "to": r.get("to",""),
            "mode": r.get("mode","BUS"), "colour": r.get("colour","#888888"),
            "distance_m": r.get("distance_m",0), "service": r.get("service",{}),
            "stops": stops, "geometry": geom}

print(f"Loading {INPUT} ({os.path.getsize(INPUT)/1e6:.1f} MB)...")

try:
    import ijson
    kept, skipped, by_mode = [], 0, {}
    print("Using ijson streaming...")
    with open(INPUT, "rb") as f:
        for i, route in enumerate(ijson.items(f, "routes.item")):
            s = slim_route(route)
            if s:
                kept.append(s)
                by_mode[s["mode"]] = by_mode.get(s["mode"],0) + 1
            else:
                skipped += 1
            if i % 50 == 0: print(f"  {i} routes...", end="\r")
except ImportError:
    print("Installing ijson...")
    os.system("pip install ijson -q")
    try:
        import ijson
        kept, skipped, by_mode = [], 0, {}
        with open(INPUT, "rb") as f:
            for i, route in enumerate(ijson.items(f, "routes.item")):
                s = slim_route(route)
                if s:
                    kept.append(s)
                    by_mode[s["mode"]] = by_mode.get(s["mode"],0) + 1
                else:
                    skipped += 1
    except:
        print("Falling back to standard json...")
        with open(INPUT, encoding="utf-8") as f:
            data = json.load(f)
        routes = data["routes"]; del data; gc.collect()
        kept, skipped, by_mode = [], 0, {}
        for route in routes:
            s = slim_route(route)
            if s:
                kept.append(s)
                by_mode[s["mode"]] = by_mode.get(s["mode"],0) + 1
            else:
                skipped += 1
        del routes; gc.collect()

print(f"\n✅ {len(kept)} routes kept, {skipped} skipped")
print(f"   Modes: {by_mode}")

os.makedirs("data", exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump({"source": "OpenStreetMap (slimmed)", "route_count": len(kept),
               "by_mode": by_mode, "routes": kept}, f,
              ensure_ascii=False, separators=(',',':'))

out_mb = os.path.getsize(OUTPUT)/1e6
print(f"💾 Saved {OUTPUT} ({out_mb:.1f} MB)")
print(f"✅ Upload to Google Drive and update your Dockerfile with the new file ID.")