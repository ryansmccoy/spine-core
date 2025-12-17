"""
Tests for spine.core.assets module.

Tests cover:
- AssetKey creation, validation, parsing, prefix matching
- FreshnessPolicy staleness detection
- AssetMaterialization creation, serialization, deserialization
- AssetObservation creation, serialization, deserialization
- AssetDefinition metadata
- AssetRegistry CRUD, queries, groups, namespaces, dependencies
- Global registry singleton management
- register_asset convenience function
"""

import pytest
from datetime import UTC, datetime, timedelta

from spine.core.assets import (
    AssetDefinition,
    AssetKey,
    AssetMaterialization,
    AssetObservation,
    AssetRegistry,
    FreshnessPolicy,
    MaterializationStatus,
    get_asset_registry,
    register_asset,
    reset_asset_registry,
)


# =============================================================================
# Helpers
# =============================================================================


def _ts(offset_hours: int = 0) -> datetime:
    """Create a UTC datetime offset from a fixed base time."""
    base = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)
    return base + timedelta(hours=offset_hours)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Reset the global registry before each test."""
    reset_asset_registry()
    yield
    reset_asset_registry()


# =============================================================================
# AssetKey
# =============================================================================


class TestAssetKey:
    """Tests for AssetKey creation and operations."""

    def test_basic_creation(self):
        key = AssetKey("sec", "filings", "10-K")
        assert key.path == ("sec", "filings", "10-K")

    def test_single_component(self):
        key = AssetKey("data")
        assert key.path == ("data",)

    def test_str_representation(self):
        key = AssetKey("sec", "filings", "10-K")
        assert str(key) == "sec/filings/10-K"

    def test_repr(self):
        key = AssetKey("sec", "filings")
        assert repr(key) == "AssetKey('sec', 'filings')"

    def test_namespace(self):
        key = AssetKey("sec", "filings", "10-K")
        assert key.namespace == "sec"

    def test_name(self):
        key = AssetKey("sec", "filings", "10-K")
        assert key.name == "10-K"

    def test_single_component_namespace_equals_name(self):
        key = AssetKey("data")
        assert key.namespace == "data"
        assert key.name == "data"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="at least one"):
            AssetKey()

    def test_empty_string_part_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            AssetKey("sec", "", "10-K")

    def test_whitespace_only_part_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            AssetKey("sec", "   ")

    def test_none_part_raises(self):
        with pytest.raises(ValueError):
            AssetKey("sec", None)  # type: ignore

    def test_frozen(self):
        key = AssetKey("sec", "filings")
        with pytest.raises(AttributeError):
            key.path = ("other",)  # type: ignore

    def test_equality(self):
        a = AssetKey("sec", "filings", "10-K")
        b = AssetKey("sec", "filings", "10-K")
        assert a == b

    def test_inequality(self):
        a = AssetKey("sec", "filings", "10-K")
        b = AssetKey("sec", "filings", "10-Q")
        assert a != b

    def test_hashable(self):
        a = AssetKey("sec", "filings", "10-K")
        b = AssetKey("sec", "filings", "10-K")
        assert hash(a) == hash(b)
        s = {a, b}
        assert len(s) == 1

    def test_is_prefix_of(self):
        prefix = AssetKey("sec")
        child = AssetKey("sec", "filings", "10-K")
        assert prefix.is_prefix_of(child)

    def test_is_not_prefix_of(self):
        a = AssetKey("sec", "filings")
        b = AssetKey("sec")
        assert not a.is_prefix_of(b)

    def test_is_prefix_of_self(self):
        key = AssetKey("sec", "filings")
        assert key.is_prefix_of(key)

    def test_from_string(self):
        key = AssetKey.from_string("sec/filings/10-K")
        assert key.path == ("sec", "filings", "10-K")

    def test_from_string_strips_slashes(self):
        key = AssetKey.from_string("/sec/filings/")
        assert key.path == ("sec", "filings")

    def test_roundtrip_dict(self):
        key = AssetKey("sec", "filings", "10-K")
        data = key.to_dict()
        restored = AssetKey.from_dict(data)
        assert restored == key

    def test_used_as_dict_key(self):
        key = AssetKey("sec", "filings", "10-K")
        d = {key: "value"}
        assert d[AssetKey("sec", "filings", "10-K")] == "value"


# =============================================================================
# FreshnessPolicy
# =============================================================================


class TestFreshnessPolicy:
    """Tests for FreshnessPolicy staleness detection."""

    def test_stale_when_never_materialized(self):
        policy = FreshnessPolicy(max_lag_seconds=3600)
        assert policy.is_stale(None) is True

    def test_not_stale_when_recent(self):
        policy = FreshnessPolicy(max_lag_seconds=3600)
        recent = datetime.now(UTC) - timedelta(seconds=60)
        assert policy.is_stale(recent) is False

    def test_stale_when_old(self):
        policy = FreshnessPolicy(max_lag_seconds=3600)
        old = datetime.now(UTC) - timedelta(hours=2)
        assert policy.is_stale(old) is True

    def test_boundary_stale(self):
        policy = FreshnessPolicy(max_lag_seconds=3600)
        just_past = datetime.now(UTC) - timedelta(seconds=3601)
        assert policy.is_stale(just_past) is True

    def test_with_cron_schedule(self):
        policy = FreshnessPolicy(max_lag_seconds=86400, cron_schedule="0 2 * * *")
        assert policy.cron_schedule == "0 2 * * *"

    def test_frozen(self):
        policy = FreshnessPolicy(max_lag_seconds=3600)
        with pytest.raises(AttributeError):
            policy.max_lag_seconds = 7200  # type: ignore


# =============================================================================
# AssetMaterialization
# =============================================================================


class TestAssetMaterialization:
    """Tests for AssetMaterialization creation and serialization."""

    def test_basic_creation(self):
        key = AssetKey("sec", "filings", "10-K")
        mat = AssetMaterialization(asset_key=key)
        assert mat.asset_key == key
        assert mat.status == MaterializationStatus.SUCCESS
        assert mat.id  # UUID assigned
        assert mat.timestamp  # UTC assigned
        assert mat.metadata == {}
        assert mat.tags == {}

    def test_with_metadata(self):
        mat = AssetMaterialization(
            asset_key=AssetKey("sec", "filings", "10-K"),
            partition="CIK:0001318605",
            metadata={"count": 42, "source": "EDGAR"},
            execution_id="exec-123",
        )
        assert mat.partition == "CIK:0001318605"
        assert mat.metadata["count"] == 42
        assert mat.execution_id == "exec-123"

    def test_with_upstream_keys(self):
        upstream = (AssetKey("sec", "index"),)
        mat = AssetMaterialization(
            asset_key=AssetKey("sec", "filings", "10-K"),
            upstream_keys=upstream,
        )
        assert mat.upstream_keys == upstream

    def test_partial_status(self):
        mat = AssetMaterialization(
            asset_key=AssetKey("sec", "filings"),
            status=MaterializationStatus.PARTIAL,
        )
        assert mat.status == MaterializationStatus.PARTIAL

    def test_frozen(self):
        mat = AssetMaterialization(asset_key=AssetKey("data"))
        with pytest.raises(AttributeError):
            mat.status = MaterializationStatus.FAILED  # type: ignore

    def test_roundtrip_dict(self):
        mat = AssetMaterialization(
            asset_key=AssetKey("sec", "filings", "10-K"),
            partition="CIK:0001318605",
            metadata={"count": 42},
            execution_id="exec-123",
            status=MaterializationStatus.SUCCESS,
            tags={"env": "prod"},
            upstream_keys=(AssetKey("sec", "index"),),
        )
        data = mat.to_dict()
        restored = AssetMaterialization.from_dict(data)
        assert restored.asset_key == mat.asset_key
        assert restored.partition == mat.partition
        assert restored.metadata == mat.metadata
        assert restored.execution_id == mat.execution_id
        assert restored.status == mat.status
        assert restored.tags == mat.tags
        assert restored.upstream_keys == mat.upstream_keys

    def test_to_dict_format(self):
        mat = AssetMaterialization(
            asset_key=AssetKey("sec", "filings"),
            partition="date:2025-01-15",
        )
        d = mat.to_dict()
        assert d["asset_key"] == "sec/filings"
        assert d["partition"] == "date:2025-01-15"
        assert d["status"] == "success"
        assert "timestamp" in d


# =============================================================================
# AssetObservation
# =============================================================================


class TestAssetObservation:
    """Tests for AssetObservation creation and serialization."""

    def test_basic_creation(self):
        obs = AssetObservation(asset_key=AssetKey("sec", "filings"))
        assert obs.asset_key == AssetKey("sec", "filings")
        assert obs.id
        assert obs.timestamp

    def test_with_metadata(self):
        obs = AssetObservation(
            asset_key=AssetKey("sec", "filings", "10-K"),
            partition="CIK:0001318605",
            metadata={"row_count": 42, "freshness_lag_hours": 2.5},
            execution_id="exec-456",
        )
        assert obs.metadata["row_count"] == 42
        assert obs.partition == "CIK:0001318605"

    def test_frozen(self):
        obs = AssetObservation(asset_key=AssetKey("data"))
        with pytest.raises(AttributeError):
            obs.partition = "new"  # type: ignore

    def test_roundtrip_dict(self):
        obs = AssetObservation(
            asset_key=AssetKey("sec", "filings"),
            partition="date:2025-01-15",
            metadata={"rows": 100},
            execution_id="exec-789",
        )
        data = obs.to_dict()
        restored = AssetObservation.from_dict(data)
        assert restored.asset_key == obs.asset_key
        assert restored.partition == obs.partition
        assert restored.metadata == obs.metadata
        assert restored.execution_id == obs.execution_id


# =============================================================================
# AssetRegistry
# =============================================================================


class TestAssetRegistry:
    """Tests for AssetRegistry CRUD and queries."""

    def test_register_and_get(self):
        registry = AssetRegistry()
        defn = AssetDefinition(
            key=AssetKey("sec", "filings", "10-K"),
            description="SEC 10-K annual filings",
        )
        registry.register(defn)
        assert registry.get(AssetKey("sec", "filings", "10-K")) == defn

    def test_get_missing_returns_none(self):
        registry = AssetRegistry()
        assert registry.get(AssetKey("nonexistent")) is None

    def test_duplicate_registration_raises(self):
        registry = AssetRegistry()
        key = AssetKey("sec", "filings")
        registry.register(AssetDefinition(key=key))
        with pytest.raises(ValueError, match="already registered"):
            registry.register(AssetDefinition(key=key))

    def test_list_all(self):
        registry = AssetRegistry()
        registry.register(AssetDefinition(key=AssetKey("a")))
        registry.register(AssetDefinition(key=AssetKey("b")))
        registry.register(AssetDefinition(key=AssetKey("c")))
        assert len(registry.list_all()) == 3

    def test_by_group(self):
        registry = AssetRegistry()
        registry.register(AssetDefinition(key=AssetKey("a"), group="sec"))
        registry.register(AssetDefinition(key=AssetKey("b"), group="sec"))
        registry.register(AssetDefinition(key=AssetKey("c"), group="portfolio"))
        assert len(registry.by_group("sec")) == 2
        assert len(registry.by_group("portfolio")) == 1
        assert len(registry.by_group("nonexistent")) == 0

    def test_by_namespace(self):
        registry = AssetRegistry()
        registry.register(AssetDefinition(key=AssetKey("sec", "filings", "10-K")))
        registry.register(AssetDefinition(key=AssetKey("sec", "index")))
        registry.register(AssetDefinition(key=AssetKey("portfolio", "positions")))
        assert len(registry.by_namespace("sec")) == 2
        assert len(registry.by_namespace("portfolio")) == 1

    def test_by_pipeline(self):
        registry = AssetRegistry()
        registry.register(AssetDefinition(
            key=AssetKey("a"), producing_pipeline="ingest_filings",
        ))
        registry.register(AssetDefinition(
            key=AssetKey("b"), producing_pipeline="ingest_filings",
        ))
        registry.register(AssetDefinition(
            key=AssetKey("c"), producing_pipeline="compute_metrics",
        ))
        assert len(registry.by_pipeline("ingest_filings")) == 2
        assert len(registry.by_pipeline("compute_metrics")) == 1

    def test_dependents_of(self):
        registry = AssetRegistry()
        source = AssetKey("sec", "index")
        registry.register(AssetDefinition(key=source))
        registry.register(AssetDefinition(
            key=AssetKey("sec", "filings"), dependencies=(source,),
        ))
        registry.register(AssetDefinition(
            key=AssetKey("portfolio", "nav"),
        ))
        dependents = registry.dependents_of(source)
        assert len(dependents) == 1
        assert dependents[0].key == AssetKey("sec", "filings")

    def test_contains(self):
        registry = AssetRegistry()
        key = AssetKey("sec", "filings")
        assert key not in registry
        registry.register(AssetDefinition(key=key))
        assert key in registry

    def test_len(self):
        registry = AssetRegistry()
        assert len(registry) == 0
        registry.register(AssetDefinition(key=AssetKey("a")))
        assert len(registry) == 1

    def test_clear(self):
        registry = AssetRegistry()
        registry.register(AssetDefinition(key=AssetKey("a")))
        registry.register(AssetDefinition(key=AssetKey("b")))
        registry.clear()
        assert len(registry) == 0


# =============================================================================
# Global Registry
# =============================================================================


class TestGlobalRegistry:
    """Tests for global registry singleton management."""

    def test_get_creates_singleton(self):
        reg1 = get_asset_registry()
        reg2 = get_asset_registry()
        assert reg1 is reg2

    def test_reset_clears_singleton(self):
        reg1 = get_asset_registry()
        reg1.register(AssetDefinition(key=AssetKey("test")))
        reset_asset_registry()
        reg2 = get_asset_registry()
        assert reg1 is not reg2
        assert len(reg2) == 0


# =============================================================================
# register_asset convenience function
# =============================================================================


class TestRegisterAsset:
    """Tests for the register_asset() convenience function."""

    def test_basic_registration(self):
        defn = register_asset("sec", "filings", "10-K", description="Annual filings")
        assert defn.key == AssetKey("sec", "filings", "10-K")
        assert defn.description == "Annual filings"
        assert get_asset_registry().get(defn.key) is defn

    def test_with_all_options(self):
        defn = register_asset(
            "sec", "filings", "10-K",
            description="Annual filings",
            producing_pipeline="ingest_filings",
            freshness_policy=FreshnessPolicy(max_lag_seconds=86400),
            group="sec_data",
            tags={"env": "prod"},
            dependencies=(AssetKey("sec", "index"),),
        )
        assert defn.producing_pipeline == "ingest_filings"
        assert defn.freshness_policy is not None
        assert defn.freshness_policy.max_lag_seconds == 86400
        assert defn.group == "sec_data"
        assert defn.tags == {"env": "prod"}
        assert defn.dependencies == (AssetKey("sec", "index"),)

    def test_duplicate_raises(self):
        register_asset("sec", "filings")
        with pytest.raises(ValueError):
            register_asset("sec", "filings")


# =============================================================================
# Integration: AssetKey + Materialization + Observation
# =============================================================================


class TestAssetIntegration:
    """Integration tests combining multiple asset primitives."""

    def test_materialization_links_to_observation(self):
        """Same key can have both materializations and observations."""
        key = AssetKey("sec", "filings", "10-K")

        mat = AssetMaterialization(
            asset_key=key,
            partition="CIK:0001318605",
            metadata={"count": 42},
            execution_id="exec-001",
        )

        obs = AssetObservation(
            asset_key=key,
            partition="CIK:0001318605",
            metadata={"row_count": 42, "freshness": "fresh"},
            execution_id="exec-002",
        )

        assert mat.asset_key == obs.asset_key
        assert mat.partition == obs.partition

    def test_upstream_lineage(self):
        """Materializations track upstream dependencies."""
        index_key = AssetKey("sec", "index")
        filing_key = AssetKey("sec", "filings", "10-K")

        index_mat = AssetMaterialization(
            asset_key=index_key,
            metadata={"entries": 1000},
        )

        filing_mat = AssetMaterialization(
            asset_key=filing_key,
            upstream_keys=(index_key,),
            metadata={"parsed": 42},
        )

        assert index_key in filing_mat.upstream_keys
        assert index_mat.asset_key == index_key

    def test_freshness_with_materialization(self):
        """FreshnessPolicy works with materialization timestamps."""
        policy = FreshnessPolicy(max_lag_seconds=3600)
        key = AssetKey("sec", "filings")

        recent_mat = AssetMaterialization(asset_key=key)
        assert policy.is_stale(recent_mat.timestamp) is False

        old_ts = datetime.now(UTC) - timedelta(hours=2)
        assert policy.is_stale(old_ts) is True

    def test_registry_with_definitions_and_materializations(self):
        """Full workflow: define → register → materialize → observe."""
        # Define
        defn = register_asset(
            "sec", "filings", "10-K",
            description="Annual filings",
            producing_pipeline="ingest_filings",
            freshness_policy=FreshnessPolicy(max_lag_seconds=86400),
            group="sec_data",
        )

        # Materialize
        mat = AssetMaterialization(
            asset_key=defn.key,
            partition="CIK:0001318605",
            metadata={"count": 42},
        )

        # Observe
        obs = AssetObservation(
            asset_key=defn.key,
            partition="CIK:0001318605",
            metadata={"row_count": 42},
        )

        # Registry queries
        registry = get_asset_registry()
        assert registry.get(defn.key) is defn
        assert len(registry.by_namespace("sec")) == 1
        assert mat.asset_key == defn.key
        assert obs.asset_key == defn.key
        assert defn.freshness_policy.is_stale(mat.timestamp) is False
