# Railway.app Dockerfile for OptiWays CSA Backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies + pyosmium via apt (more reliable than pip)
RUN apt-get update && apt-get install -y \
    wget \
    python3-osmium \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (without pyosmium - installed via apt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py .

# Create data directory and download OSM data
RUN mkdir -p data && \
    wget -q \
    https://download.geofabrik.de/asia/philippines-latest.osm.pbf \
    -O data/philippines-latest.osm.pbf \
    && echo "✅ OSM file downloaded" \
    && ls -lh data/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
