# ─────────────────────────────────────────────────────────────────────────────
# OptiWays CSA Backend — Railway.app Dockerfile
# Build time:  ~2 min (OSM download only)
# Runtime:     Server starts instantly in mock mode, loads OSM in background
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-bookworm

WORKDIR /app

# ─── System dependencies ──────────────────────────────────────────────────────
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
# Downloads Philippines OSM extract (~565MB) at build time.
# Cache bake happens at runtime in the background — no build timeout risk.
RUN mkdir -p data && \
    wget --no-verbose \
         --tries=3 \
         --timeout=300 \
         -O data/philippines-latest.osm.pbf \
         https://download.geofabrik.de/asia/philippines-latest.osm.pbf \
    && echo "✅ OSM download complete — $(du -sh data/philippines-latest.osm.pbf | cut -f1)"

# ─── Runtime ──────────────────────────────────────────────────────────────────
# Single worker to conserve RAM during OSM parse (~400MB peak).
# Server starts immediately in mock mode.
# Real CSA routing activates automatically after ~5 min background parse.
EXPOSE 8000

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
