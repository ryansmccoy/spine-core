"""
FINRA OTC Transparency domain schema - tables, stages, tiers, and natural keys.

This is the only place that defines FINRA OTC-specific constants.
All other modules in this domain import from here.

SCHEMA OWNERSHIP:
- This domain defines ONLY domain data tables (raw, venue_volume, symbol_summary, etc.)
- Infrastructure tables (manifest, rejects, quality) are in spine.core.schema
- This domain uses core_manifest, core_rejects, core_quality with domain="finra_otc_transparency"
"""

from enum import Enum

# Domain identifier for core infrastructure tables
DOMAIN = "finra_otc_transparency"


class Tier(str, Enum):
    """
    FINRA OTC transparency tier classification.

    NMS_TIER_1: Stocks in S&P 500, Russell 1000, or high volume
    NMS_TIER_2: All other NMS stocks
    OTC: Non-NMS (OTC Markets) stocks
    """

    NMS_TIER_1 = "NMS_TIER_1"
    NMS_TIER_2 = "NMS_TIER_2"
    OTC = "OTC"

    @classmethod
    def from_finra(cls, value: str) -> "Tier":
        """
        Parse tier from FINRA file value.

        FINRA uses strings like "NMS Tier 1" which we normalize.
        """
        normalized = value.strip().upper().replace(" ", "_")
        # Handle FINRA's exact strings
        mappings = {
            "NMS_TIER_1": cls.NMS_TIER_1,
            "NMS_TIER_2": cls.NMS_TIER_2,
            "OTC": cls.OTC,
        }
        return mappings.get(normalized, cls.OTC)

    @classmethod
    def from_alias(cls, value: str) -> "Tier":
        """
        Parse tier from user-friendly alias.

        Accepts case-insensitive aliases like 'tier1', 'Tier1', 'OTC', etc.
        Raises ValueError if the alias is not recognized.
        """
        alias = TIER_ALIASES.get(value)
        if alias is None:
            valid = ", ".join(TIER_VALUES)
            raise ValueError(f"Invalid tier: '{value}'. Valid values: {valid}")
        return cls(alias)


# =============================================================================
# TIER ALIASES (for CLI/API user input)
# =============================================================================

# Canonical tier values (strings, for validation)
TIER_VALUES = ["OTC", "NMS_TIER_1", "NMS_TIER_2"]

# User-friendly aliases that map to canonical tier values
TIER_ALIASES: dict[str, str] = {
    # OTC variants
    "otc": "OTC",
    "OTC": "OTC",
    # NMS Tier 1 variants
    "tier1": "NMS_TIER_1",
    "Tier1": "NMS_TIER_1",
    "TIER1": "NMS_TIER_1",
    "NMS_TIER_1": "NMS_TIER_1",
    "nms_tier_1": "NMS_TIER_1",
    # NMS Tier 2 variants
    "tier2": "NMS_TIER_2",
    "Tier2": "NMS_TIER_2",
    "TIER2": "NMS_TIER_2",
    "NMS_TIER_2": "NMS_TIER_2",
    "nms_tier_2": "NMS_TIER_2",
}


# =============================================================================
# TABLE NAMES (domain data tables only)
# =============================================================================

# Table name prefix for this domain (used in SQLite; maps to schema in Postgres)
TABLE_PREFIX = "finra_otc_transparency"

TABLES = {
    # Domain data tables - use full prefixed names for SQLite compatibility
    "raw": f"{TABLE_PREFIX}_raw",
    "venue_volume": f"{TABLE_PREFIX}_venue_volume",
    "symbol_summary": f"{TABLE_PREFIX}_symbol_summary",
    "venue_share": f"{TABLE_PREFIX}_venue_share",
    "rolling": f"{TABLE_PREFIX}_symbol_rolling_6w",
    "snapshot": f"{TABLE_PREFIX}_research_snapshot",
    "liquidity": f"{TABLE_PREFIX}_liquidity_score",
}


# =============================================================================
# WORKFLOW STAGES
# =============================================================================

STAGES = [
    "PENDING",  # Created, not yet processed
    "INGESTED",  # Raw data loaded
    "NORMALIZED",  # Validated and normalized
    "AGGREGATED",  # Summaries computed
    "ROLLING",  # Rolling metrics computed
    "SNAPSHOT",  # Research snapshot built
]


# =============================================================================
# NATURAL KEY
# =============================================================================

# The logical key for OTC venue volume data
NATURAL_KEY = ["week_ending", "tier", "symbol", "mpid"]

# Manifest key (week + tier) - used as partition_key in core_manifest
MANIFEST_KEY = ["week_ending", "tier"]


# =============================================================================
# PIPELINE NAMES
# =============================================================================

PIPELINES = {
    "ingest": "finra.otc_transparency.ingest_week",
    "normalize": "finra.otc_transparency.normalize_week",
    "aggregate": "finra.otc_transparency.aggregate_week",
    "rolling": "finra.otc_transparency.compute_rolling",
    "snapshot": "finra.otc_transparency.research_snapshot",
    "backfill": "finra.otc_transparency.backfill_range",
    "venue_share": "finra.otc_transparency.compute_venue_share",
}


# =============================================================================
# CALC VERSION REGISTRY
# =============================================================================
# Policy-driven version selection. Use get_current_version() instead of MAX().
#
# CONTRACT (enforced by test_fitness.py):
# ─────────────────────────────────────────────────────────────────────────────
# 1. INVARIANT: current version MUST exist in versions list
# 2. INVARIANT: current version MUST NOT be in deprecated list
# 3. INVARIANT: deprecated versions MUST still exist in versions list
#    (never remove a version—only deprecate it)
# 4. INVARIANT: versions list MUST NOT be empty
# 5. INVARIANT: business_keys MUST NOT be empty
# 6. CONVENTION: versions list should be sorted chronologically (oldest first)
# 7. CONVENTION: table name should use {domain}_ prefix and be snake_case
#
# MIGRATION RULES:
# ─────────────────────────────────────────────────────────────────────────────
# - To add a new version: append to versions[], leave current unchanged
# - To activate a new version: update current to the new version
# - To deprecate a version: add to deprecated[], update current if needed
# - NEVER remove a version from versions[] without a full migration plan
# - NEVER set current to a deprecated version
#
# See docs/fitness/02-calc-contract-and-conventions.md for full documentation.

CALCS = {
    "symbol_summary": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_symbol_summary",
        "business_keys": ["week_ending", "tier", "symbol"],
    },
    "venue_share": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_venue_share",
        "business_keys": ["week_ending", "tier", "mpid"],
    },
    "rolling_6w": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_symbol_rolling_6w",
        "business_keys": ["week_ending", "tier", "symbol"],
    },
    "liquidity_score": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_liquidity_score",
        "business_keys": ["week_ending", "tier", "symbol"],
    },
    # NEW: Real Trading Analytics Calculations
    "weekly_symbol_venue_volume": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_weekly_symbol_venue_volume",
        "business_keys": ["week_ending", "tier", "symbol", "mpid"],
        "description": "Venue-level volume and trade count for each symbol (base gold table)",
    },
    "weekly_symbol_venue_share": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_weekly_symbol_venue_share",
        "business_keys": ["week_ending", "tier", "symbol", "mpid"],
        "description": "Venue market share per symbol (venue_volume / total_symbol_volume)",
    },
    "weekly_symbol_venue_concentration_hhi": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_weekly_symbol_venue_concentration_hhi",
        "business_keys": ["week_ending", "tier", "symbol"],
        "description": "Herfindahl-Hirschman Index (HHI) measuring venue concentration per symbol",
    },
    "weekly_symbol_tier_volume_share": {
        "versions": ["v1"],
        "current": "v1",
        "deprecated": [],
        "table": f"{TABLE_PREFIX}_weekly_symbol_tier_volume_share",
        "business_keys": ["week_ending", "tier", "symbol"],
        "description": "Tier volume split showing distribution of symbol volume across tiers",
    },
}


def get_current_version(calc_name: str) -> str:
    """
    Return the policy-defined current version for a calculation.
    
    Use this instead of MAX(calc_version) to ensure v10 > v2.
    
    Raises:
        KeyError: If calc_name not in registry
    """
    if calc_name not in CALCS:
        raise KeyError(f"Unknown calc: {calc_name}. Known: {list(CALCS.keys())}")
    return CALCS[calc_name]["current"]


def get_version_rank(calc_name: str, version: str) -> int:
    """
    Return numeric rank for a version (for ordering).
    
    v1 → 1, v2 → 2, v10 → 10
    Handles both "v1" and "1" formats.
    """
    if calc_name not in CALCS:
        raise KeyError(f"Unknown calc: {calc_name}")
    
    versions = CALCS[calc_name]["versions"]
    
    # Parse version string to int
    v_str = version.lstrip("v")
    try:
        v_int = int(v_str)
    except ValueError:
        # Not a numeric version, use index in list
        if version in versions:
            return versions.index(version) + 1
        return 0
    
    return v_int


def is_deprecated(calc_name: str, version: str) -> bool:
    """Check if a calc version is deprecated."""
    if calc_name not in CALCS:
        return False
    return version in CALCS[calc_name].get("deprecated", [])


def check_deprecation_warning(calc_name: str, version: str) -> str | None:
    """
    Return a deprecation warning message if version is deprecated, else None.
    
    Usage (CLI/API integration):
        warning = check_deprecation_warning("venue_share", "v1")
        if warning:
            print(f"⚠️  {warning}", file=sys.stderr)
    
    Returns:
        Deprecation warning message or None if not deprecated
    """
    if not is_deprecated(calc_name, version):
        return None
    
    current = get_current_version(calc_name)
    return (
        f"DEPRECATED: {calc_name} {version} is deprecated. "
        f"Use version '{current}' instead. "
        f"Deprecated versions may be removed in future releases."
    )


def get_calc_metadata(calc_name: str, version: str | None = None) -> dict:
    """
    Return metadata for a calc version (for API responses).
    
    If version is None, returns metadata for current version.
    
    Example response:
        {
            "calc_name": "venue_share",
            "calc_version": "v1",
            "is_current": True,
            "deprecated": False,
            "deprecation_warning": None,
            "table": "finra_otc_transparency_venue_share",
            "business_keys": ["week_ending", "tier", "mpid"]
        }
    """
    if calc_name not in CALCS:
        raise KeyError(f"Unknown calc: {calc_name}. Known: {list(CALCS.keys())}")
    
    config = CALCS[calc_name]
    v = version or config["current"]
    
    if v not in config["versions"]:
        raise ValueError(f"Unknown version '{v}' for calc '{calc_name}'. Known: {config['versions']}")
    
    deprecated = is_deprecated(calc_name, v)
    
    return {
        "calc_name": calc_name,
        "calc_version": v,
        "is_current": v == config["current"],
        "deprecated": deprecated,
        "deprecation_warning": check_deprecation_warning(calc_name, v),
        "table": config["table"],
        "business_keys": config["business_keys"],
    }
