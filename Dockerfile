# ─────────────────────────────────────────────────────────────────────────────
# GIS Bootcamp — Dockerized Spatial API
#
# Multi-stage build:
#   builder  — installs all Python dependencies (includes build-essential)
#   runtime  — minimal image with only the installed packages and app code
#
# Build:  docker build -t gis-bootcamp .
# Run:    docker run -p 8000:8000 gis-bootcamp
# Compose: docker compose up
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

# Build-time system deps (compiler toolchain for packages that build C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy only what pip needs to resolve and install dependencies.
# The gis_bootcamp source must be present so `pip install .` resolves the package.
COPY pyproject.toml .
COPY gis_bootcamp/ gis_bootcamp/

# Install into /install so we can copy just the packages to the runtime stage.
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --prefix=/install .


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="GIS Bootcamp Spatial API"
LABEL org.opencontainers.image.description="FastAPI service exposing geospatial tools"
LABEL org.opencontainers.image.source="https://github.com/BarackAyinde/gis-bootcamp"

# Runtime system libs required by geospatial binary wheels:
#   libgomp1  — OpenMP runtime (numpy, scipy parallelism)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Pull installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source (already available as part of the installed package,
# but kept here for uvicorn's module discovery path)
COPY gis_bootcamp/ gis_bootcamp/

# Create a non-root user and own the working directory
RUN adduser --disabled-password --gecos "" --uid 1000 appuser \
    && mkdir -p /app/data /app/output \
    && chown -R appuser:appuser /app

USER appuser

# Port that uvicorn binds to inside the container
EXPOSE 8000

# Liveness probe — polls /health every 30 s; fails if three consecutive checks fail
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" \
        || exit 1

# Production entry point: single uvicorn worker (scale horizontally via replicas)
CMD ["python", "-m", "uvicorn", "gis_bootcamp.spatial_api:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
