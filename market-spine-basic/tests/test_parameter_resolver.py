"""Tests for the ParameterResolver service."""

from datetime import date, timedelta

import pytest

from market_spine.app.services.params import ParameterResolver
from market_spine.app.services.tier import TierNormalizer


class TestParameterResolver:
    """Test suite for ParameterResolver."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.resolver = ParameterResolver()

    # =========================================================================
    # resolve() tests
    # =========================================================================

    def test_resolve_passes_through_params(self) -> None:
        """Parameters should pass through to result."""
        result = self.resolver.resolve(
            raw_params={"key": "value", "count": 42},
        )
        assert result["key"] == "value"
        assert result["count"] == 42

    def test_resolve_normalizes_tier(self) -> None:
        """Tier parameters should be normalized."""
        result = self.resolver.resolve(
            raw_params={"tier": "tier1"},
        )
        assert result["tier"] == "NMS_TIER_1"

    def test_resolve_tier_alias_variants(self) -> None:
        """Various tier aliases should normalize correctly."""
        assert self.resolver.resolve({"tier": "otc"})["tier"] == "OTC"
        assert self.resolver.resolve({"tier": "Tier1"})["tier"] == "NMS_TIER_1"
        assert self.resolver.resolve({"tier": "tier2"})["tier"] == "NMS_TIER_2"

    def test_resolve_invalid_tier_raises(self) -> None:
        """Invalid tier values should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            self.resolver.resolve({"tier": "invalid"})

    def test_resolve_preserves_non_tier_params(self) -> None:
        """Non-tier parameters should be preserved unchanged."""
        result = self.resolver.resolve(
            raw_params={
                "tier": "tier1",
                "week_ending": "2025-01-10",
                "file_path": "/data/file.txt",
            },
        )
        assert result["tier"] == "NMS_TIER_1"
        assert result["week_ending"] == "2025-01-10"
        assert result["file_path"] == "/data/file.txt"

    # =========================================================================
    # validate_date() tests
    # =========================================================================

    def test_validate_date_valid_format(self) -> None:
        """Valid date strings should pass validation."""
        assert self.resolver.validate_date("2025-01-10") is True
        assert self.resolver.validate_date("2024-12-31") is True
        assert self.resolver.validate_date("2025-02-28") is True

    def test_validate_date_invalid_format(self) -> None:
        """Invalid date formats should fail validation."""
        assert self.resolver.validate_date("01-10-2025") is False  # Wrong order
        assert self.resolver.validate_date("2025/01/10") is False  # Wrong separator
        assert self.resolver.validate_date("not-a-date") is False
        assert self.resolver.validate_date("") is False

    def test_validate_date_invalid_dates(self) -> None:
        """Invalid dates (correct format) should fail validation."""
        assert self.resolver.validate_date("2025-02-30") is False  # Feb 30
        assert self.resolver.validate_date("2025-13-01") is False  # Month 13
        assert self.resolver.validate_date("2025-00-01") is False  # Month 0

    # =========================================================================
    # validate_required() tests
    # =========================================================================

    def test_validate_required_all_present(self) -> None:
        """All required params present should return empty list."""
        missing = self.resolver.validate_required(
            params={"tier": "OTC", "week_ending": "2025-01-10"},
            required=["tier", "week_ending"],
        )
        assert missing == []

    def test_validate_required_some_missing(self) -> None:
        """Missing required params should be returned."""
        missing = self.resolver.validate_required(
            params={"tier": "OTC"},
            required=["tier", "week_ending", "file_path"],
        )
        assert "week_ending" in missing
        assert "file_path" in missing
        assert "tier" not in missing

    def test_validate_required_none_present(self) -> None:
        """All missing should return all required."""
        missing = self.resolver.validate_required(
            params={},
            required=["a", "b", "c"],
        )
        assert set(missing) == {"a", "b", "c"}

    def test_validate_required_no_requirements(self) -> None:
        """No required params should always pass."""
        missing = self.resolver.validate_required(params={}, required=[])
        assert missing == []


class TestParameterResolverWithCustomNormalizer:
    """Test ParameterResolver with injected dependencies."""

    def test_custom_tier_normalizer(self) -> None:
        """Custom tier normalizer should be used."""
        normalizer = TierNormalizer()
        resolver = ParameterResolver(tier_normalizer=normalizer)

        result = resolver.resolve({"tier": "tier1"})
        assert result["tier"] == "NMS_TIER_1"
