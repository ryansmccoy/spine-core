# Market Spine Advanced
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY README.md .
COPY src/ src/
COPY migrations/ migrations/

# Install dependencies
RUN uv pip install --system -e .

# Create data directory
RUN mkdir -p /app/data

# Set Python path
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "-m", "market_spine.cli", "serve"]
