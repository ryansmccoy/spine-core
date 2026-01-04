"""
Parameter resolution service.

Resolves and validates pipeline parameters, applying normalization rules.
This is the command-layer service that transforms raw CLI/API parameters
into canonical form for the framework.

Separation of Concerns:
    ParamParser (CLI layer):       Parse & merge CLI inputs → raw dict
    ParameterResolver (this module): Normalize & validate → canonical dict

This service handles:
- Normalizing tier values (tier1 → NMS_TIER_1)
- Validating date formats
- Checking required parameters
"""

from datetime import datetime
from typing import Any

from market_spine.app.services.tier import TierNormalizer


class ParameterResolver:
    """
    Resolve and validate pipeline parameters.

    This service merges parameters from multiple sources and applies
    normalization rules. It is used by both CLI and API to ensure
    consistent parameter handling.

    Example:
        resolver = ParameterResolver()
        params = resolver.resolve(
            raw_params={"tier": "tier1", "week_ending": "2025-12-19"},
        )
        # Returns {"tier": "NMS_TIER_1", "week_ending": "2025-12-19"}
    """

    def __init__(self, tier_normalizer: TierNormalizer | None = None) -> None:
        """Initialize with optional tier normalizer."""
        self._tier_normalizer = tier_normalizer or TierNormalizer()

    def resolve(
        self,
        raw_params: dict[str, Any],
        normalize_tier: bool = True,
    ) -> dict[str, Any]:
        """
        Resolve parameters by applying normalization rules.

        Args:
            raw_params: Raw parameter dictionary
            normalize_tier: Whether to normalize tier values (default True)

        Returns:
            Resolved parameter dictionary

        Raises:
            ValueError: If tier normalization fails
        """
        resolved = dict(raw_params)

        # Normalize tier if present and requested
        if normalize_tier and "tier" in resolved and resolved["tier"] is not None:
            resolved["tier"] = self._tier_normalizer.normalize(resolved["tier"])

        return resolved

    @staticmethod
    def validate_date(date_str: str) -> bool:
        """
        Validate that a string is a valid YYYY-MM-DD date.

        Args:
            date_str: Date string to validate

        Returns:
            True if valid, False otherwise
        """
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    @staticmethod
    def validate_required(
        params: dict[str, Any],
        required: list[str],
    ) -> list[str]:
        """
        Check for missing required parameters.

        Args:
            params: Parameter dictionary
            required: List of required parameter names

        Returns:
            List of missing parameter names (empty if all present)
        """
        missing = []
        for name in required:
            if name not in params or params[name] is None:
                missing.append(name)
        return missing
