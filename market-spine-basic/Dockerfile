# Market Spine Basic - Docker Image
# Multi-stage build for minimal production image

# =============================================================================
# Stage 1: Build environment
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy workspace files needed for dependency resolution
# We need the packages directory since we depend on local packages
COPY packages/ /packages/
COPY market-spine-basic/pyproject.toml market-spine-basic/uv.lock market-spine-basic/README.md ./

# Update pyproject.toml to use absolute paths for packages
# This is needed because Docker context doesn't preserve relative paths the same way
RUN sed -i 's|../packages/|/packages/|g' pyproject.toml

# Install dependencies (production only)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY market-spine-basic/src/ ./src/
COPY market-spine-basic/migrations/ ./migrations/

# Build schema from modules (if needed)
COPY scripts/build_schema.py /scripts/
RUN python /scripts/build_schema.py || echo "Schema already generated"

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


# =============================================================================
# Stage 2: Production runtime
# =============================================================================
FROM python:3.12-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd --gid 1000 spine && \
    useradd --uid 1000 --gid 1000 --shell /bin/bash --create-home spine

# Copy virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application files
COPY --from=builder /app/src /app/src
COPY --from=builder /app/migrations /app/migrations

# Copy entrypoint script
COPY market-spine-basic/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Copy packages (needed for imports)
COPY --from=builder /packages /packages

# Create data and database directories
RUN mkdir -p /app/data /app/db && \
    chown -R spine:spine /app

# Switch to non-root user
USER spine

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV SPINE_DATABASE_PATH="/app/db/spine.db"
ENV SPINE_DATA_DIR="/app/data"
ENV SPINE_LOG_FORMAT="json"
ENV PYTHONUNBUFFERED=1

# Expose volume mounts
VOLUME ["/app/data", "/app/db"]

# Set entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sqlite3; sqlite3.connect('/app/db/spine.db').execute('SELECT 1')" || exit 1

# Default command: run API server
CMD ["uvicorn", "market_spine.api.app:app", "--host", "0.0.0.0", "--port", "8000"]


# =============================================================================
# Usage:
# =============================================================================
#
# Build from spine-core root:
#   docker build -t market-spine-basic -f market-spine-basic/Dockerfile .
#
# Run with persistent volumes:
#   docker run -v spine-data:/app/data -v spine-db:/app/db market-spine-basic
#
# Run a pipeline:
#   docker run -v spine-data:/app/data -v spine-db:/app/db \
#     market-spine-basic spine run otc.ingest_week \
#       -p week_ending=2025-12-26 \
#       -p tier=NMS_TIER_1 \
#       -p file_path=/app/data/finra/nms_tier1_2025-12-26.psv
#
# Interactive shell:
#   docker run -it -v spine-data:/app/data -v spine-db:/app/db \
#     market-spine-basic spine shell
