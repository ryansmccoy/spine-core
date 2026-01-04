# Multi-stage Dockerfile for Market Spine Full
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Builder stage
FROM base as builder

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY migrations/ migrations/
COPY data/ data/

# Install dependencies
RUN uv sync --frozen --no-dev

# Runtime stage
FROM base as runtime

# Copy installed packages from builder
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/migrations /app/migrations
COPY --from=builder /app/data /app/data

# Set PATH
ENV PATH="/app/.venv/bin:$PATH"

# Create non-root user
RUN useradd -m -u 1000 spine && chown -R spine:spine /app
USER spine

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# Default command (API)
EXPOSE 8000
CMD ["uvicorn", "market_spine.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
