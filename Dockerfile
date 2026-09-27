# syntax=docker/dockerfile:1

# ---------- Stage 1: build the React frontend with Vite ----------
FROM node:20-alpine AS frontend

WORKDIR /build

# Copied first so a source-only change does not invalidate the install layer.
COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./

# No VITE_API_URL / VITE_SOCKET_URL is set here on purpose. Both services fall
# back to the page's own origin, which is correct once Flask serves the bundle
# and the API together.
RUN npm run build


# ---------- Stage 2: Python runtime serving API, sockets and SPA ----------
FROM python:3.11-slim AS runtime

# Set by the pipeline's Build stage from the semantic version, so /health can
# report exactly which release is running.
ARG APP_VERSION=0.0.0

ENV APP_VERSION=${APP_VERSION} \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SOCKETIO_ASYNC_MODE=eventlet

WORKDIR /app

COPY backend/requirements.txt ./

# The build tooling is upgraded before the application's own dependencies
# because two of the HIGH findings from the Security stage in build #1 live
# there rather than in requirements.txt: CVE-2026-24049 in wheel (privilege
# escalation via a malicious wheel file) and CVE-2026-23949 in jaraco.context
# (path traversal via a malicious tar archive), which arrives as a dependency
# of setuptools. Both ship inside the python:3.11-slim base image.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt

COPY backend/ ./

# The compiled SPA, served by app.py's serve_spa() route.
COPY --from=frontend /build/dist ./static

# /app/data is where SQLite lives, backed by a named volume so the database
# survives an image rebuild.
RUN mkdir -p /app/data \
 && useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app

USER appuser

EXPOSE 5000

# Uses Python rather than curl so no extra apt packages enter the image,
# which keeps the Trivy scan in the Security stage clean.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=4).status == 200 else 1)"

# -w 1 is mandatory: Flask-SocketIO cannot span multiple workers without a
# Redis message queue, and a second worker would break the handshake.
CMD ["gunicorn", "-k", "eventlet", "-w", "1", "-b", "0.0.0.0:5000", \
     "--access-logfile", "-", "--error-logfile", "-", "app:app"]
