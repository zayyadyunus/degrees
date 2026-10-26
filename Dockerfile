# Single-container deploy: FastAPI serves both the API and the built UI.
#   docker build -t degrees .
#   docker run -p 8000:8000 degrees

# --- 1. Build the frontend ---------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# No VITE_API_URL: the production bundle calls its own origin.
RUN npm run build

# --- 2. Runtime --------------------------------------------------------------
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NLTK_DATA=/usr/local/share/nltk_data \
    DEGREES_ALLOW_SYNTHETIC=0 \
    DEGREES_STATIC_DIR=/app/frontend/dist \
    DEGREES_DOCS=0
# Trust X-Forwarded-For so rate limits key on the real client IP behind a
# platform proxy. If the container is exposed directly, set this to the
# proxy's address instead (clients could otherwise spoof their IP).
ENV FORWARDED_ALLOW_IPS=*

WORKDIR /app/backend
COPY backend/requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock \
 && python -m nltk.downloader -d "$NLTK_DATA" wordnet omw-1.4

COPY backend/app ./app
COPY backend/data ./data
COPY --from=frontend /app/frontend/dist /app/frontend/dist

RUN useradd --create-home --uid 1000 degrees
USER degrees

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=2)"

# One worker only: games live in process memory. PORT is honored for
# platforms (Fly, Render, Cloud Run, Railway) that inject it.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
