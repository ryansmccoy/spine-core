"""
Tier normalization service.

Normalizes user-friendly tier aliases (tier1, Tier2, OTC) to
canonical database values (NMS_TIER_1, NMS_TIER_2, OTC).

This service imports tier constants from spine.domains, ensuring
a single source of truth for tier definitions.
"""

from spine.domains.finra.otc_transparency.schema import (
    TIER_ALIASES,
    TIER_VALUES,
    Tier,
)


class TierNormalizer:
    """
    Normalize tier strings to canonical values.

    This service provides tier normalization for both CLI and API.
    It is stateless and can be instantiated without dependencies.

    Example:
        normalizer = TierNormalizer()
        tier = normalizer.normalize("tier1")  # Returns "NMS_TIER_1"
        tier = normalizer.normalize("OTC")    # Returns "OTC"
    """

    def __init__(self) -> None:
        """Initialize with tier aliases from domain schema."""
        self._aliases = TIER_ALIASES
        self._valid_values = TIER_VALUES

    @property
    def valid_values(self) -> list[str]:
        """Get list of valid canonical tier values."""
        return list(self._valid_values)

    def get_valid_values(self) -> list[str]:
        """
        Get list of valid canonical tier values.

        This method is preferred over the property for use in commands,
        as it makes the delegation pattern explicit.

        Returns:
            List of canonical tier values (e.g., ["OTC", "NMS_TIER_1", "NMS_TIER_2"])
        """
        return list(self._valid_values)

    def normalize(self, tier: str | None) -> str | None:
        """
        Normalize a tier string to its canonical value.

        Args:
            tier: User-provided tier string (e.g., "tier1", "OTC")

        Returns:
            Canonical tier value (e.g., "NMS_TIER_1") or None if input is None

        Raises:
            ValueError: If tier is not a recognized value or alias
        """
        if tier is None:
            return None

        canonical = self._aliases.get(tier)
        if canonical is None:
            # Check if it's already a canonical value (case-insensitive)
            upper = tier.upper()
            if upper in self._valid_values:
                return upper
            valid = ", ".join(self._valid_values)
            raise ValueError(f"Invalid tier: '{tier}'. Valid values: {valid}")

        return canonical

    def normalize_or_none(self, tier: str | None) -> str | None:
        """
        Normalize a tier string, returning None on invalid input.

        Unlike normalize(), this does not raise on invalid input.
        Useful when validation happens elsewhere.
        """
        if tier is None:
            return None
        return self._aliases.get(tier, tier.upper() if tier.upper() in self._valid_values else None)

    def is_valid(self, tier: str | None) -> bool:
        """Check if a tier string is valid (alias or canonical)."""
        if tier is None:
            return False
        if tier in self._aliases:
            return True
        return tier.upper() in self._valid_values

    def to_enum(self, tier: str) -> Tier:
        """
        Convert tier string to Tier enum.

        Args:
            tier: User-provided tier string

        Returns:
            Tier enum value

        Raises:
            ValueError: If tier is not valid
        """
        canonical = self.normalize(tier)
        if canonical is None:
            raise ValueError("Tier cannot be None")
        return Tier(canonical)
