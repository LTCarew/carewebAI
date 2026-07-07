# ─────────────────────────────────────────────────────────────
# CareWeb Registry — Production Dockerfile
# Target: Google Cloud Run
# ─────────────────────────────────────────────────────────────

# ── Stage 1: build / install dependencies ──────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# System deps for psycopg2-binary and general builds
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: final slim image ───────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Runtime system deps (libpq for psycopg2)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy project source
COPY . .

# Collect static files at build time so the image is self-contained
RUN python manage.py collectstatic --noinput

# Cloud Run injects PORT; gunicorn binds to it
ENV PORT=8080
EXPOSE 8080

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

# ── Entrypoint ──────────────────────────────────────────────
# Workers = 2 * CPU cores + 1; Cloud Run default is 1 vCPU → 3 workers
CMD exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers 3 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    config.wsgi:application
