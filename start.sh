#!/bin/sh
set -e

mkdir -p /data/uploads /data/outputs /data/previews

echo "Starting backend on port 8000..."
cd /backend
DATA_DIR=/data \
UPLOADS_DIR=/data/uploads \
OUTPUTS_DIR=/data/outputs \
PREVIEWS_DIR=/data/previews \
DB_PATH=/data/jobs.db \
CORS_ORIGINS='["*"]' \
TZ=Europe/Warsaw \
uvicorn app.main:app --host 0.0.0.0 --port 8000 &

# Wait until backend is ready
i=0
until wget -qO- http://localhost:8000/health >/dev/null 2>&1; do
    i=$((i+1))
    if [ $i -ge 30 ]; then echo "Backend failed to start"; exit 1; fi
    sleep 1
done
echo "Backend ready."

echo "Starting frontend on port ${PORT:-3000}..."
cd /frontend
PORT=${PORT:-3000} \
HOSTNAME=0.0.0.0 \
BACKEND_URL=http://localhost:8000 \
exec node server.js
