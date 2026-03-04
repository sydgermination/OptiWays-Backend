# Railway.app Dockerfile for OptiWays CSA Backend
FROM python:3.11-bookworm

WORKDIR /app

# Install system dependencies + osmium
RUN apt-get update && apt-get install -y \
    wget \
    python3-osmium \
    && rm -rf /var/lib/apt/lists/*

# Make apt-installed pyosmium available to our python
RUN pip install --no-cache-dir osmium

# Install other Python dependencies
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
