# OptiWays CSA Backend — Railway.app Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Download transit routes from GitHub Releases
RUN mkdir -p data && wget -q \
    "https://github.com/sydgermination/OptiWays-Backend/releases/download/v1.0/transit_routes_slim.json" \
    -O data/transit_routes.json \
    && echo "✅ Downloaded: $(du -sh data/transit_routes.json)"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
