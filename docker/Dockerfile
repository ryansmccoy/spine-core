# ============================================
# spine-core Dockerfile
# ============================================
# Multi-stage build using uv for fast installs.
#
# Build:
#   docker build -f docker/Dockerfile -t spine-core .
#
# Run:
#   docker run -p 12000:80 spine-core
# ============================================

# --- Stage 1: Builder ---
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package with all optional dependencies
RUN uv pip install --system --no-cache ".[all]"

# --- Stage 2: Runtime ---
FROM python:3.12-slim AS runtime

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY src/ src/
COPY .env.base .env.base

# Create data directory
RUN mkdir -p /app/data /app/logs

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1
ENV SPINE_DATA_DIR=/app/data
ENV SPINE_LOG_DIR=/app/logs
ENV SPINE_API_HOST=0.0.0.0

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:80/health/live || exit 1

# Run the API on port 80 inside the container (mapped to 12000 externally)
CMD ["uvicorn", "spine.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "80"]
