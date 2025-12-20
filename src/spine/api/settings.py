"""
API-specific settings.

Extends :class:`~spine.core.settings.SpineBaseSettings` with parameters
that govern the REST transport (CORS, rate-limiting, auth, prefix).

All values can be overridden via environment variables prefixed with
``SPINE_`` (inherited) or ``SPINE_API_`` for API-specific knobs.
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic_settings import BaseSettings
except ImportError:  # pragma: no cover
    from pydantic import BaseModel as BaseSettings  # type: ignore[assignment]

from pydantic import Field


class SpineCoreAPISettings(BaseSettings):
    """Settings for the spine-core REST API.

    Order of precedence (highest → lowest):
        1. Environment variables (``SPINE_API_PREFIX``, etc.)
        2. ``.env`` file
        3. Defaults below
    """

    # ── Server ───────────────────────────────────────────────────────────
    host: str = Field(default="0.0.0.0", description="Bind address")
    port: int = Field(default=12000, description="Bind port (ecosystem convention)")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Log level")

    # ── API ──────────────────────────────────────────────────────────────
    api_prefix: str = Field(default="/api/v1", description="URL prefix for all endpoints")
    api_title: str = Field(default="spine-core API", description="OpenAPI title")
    api_version: str = Field(default="0.3.0", description="OpenAPI version string")

    # ── Database ─────────────────────────────────────────────────────────
    database_url: str = Field(
        default="sqlite:///spine_core.db",
        description="SQLAlchemy-style connection URL",
    )
    data_dir: str = Field(default="~/.spine", description="Data directory for file-based stores")

    # ── CORS ─────────────────────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["*"],
        description="Allowed CORS origins",
    )

    # ── Rate limiting ────────────────────────────────────────────────────
    rate_limit_enabled: bool = Field(default=False, description="Enable rate limiting")
    rate_limit_rpm: int = Field(default=120, description="Requests per minute")

    # ── Auth ─────────────────────────────────────────────────────────────
    api_key: str | None = Field(default=None, description="Optional API key for gating access")

    model_config: dict[str, Any] = {
        "env_prefix": "SPINE_",
        "env_file": ".env",
        "extra": "ignore",
        "env_nested_delimiter": "__",
    }
