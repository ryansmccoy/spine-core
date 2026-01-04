"""
REST API module for Market Spine.

This module provides a FastAPI-based REST API for pipeline operations.
The Basic tier provides a simple, synchronous API with core operations.

Entry Points:
    - app: The FastAPI application instance
    - create_app(): Factory function for testing/configuration

Tier Capabilities (Basic):
    - Synchronous execution only
    - No authentication
    - No rate limiting
    - No execution history
"""

from market_spine.api.app import app, create_app

__all__ = ["app", "create_app"]
