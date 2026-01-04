"""Tests for the TierNormalizer service."""

import pytest

from market_spine.app.services.tier import TierNormalizer


class TestTierNormalizer:
    """Test suite for TierNormalizer."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.normalizer = TierNormalizer()

    # =========================================================================
    # normalize() tests
    # =========================================================================

    def test_normalize_canonical_values_unchanged(self) -> None:
        """Canonical tier values should pass through unchanged."""
        assert self.normalizer.normalize("OTC") == "OTC"
        assert self.normalizer.normalize("NMS_TIER_1") == "NMS_TIER_1"
        assert self.normalizer.normalize("NMS_TIER_2") == "NMS_TIER_2"

    def test_normalize_lowercase_aliases(self) -> None:
        """Lowercase aliases should normalize correctly."""
        assert self.normalizer.normalize("otc") == "OTC"
        assert self.normalizer.normalize("tier1") == "NMS_TIER_1"
        assert self.normalizer.normalize("tier2") == "NMS_TIER_2"

    def test_normalize_mixed_case_aliases(self) -> None:
        """Mixed case aliases should normalize correctly."""
        # These aliases are defined in TIER_ALIASES
        assert self.normalizer.normalize("Tier1") == "NMS_TIER_1"
        assert self.normalizer.normalize("Tier2") == "NMS_TIER_2"
        assert self.normalizer.normalize("TIER1") == "NMS_TIER_1"
        assert self.normalizer.normalize("TIER2") == "NMS_TIER_2"

    def test_normalize_nms_underscore_variants(self) -> None:
        """NMS underscore variants should normalize correctly."""
        assert self.normalizer.normalize("nms_tier_1") == "NMS_TIER_1"
        assert self.normalizer.normalize("nms_tier_2") == "NMS_TIER_2"

    def test_normalize_invalid_tier_raises(self) -> None:
        """Invalid tier values should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            self.normalizer.normalize("invalid")

        with pytest.raises(ValueError, match="Invalid tier"):
            self.normalizer.normalize("tier3")

        with pytest.raises(ValueError, match="Invalid tier"):
            self.normalizer.normalize("")

    # =========================================================================
    # normalize_or_none() tests
    # =========================================================================

    def test_normalize_or_none_valid(self) -> None:
        """Valid tiers should return normalized value."""
        assert self.normalizer.normalize_or_none("tier1") == "NMS_TIER_1"
        assert self.normalizer.normalize_or_none("OTC") == "OTC"

    def test_normalize_or_none_invalid(self) -> None:
        """Invalid tiers should return None instead of raising."""
        assert self.normalizer.normalize_or_none("invalid") is None
        assert self.normalizer.normalize_or_none("") is None

    # =========================================================================
    # is_valid() tests
    # =========================================================================

    def test_is_valid_canonical(self) -> None:
        """Canonical values should be valid."""
        assert self.normalizer.is_valid("OTC") is True
        assert self.normalizer.is_valid("NMS_TIER_1") is True
        assert self.normalizer.is_valid("NMS_TIER_2") is True

    def test_is_valid_aliases(self) -> None:
        """Aliases should be valid."""
        assert self.normalizer.is_valid("tier1") is True
        assert self.normalizer.is_valid("tier2") is True
        assert self.normalizer.is_valid("otc") is True

    def test_is_valid_invalid(self) -> None:
        """Invalid values should return False."""
        assert self.normalizer.is_valid("invalid") is False
        assert self.normalizer.is_valid("tier3") is False
        assert self.normalizer.is_valid("") is False

    # =========================================================================
    # to_enum() tests
    # =========================================================================

    def test_to_enum_returns_tier_enum(self) -> None:
        """to_enum should return Tier enum values."""
        from spine.domains.finra.otc_transparency.schema import Tier

        assert self.normalizer.to_enum("tier1") == Tier.NMS_TIER_1
        assert self.normalizer.to_enum("OTC") == Tier.OTC
        assert self.normalizer.to_enum("tier2") == Tier.NMS_TIER_2

    def test_to_enum_invalid_raises(self) -> None:
        """to_enum should raise for invalid tiers."""
        with pytest.raises(ValueError):
            self.normalizer.to_enum("invalid")
