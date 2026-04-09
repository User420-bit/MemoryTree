# Memory Tree — Multi-Stage Dockerfile (ARM64/Pi Zero 2 W optimiert)

# ── Stage 1: Python Dependencies bauen ──────────────────────────────────────
FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libc6-dev libjpeg62-turbo-dev zlib1g-dev libwebp-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime Image ──────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS runtime

# Sicherheit: non-root User
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Runtime-Abhängigkeiten (Pillow benötigt libjpeg, libwebp)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libjpeg62-turbo libwebp7 sqlite3 curl && \
    rm -rf /var/lib/apt/lists/*

# Python-Pakete aus Build-Stage kopieren
COPY --from=builder /install /usr/local

# Python-Optimierungen
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

# Anwendungscode kopieren
COPY main.py config.py database.py auth.py models.py schemas.py middleware.py uploads.py gunicorn.conf.py ./
COPY routers/ ./routers/
COPY templates/ ./templates/
COPY static/ ./static/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Daten-Verzeichnisse erstellen
RUN mkdir -p /app/data/uploads/thumbs && \
    chown -R appuser:appuser /app/data

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Als non-root User ausführen
USER appuser

EXPOSE 8000

# Gunicorn mit UvicornWorker starten
CMD ["gunicorn", "-c", "gunicorn.conf.py", "main:app"]
