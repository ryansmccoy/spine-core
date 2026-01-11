"""
Domain plugins for Market Spine.

Each domain is a self-contained plugin that provides:
- models.py: Domain-specific data models
- pipelines.py: Pipeline definitions with @register_pipeline decorator
- repository.py: Data access layer (async for PostgreSQL)
- Optional: connector.py, routes.py, quality.py

Domains are auto-discovered by the registry.
"""
