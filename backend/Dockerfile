# Railway.app Dockerfile for OptiWays CSA Backend
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for pyosmium
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    cmake \
    libboost-dev \
    libexpat1-dev \
    zlib1g-dev \
    libbz2-dev \
    libprotozero-dev \
    libboost-program-options-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY *.py .

# Create data directory and download OSM data
RUN mkdir -p data && \
    wget -q --show-progress \
    https://download.geofabrik.de/asia/philippines-latest.osm.pbf \
    -O data/philippines-latest.osm.pbf \
    && echo "✅ OSM file downloaded" \
    && ls -lh data/

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
