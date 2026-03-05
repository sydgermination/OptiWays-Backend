# ─────────────────────────────────────────────────────────────────────────────
# OptiWays CSA Backend — Railway.app Dockerfile
# Lightweight mode: uses data/transit_routes.json only (no PBF download)
# Build time:  ~1 min
# RAM needed:  ~300MB
# Startup:     ~30 seconds (JSON parse, no PBF needed)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# Minimal system deps — no osmium needed in JSON-only mode
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Source code
COPY *.py .

# Transit data (transit_routes.json — committed via Git LFS)
COPY data/ ./data/

EXPOSE 8000

CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1"]
