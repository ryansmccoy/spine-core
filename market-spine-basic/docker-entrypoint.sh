#!/bin/sh
# Docker entrypoint script for Market Spine Basic
# Ensures database is initialized before starting the service

set -e

# Initialize database (idempotent - safe to run multiple times)
# Use --force to skip interactive confirmation in container
echo "Initializing database..."
spine db init --force

# Execute the main command (passed as arguments)
exec "$@"
