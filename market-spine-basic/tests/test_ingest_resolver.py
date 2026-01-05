"""Tests for the IngestResolver service."""


from market_spine.app.services.ingest import IngestResolver


class TestIngestResolver:
    """Test suite for IngestResolver."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.resolver = IngestResolver()

    # =========================================================================
    # is_ingest_pipeline() tests
    # =========================================================================

    def test_is_ingest_pipeline_true(self) -> None:
        """Ingest pipeline names should be detected."""
        assert self.resolver.is_ingest_pipeline("finra.otc_transparency.ingest_file") is True
        assert self.resolver.is_ingest_pipeline("finra.otc_transparency.ingest") is True
        assert self.resolver.is_ingest_pipeline("some.ingest_data") is True

    def test_is_ingest_pipeline_false(self) -> None:
        """Non-ingest pipeline names should return False."""
        assert self.resolver.is_ingest_pipeline("finra.otc_transparency.normalize_week") is False
        assert self.resolver.is_ingest_pipeline("finra.otc_transparency.aggregate") is False
        assert self.resolver.is_ingest_pipeline("process_data") is False

    # =========================================================================
    # resolve() with explicit file_path
    # =========================================================================

    def test_resolve_explicit_file_path(self) -> None:
        """Explicit file_path should be used directly."""
        result = self.resolver.resolve(
            pipeline="finra.otc_transparency.ingest_file",
            params={
                "tier": "NMS_TIER_1",
                "week_ending": "2025-01-10",
                "file_path": "/custom/path/data.txt",
            },
        )

        assert result is not None
        assert result.source_type == "explicit"
        assert result.file_path == "/custom/path/data.txt"
        assert result.derivation_logic is None

    # =========================================================================
    # resolve() with derived file_path
    # =========================================================================

    def test_resolve_derived_otc(self) -> None:
        """OTC tier should derive to 'otc' filename."""
        result = self.resolver.resolve(
            pipeline="finra.otc_transparency.ingest_file",
            params={
                "tier": "OTC",
                "week_ending": "2025-01-10",
            },
        )

        assert result is not None
        assert result.source_type == "derived"
        assert "otc" in result.file_path.lower()
        # Date is formatted as YYYYMMDD (no hyphens) in file path
        assert "20250110" in result.file_path
        assert result.derivation_logic is not None

    def test_resolve_derived_tier1(self) -> None:
        """NMS_TIER_1 should derive to 'tier1' filename."""
        result = self.resolver.resolve(
            pipeline="finra.otc_transparency.ingest_file",
            params={
                "tier": "NMS_TIER_1",
                "week_ending": "2025-01-10",
            },
        )

        assert result is not None
        assert result.source_type == "derived"
        assert "tier1" in result.file_path.lower()

    def test_resolve_derived_tier2(self) -> None:
        """NMS_TIER_2 should derive to 'tier2' filename."""
        result = self.resolver.resolve(
            pipeline="finra.otc_transparency.ingest_file",
            params={
                "tier": "NMS_TIER_2",
                "week_ending": "2025-01-10",
            },
        )

        assert result is not None
        assert result.source_type == "derived"
        assert "tier2" in result.file_path.lower()

    # =========================================================================
    # resolve() for non-ingest pipelines
    # =========================================================================

    def test_resolve_non_ingest_returns_none(self) -> None:
        """Non-ingest pipelines should return None."""
        result = self.resolver.resolve(
            pipeline="finra.otc_transparency.normalize_week",
            params={"tier": "OTC", "week_ending": "2025-01-10"},
        )
        assert result is None

    # =========================================================================
    # derive_file_path_preview() tests
    # =========================================================================

    def test_derive_file_path_preview(self) -> None:
        """Preview should show derived path without checking existence."""
        preview = self.resolver.derive_file_path_preview(
            tier="NMS_TIER_1",
            week_ending="2025-01-10",
        )

        assert preview is not None
        assert "tier1" in preview.lower()
        # Date is formatted as YYYYMMDD (no hyphens) in file path
        assert "20250110" in preview

    def test_derive_file_path_preview_normalizes_tier(self) -> None:
        """Preview should normalize tier aliases."""
        preview = self.resolver.derive_file_path_preview(
            tier="tier1",  # Alias
            week_ending="2025-01-10",
        )

        assert preview is not None
        assert "tier1" in preview.lower()


class TestIngestResolverFilePathDerivation:
    """Test IngestResolver file path derivation edge cases."""

    def test_derive_respects_tier_mapping(self) -> None:
        """TIER_FILE_MAP should be used for tier to filename conversion."""
        resolver = IngestResolver()

        # Check the tier mapping is applied correctly
        result = resolver.resolve(
            pipeline="ingest_file",
            params={"tier": "NMS_TIER_1", "week_ending": "2025-01-10"},
        )

        assert result is not None
        assert "tier1" in result.file_path.lower()
