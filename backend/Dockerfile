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

# Download transit_routes.json from Google Drive
RUN mkdir -p data && gdown "1Upirxqn7b7ls_kmthJ71P6stf5WyMYY7" -O data/transit_routes.json \
    && echo "✅ Downloaded: $(du -sh data/transit_routes.json)"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
