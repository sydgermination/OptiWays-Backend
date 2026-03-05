# OptiWays CSA Backend — Railway.app Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py .

# Download transit routes JSON from Google Drive at build time
RUN mkdir -p data && wget -q \
    "https://drive.google.com/uc?export=download&id=1Upirxqn7b7ls_kmthJ71P6stf5WyMYY7" \
    -O data/transit_routes.json \
    && echo "✅ transit_routes.json downloaded: $(du -sh data/transit_routes.json)"

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
