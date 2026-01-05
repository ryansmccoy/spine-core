"""
Capabilities discovery endpoint.

Allows clients to discover what features are available in the current
API tier without hard-coding tier detection logic.

This endpoint is AUTHORITATIVE for feature detection. Clients should:
1. Call /v1/capabilities on startup
2. Cache the response for the session
3. Use feature flags to enable/disable functionality
4. NOT assume capabilities based on version or tier name

Contract Guarantees (v1):
- All fields listed in CapabilitiesResponse are GUARANTEED
- New fields may be added (forward-compatible)
- Existing boolean fields will not change type
- Existing boolean fields set to False may become True in higher tiers
"""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from market_spine import __version__


class CapabilitiesResponse(BaseModel):
    """
    Tier capabilities for API introspection.

    Clients should use this endpoint to discover available features
    rather than assuming capabilities based on version or tier name.

    All fields are guaranteed to exist. Clients may safely access
    any field without None-checking for boolean flags.
    """

    # API identification
    api_version: str = Field(
        description="API version string (e.g., 'v1'). Use for contract compatibility."
    )
    tier: str = Field(description="Tier name: 'basic', 'intermediate', or 'full'")
    version: str = Field(
        description="Package version (semver). Use for debugging, not feature detection."
    )

    # Execution capabilities
    sync_execution: bool = Field(description="Synchronous blocking execution is supported")
    async_execution: bool = Field(description="Asynchronous non-blocking execution is supported")
    execution_history: bool = Field(description="Historical execution records can be queried")

    # Security & operational capabilities
    authentication: bool = Field(description="API authentication is required/supported")
    scheduling: bool = Field(description="Scheduled/cron-based execution is supported")
    rate_limiting: bool = Field(description="Request rate limiting is enforced")
    webhook_notifications: bool = Field(
        description="Webhook callbacks for execution events are supported"
    )


router = APIRouter(tags=["Discovery"])


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def get_capabilities() -> CapabilitiesResponse:
    """
    Discover API capabilities.

    Returns the tier name and feature flags for all capabilities.
    Clients should use this to adapt their behavior based on
    available features.

    This endpoint is the AUTHORITATIVE source for feature detection.
    Do not hard-code capability assumptions based on tier name.

    Basic tier capabilities:
    - Synchronous execution only
    - No authentication, scheduling, or rate limiting
    - No execution history or webhooks
    """
    return CapabilitiesResponse(
        api_version="v1",
        tier="basic",
        version=__version__,
        sync_execution=True,
        async_execution=False,
        execution_history=False,
        authentication=False,
        scheduling=False,
        rate_limiting=False,
        webhook_notifications=False,
    )
