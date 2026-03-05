# OptiWays CSA Backend — Railway.app Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install gdown for Google Drive downloads
RUN pip install --no-cache-dir gdown

COPY *.py .

# Download slimmed transit routes JSON from Google Drive (~10MB)
RUN mkdir -p data && gdown "1q_pQZhynQhWhMzUSvqZGVBz9aF2TwChL" -O data/transit_routes.json \
    && echo "✅ Downloaded: $(du -sh data/transit_routes.json)"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
