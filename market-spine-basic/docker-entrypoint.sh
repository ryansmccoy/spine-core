#!/bin/sh
# Docker entrypoint script for Market Spine Basic
# Ensures database is initialized before starting the service

set -e

# Initialize database (idempotent - safe to run multiple times)
echo "Initializing database..."
spine db init

# Execute the main command (passed as arguments)
exec "$@"
