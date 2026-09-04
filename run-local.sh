#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "   DroneWatch Platform - Local Docker Stack Launch"
echo "=========================================================="

# Ensure .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Ensure video directory exists
if [ ! -d videos ]; then
    mkdir -p videos
fi

echo "Building and starting Docker services..."
docker compose down --remove-orphans
docker compose up -d --build

echo "Waiting for PostgreSQL database to initialize..."
until docker compose exec -T postgres pg_isready -U postgres; do
    echo "Waiting for database..."
    sleep 2
done

echo "Database is ready! Applying schema and seeds..."
docker compose exec -T postgres psql -U postgres -d dronewatch -f /docker-entrypoint-initdb.d/schema.sql
docker compose exec -T postgres psql -U postgres -d dronewatch -f /docker-entrypoint-initdb.d/seed.sql

echo "=========================================================="
echo "   DroneWatch Platform is running successfully!"
echo "   - Frontend Dashboard:   http://localhost:3000"
echo "   - Express REST API:     http://localhost:8080/api/v1/health"
echo "   - MediaMTX RTSP Server: rtsp://localhost:8554"
echo "   - MediaMTX HLS Stream:  http://localhost:8888"
echo "=========================================================="
