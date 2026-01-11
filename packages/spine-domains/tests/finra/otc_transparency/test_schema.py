# tests/finra/otc_transparency/test_schema.py

"""Tests for FINRA OTC Transparency schema and constants."""

from spine.domains.finra.otc_transparency.schema import DOMAIN, STAGES, TABLES, Tier


class TestSchema:
    """Tests for FINRA OTC Transparency schema and constants."""

    def test_domain_constant(self):
        """Test that domain identifier is 'finra_otc_transparency'."""
        assert DOMAIN == "finra_otc_transparency"

    def test_stages_defined(self):
        """Test that workflow stages are defined."""
        assert isinstance(STAGES, list)
        assert "INGESTED" in STAGES
        assert "NORMALIZED" in STAGES
        assert "AGGREGATED" in STAGES

    def test_tier_enum(self):
        """Test Tier enum values."""
        assert Tier.NMS_TIER_1.value == "NMS_TIER_1"
        assert Tier.NMS_TIER_2.value == "NMS_TIER_2"
        assert Tier.OTC.value == "OTC"

    def test_tier_from_finra(self):
        """Test parsing FINRA tier strings."""
        assert Tier.from_finra("NMS Tier 1") == Tier.NMS_TIER_1
        assert Tier.from_finra("NMS Tier 2") == Tier.NMS_TIER_2
        assert Tier.from_finra("OTC") == Tier.OTC
        # Invalid defaults to OTC
        assert Tier.from_finra("Unknown") == Tier.OTC

    def test_tables_have_domain_prefix(self):
        """Test that table names use the finra_otc_transparency prefix."""
        for key, table_name in TABLES.items():
            assert table_name.startswith("finra_otc_transparency_"), (
                f"Table '{key}' ({table_name}) should start with 'finra_otc_transparency_'"
            )

    def test_expected_tables_exist(self):
        """Test that expected table keys are defined."""
        expected_keys = ["raw", "venue_volume", "symbol_summary", "rolling"]
        for key in expected_keys:
            assert key in TABLES, f"Expected table key '{key}' not found in TABLES"
