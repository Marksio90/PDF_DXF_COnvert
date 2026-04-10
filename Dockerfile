# ── Stage 1: Build Next.js frontend ──────────────────────────────────────
FROM node:20-alpine AS frontend-build
WORKDIR /app

COPY frontend/package.json ./
RUN npm install

COPY frontend/ ./
RUN npm run build

# ── Stage 2: Combined runtime (Python 3.11 + Node.js 20) ─────────────────
FROM python:3.11-slim

# System deps: Node.js 20 + MuPDF (required by PyMuPDF) + wget (health probe)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates wget libmupdf-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# ── Python backend ────────────────────────────────────────────────────────
WORKDIR /backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app/ ./app/

# ── Next.js standalone frontend ───────────────────────────────────────────
WORKDIR /frontend
COPY --from=frontend-build /app/.next/standalone ./
COPY --from=frontend-build /app/.next/static ./.next/static
RUN mkdir -p public

# ── Data dirs + startup script ────────────────────────────────────────────
RUN mkdir -p /data/uploads /data/outputs /data/previews

COPY start.sh /start.sh
RUN chmod +x /start.sh

ENV PYTHONUNBUFFERED=1

# Railway exposes $PORT → Next.js; backend on 8000 is internal only
EXPOSE 3000

CMD ["/start.sh"]
