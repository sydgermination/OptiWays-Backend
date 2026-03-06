# Railway.app Dockerfile for OptiWays CSA Backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including wget
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    libboost-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py .

# Create data directory
RUN mkdir -p data

# Download Philippines OSM data during build
# Source: Geofabrik (official OSM mirror, always up to date)
RUN wget -q --show-progress \
    https://download.geofabrik.de/asia/philippines-latest.osm.pbf \
    -O data/philippines-260301.osm.pbf \
    && echo "✅ OSM file downloaded successfully" \
    && ls -lh data/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]