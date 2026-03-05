# OptiWays CSA Backend — Railway.app Dockerfile
# Lightweight mode: uses data/transit_routes.json only
# No PBF download — builds network from OSM Overpass data instead
# Build time: ~1 min | RAM: ~300MB | Startup: ~30 sec

FROM python:3.11-slim

WORKDIR /app

# Minimal system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code
COPY *.py .

# Transit data (transit_routes.json via Git LFS — 749 routes, all modes)
COPY data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
