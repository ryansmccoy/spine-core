# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install uv
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install dependencies
RUN uv pip install --system -e .

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/spine /usr/local/bin/spine

# Copy application code
COPY src/ src/
COPY data/ data/

# Create non-root user
RUN useradd --create-home --shell /bin/bash spine && \
    chown -R spine:spine /app

USER spine

# Default command
CMD ["spine", "serve"]
