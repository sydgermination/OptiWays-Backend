# ─────────────────────────────────────────────────────────────────────────────
# OptiWays CSA Backend — Railway.app Dockerfile
# Build time:  ~10-15 min (OSM download + parse + cache bake)
# Runtime:     ~3 sec cold start (loads pre-baked cache)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-bookworm AS base

WORKDIR /app

# ─── System dependencies ──────────────────────────────────────────────────────
# osmium-tool + libosmium for the Python osmium binding
RUN apt-get update && apt-get install -y --no-install-recommends \
        wget \
        build-essential \
        cmake \
        libosmium2-dev \
        libprotozero-dev \
        libboost-python-dev \
        libboost-dev \
        zlib1g-dev \
        libexpat1-dev \
        libbz2-dev \
        liblz4-dev \
        libzstd-dev \
    && rm -rf /var/lib/apt/lists/*

# ─── Python dependencies ──────────────────────────────────────────────────────
RUN pip install --no-cache-dir osmium

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Source code ──────────────────────────────────────────────────────────────
COPY *.py .

# ─── OSM data download ────────────────────────────────────────────────────────
# Download Philippines OSM extract (~300 MB).
# Using --no-verbose keeps build logs clean; remove if you want progress.
RUN mkdir -p data && \
    wget --no-verbose \
         --tries=3 \
         --timeout=120 \
         -O data/philippines-latest.osm.pbf \
         https://download.geofabrik.de/asia/philippines-latest.osm.pbf \
    && echo "✅ OSM download complete — $(du -sh data/philippines-latest.osm.pbf | cut -f1)"

# ─── Pre-bake the transit cache ───────────────────────────────────────────────
# Runs the full OSM parse + timetable build at IMAGE BUILD TIME.
# This moves the ~5 min parse cost to CI/CD, making every cold start instant.
# If the parse fails the build fails loudly here rather than silently at runtime.
RUN python - <<'EOF'
import sys
from osm_loader import load_or_build_network

print("🏗️  Pre-baking transit cache...")
stops, connections = load_or_build_network(
    "data/philippines-latest.osm.pbf",
    force_rebuild=True
)
if len(stops) < 500:
    print(f"❌ Only {len(stops)} stops found — something is wrong. Failing build.")
    sys.exit(1)
if len(connections) < 1000:
    print(f"❌ Only {len(connections)} connections found — something is wrong. Failing build.")
    sys.exit(1)
print(f"✅ Cache baked: {len(stops):,} stops, {len(connections):,} connections")
EOF

# Verify cache file exists and print its size
RUN ls -lh data/ph_transit_cache.pkl && \
    echo "✅ Cache file verified"

# ─── Runtime ──────────────────────────────────────────────────────────────────
EXPOSE 8000

# Use 2 workers — Railway free tier has 512 MB RAM; increase for paid plans.
# --preload shares the loaded network across workers (saves memory).
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--preload"]
