"""
Financial observation domain models (stdlib dataclass).

STDLIB ONLY - NO PYDANTIC.

Universal financial primitives promoted from market-spine for cross-spine
reuse. Any spine project that tracks financial data points (observations,
metrics, provenance) should import from here.

Models:
    MetricSpec: What's being measured (orthogonal axes)
    FiscalPeriod: What timeframe the number measures
    ValueWithUnits: Numeric value with currency/scale
    ProvenanceRef: Document-level lineage (where data came from)
    SourceKey: Field-level provenance (which field in which dataset)
    Observation: A single data point with 3D time semantics
    ObservationSet: Collection for comparison/analysis

Time dimensions on Observation:
    1. period: What timeframe the number measures (Q4 FY2025)
    2. as_of: When it was known/published (filing date)
    3. captured_at: When our system ingested it (staleness tracking)

Consistent with entityspine ADR-006 bitemporal pattern
(captured_at + valid_from/valid_to).
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256

from spine.core.enums import ProvenanceKind, VendorNamespace
from spine.core.timestamps import generate_ulid, utc_now
from spine.domain.finance.enums import (
    AccountingBasis,
    MetricCategory,
    MetricCode,
    ObservationType,
    PeriodType,
    PerShareType,
    Presentation,
    ScopeType,
)

# =============================================================================
# MetricSpec - Structured metric specification
# =============================================================================


@dataclass(frozen=True, slots=True)
class MetricSpec:
    """
    Structured metric specification with orthogonal axes.

    Replaces ambiguous (MetricCode, variant) with explicit dimensions
    that don't conflate different concepts (basis vs presentation vs
    share type vs scope).

    Example::

        MetricSpec(
            code=MetricCode.EPS,
            category=MetricCategory.PER_SHARE,
            basis=AccountingBasis.GAAP,
            presentation=Presentation.REPORTED,
            per_share=PerShareType.DILUTED,
            scope=ScopeType.TOTAL,
        )

    Attributes:
        code: Core metric identifier (REVENUE, EPS, etc.)
        category: Financial statement category
        basis: Accounting standard (GAAP, IFRS)
        presentation: How adjusted (reported, company_adj, vendor_norm)
        per_share: Share count basis for EPS-like (basic, diluted)
        scope: Operations scope (total, continuing, discontinued)
        custom_code: For unmapped metrics
        custom_name: Human-readable name for custom metrics
    """

    code: MetricCode
    category: MetricCategory = MetricCategory.OTHER
    basis: AccountingBasis = AccountingBasis.GAAP
    presentation: Presentation = Presentation.REPORTED
    per_share: PerShareType | None = None
    scope: ScopeType | None = None
    custom_code: str | None = None
    custom_name: str | None = None

    def __post_init__(self) -> None:
        """Validate MetricSpec — default to diluted for EPS-like metrics."""
        if self.code in (MetricCode.EPS, MetricCode.DPS, MetricCode.BPS, MetricCode.CFPS):
            if self.per_share is None:
                object.__setattr__(self, "per_share", PerShareType.DILUTED)

    def __str__(self) -> str:
        """Human-readable representation."""
        parts = [self.code.value.upper()]

        if self.per_share:
            parts.append(f"({self.per_share.value})")

        qualifiers = []
        if self.basis != AccountingBasis.GAAP:
            qualifiers.append(self.basis.value)
        if self.presentation != Presentation.REPORTED:
            qualifiers.append(self.presentation.value)
        if self.scope and self.scope != ScopeType.TOTAL:
            qualifiers.append(self.scope.value)

        if qualifiers:
            parts.append(f"[{', '.join(qualifiers)}]")

        return " ".join(parts)

    @property
    def canonical_key(self) -> str:
        """Stable key for grouping/matching."""
        parts = [
            self.code.value,
            self.category.value,
            self.basis.value,
            self.presentation.value,
            self.per_share.value if self.per_share else "na",
            self.scope.value if self.scope else "total",
        ]
        return ":".join(parts)

    # --- Factory methods for common metrics ---

    @classmethod
    def revenue(cls, presentation: Presentation = Presentation.REPORTED) -> "MetricSpec":
        """Revenue metric."""
        return cls(
            code=MetricCode.REVENUE,
            category=MetricCategory.INCOME_STATEMENT,
            presentation=presentation,
        )

    @classmethod
    def eps_gaap_diluted(cls) -> "MetricSpec":
        """GAAP diluted EPS."""
        return cls(
            code=MetricCode.EPS,
            category=MetricCategory.PER_SHARE,
            basis=AccountingBasis.GAAP,
            presentation=Presentation.REPORTED,
            per_share=PerShareType.DILUTED,
            scope=ScopeType.TOTAL,
        )

    @classmethod
    def eps_gaap_basic(cls) -> "MetricSpec":
        """GAAP basic EPS."""
        return cls(
            code=MetricCode.EPS,
            category=MetricCategory.PER_SHARE,
            basis=AccountingBasis.GAAP,
            presentation=Presentation.REPORTED,
            per_share=PerShareType.BASIC,
            scope=ScopeType.TOTAL,
        )

    @classmethod
    def net_income(cls, presentation: Presentation = Presentation.REPORTED) -> "MetricSpec":
        """Net income metric."""
        return cls(
            code=MetricCode.NET_INCOME,
            category=MetricCategory.INCOME_STATEMENT,
            presentation=presentation,
        )

    @classmethod
    def ebitda(cls, presentation: Presentation = Presentation.REPORTED) -> "MetricSpec":
        """EBITDA metric."""
        return cls(
            code=MetricCode.EBITDA,
            category=MetricCategory.INCOME_STATEMENT,
            presentation=presentation,
        )

    @classmethod
    def fcf(cls) -> "MetricSpec":
        """Free cash flow metric."""
        return cls(
            code=MetricCode.FCF,
            category=MetricCategory.CASH_FLOW,
        )


# =============================================================================
# FiscalPeriod - What timeframe the number measures
# =============================================================================


@dataclass(frozen=True, slots=True)
class FiscalPeriod:
    """
    Fiscal period — WHAT timeframe the number measures.

    This is the measurement period, not when reported or captured.

    Examples:
        FY2025: full fiscal year 2025
        Q4 FY2025: fourth fiscal quarter 2025
        H1 2025: first half 2025
        TTM Q3 2025: trailing 12 months ending Q3 2025

    Attributes:
        fiscal_year: Year (e.g., 2025)
        period_type: Type of period (ANNUAL, QUARTERLY, etc.)
        quarter: 1-4 for quarterly
        half: 1-2 for semi-annual
        fye_month: Fiscal year end month (1-12, default 12)
        period_start: Start date if known
        period_end: End date if known
    """

    fiscal_year: int
    period_type: PeriodType
    quarter: int | None = None
    half: int | None = None
    fye_month: int = 12
    period_start: date | None = None
    period_end: date | None = None

    def __post_init__(self) -> None:
        """Validate FiscalPeriod."""
        if self.period_type == PeriodType.QUARTERLY:
            if self.quarter is None or not (1 <= self.quarter <= 4):
                raise ValueError(f"Quarterly period requires quarter 1-4, got {self.quarter}")
        if self.period_type == PeriodType.SEMI_ANNUAL:
            if self.half is None or not (1 <= self.half <= 2):
                raise ValueError(f"Semi-annual period requires half 1-2, got {self.half}")

    def __str__(self) -> str:
        if self.period_type == PeriodType.ANNUAL:
            return f"FY{self.fiscal_year}"
        elif self.period_type == PeriodType.QUARTERLY:
            return f"Q{self.quarter} FY{self.fiscal_year}"
        elif self.period_type == PeriodType.SEMI_ANNUAL:
            return f"H{self.half} {self.fiscal_year}"
        elif self.period_type == PeriodType.TTM:
            if self.quarter:
                return f"TTM Q{self.quarter} {self.fiscal_year}"
            return f"TTM {self.fiscal_year}"
        else:
            return f"{self.period_type.value} {self.fiscal_year}"

    @property
    def canonical_key(self) -> str:
        """Stable string for hashing/grouping."""
        return f"{self.fiscal_year}:{self.period_type.value}:{self.quarter or 0}:{self.half or 0}"

    @classmethod
    def annual(cls, year: int, fye_month: int = 12) -> "FiscalPeriod":
        """Create annual period."""
        return cls(fiscal_year=year, period_type=PeriodType.ANNUAL, fye_month=fye_month)

    @classmethod
    def quarterly(cls, year: int, quarter: int, fye_month: int = 12) -> "FiscalPeriod":
        """Create quarterly period."""
        return cls(
            fiscal_year=year, period_type=PeriodType.QUARTERLY, quarter=quarter, fye_month=fye_month
        )

    @classmethod
    def semi_annual(cls, year: int, half: int, fye_month: int = 12) -> "FiscalPeriod":
        """Create semi-annual period."""
        return cls(
            fiscal_year=year, period_type=PeriodType.SEMI_ANNUAL, half=half, fye_month=fye_month
        )

    @classmethod
    def ttm(cls, year: int, ending_quarter: int | None = None) -> "FiscalPeriod":
        """Create trailing twelve months period."""
        return cls(fiscal_year=year, period_type=PeriodType.TTM, quarter=ending_quarter)


# =============================================================================
# ProvenanceRef - Which document/snapshot produced this
# =============================================================================


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    """
    Document/snapshot that produced this observation.

    Answers: "Where did this value come from?"

    Separate from SourceKey (which dataset/field) because:
    - Same dataset can have multiple snapshots
    - Same document can produce multiple metrics
    - Lineage tracking needs document-level identity

    Attributes:
        kind: Type of provenance (sec_filing, vendor_snapshot, etc.)
        external_id: External identifier (accession number, URL hash, etc.)
        provenance_id: ULID primary key
        published_at: When source published this
        document_url: URL to source document
        document_title: Title of source document
        accession_number: SEC accession number (for filings)
        form_type: SEC form type (10-K, 10-Q, 8-K)
        filing_date: SEC filing date
        snapshot_date: Vendor snapshot date
        snapshot_version: Vendor snapshot version
    """

    kind: ProvenanceKind
    external_id: str

    provenance_id: str = field(default_factory=generate_ulid)
    published_at: datetime | None = None
    document_url: str | None = None
    document_title: str | None = None

    # SEC filing specific
    accession_number: str | None = None
    form_type: str | None = None
    filing_date: date | None = None

    # Vendor snapshot specific
    snapshot_date: date | None = None
    snapshot_version: str | None = None

    def __post_init__(self) -> None:
        """Validate ProvenanceRef."""
        if not self.external_id or not self.external_id.strip():
            raise ValueError("external_id cannot be empty")

    def __str__(self) -> str:
        return f"{self.kind.value}:{self.external_id}"

    @classmethod
    def sec_filing(
        cls,
        accession_number: str,
        form_type: str,
        filing_date: date,
    ) -> "ProvenanceRef":
        """Create SEC filing provenance."""
        return cls(
            kind=ProvenanceKind.SEC_FILING,
            external_id=accession_number,
            accession_number=accession_number,
            form_type=form_type,
            filing_date=filing_date,
            published_at=datetime.combine(filing_date, datetime.min.time()),
        )

    @classmethod
    def vendor_snapshot(
        cls,
        vendor: VendorNamespace,
        snapshot_date: date,
        snapshot_id: str | None = None,
    ) -> "ProvenanceRef":
        """Create vendor snapshot provenance."""
        ext_id = snapshot_id or f"{vendor.value}:{snapshot_date.isoformat()}"
        return cls(
            kind=ProvenanceKind.VENDOR_SNAPSHOT,
            external_id=ext_id,
            snapshot_date=snapshot_date,
        )

    @classmethod
    def press_release(
        cls,
        release_date: date,
        url: str | None = None,
        title: str | None = None,
    ) -> "ProvenanceRef":
        """Create press release provenance."""
        ext_id = url or f"pr:{release_date.isoformat()}"
        return cls(
            kind=ProvenanceKind.PRESS_RELEASE,
            external_id=ext_id,
            published_at=datetime.combine(release_date, datetime.min.time()),
            document_url=url,
            document_title=title,
        )


# =============================================================================
# SourceKey - Which dataset/field produced this
# =============================================================================


@dataclass(frozen=True, slots=True)
class SourceKey:
    """
    Dataset/field that produced this observation.

    Answers: "What was the source field code?"

    Separate from ProvenanceRef because:
    - Multiple documents can reference same field
    - Field mapping is vendor-specific
    - Needed for crosswalk/reconciliation

    Vendor-specific factory methods (e.g. factset(), bloomberg())
    live in market-spine. This base class provides the core structure
    and the XBRL factory for SEC-sourced data.

    Attributes:
        vendor: Vendor namespace
        dataset: Dataset name (ff_fundamentals, bloomberg_estimates)
        field_name: Original field name (FF_SALES, IS_EPS)
        xbrl_namespace: XBRL namespace (us-gaap, ifrs-full)
        xbrl_tag: XBRL tag name (Revenues, NetIncomeLoss)
    """

    vendor: VendorNamespace | None = None
    dataset: str | None = None
    field_name: str | None = None
    xbrl_namespace: str | None = None
    xbrl_tag: str | None = None

    def __str__(self) -> str:
        if self.xbrl_tag:
            return f"{self.xbrl_namespace or 'xbrl'}:{self.xbrl_tag}"
        if self.vendor and self.field_name:
            return f"{self.vendor.value}:{self.field_name}"
        return self.field_name or self.dataset or "unknown"

    @classmethod
    def sec_xbrl(cls, tag: str, namespace: str = "us-gaap") -> "SourceKey":
        """Create SEC XBRL source key."""
        return cls(vendor=VendorNamespace.SEC, xbrl_namespace=namespace, xbrl_tag=tag)

    @classmethod
    def from_vendor(
        cls,
        vendor: VendorNamespace,
        field_name: str,
        dataset: str | None = None,
    ) -> "SourceKey":
        """Create a vendor field source key (generic factory)."""
        return cls(vendor=vendor, dataset=dataset, field_name=field_name)


# =============================================================================
# ValueWithUnits - Raw + normalized value storage
# =============================================================================


@dataclass(frozen=True, slots=True)
class ValueWithUnits:
    """
    Numeric value with explicit units and scale.

    Stores BOTH raw and normalized values to prevent:
    - "$119.2B" vs "119,200 (millions)" confusion
    - Currency conversion ambiguity
    - Scale mismatches in aggregation

    value_normalized is ALWAYS in base units (e.g., USD, not USD millions).

    Attributes:
        value_normalized: Value in base units (always use this for math)
        value_raw: Value as received from source
        unit: Unit type (USD, EUR, USD/share, %, shares)
        scale: Multiplier from raw to normalized (1, 1000, 1000000)
        currency: ISO 4217 currency code
    """

    value_normalized: Decimal
    value_raw: Decimal
    unit: str
    scale: int = 1
    currency: str | None = None

    def __post_init__(self) -> None:
        """Validate ValueWithUnits."""
        if self.scale <= 0:
            raise ValueError(f"scale must be positive, got {self.scale}")

    @classmethod
    def from_raw(
        cls,
        value_raw: Decimal,
        unit: str,
        scale: int = 1,
        currency: str | None = None,
    ) -> "ValueWithUnits":
        """Create from raw value, auto-normalizing."""
        return cls(
            value_normalized=value_raw * scale,
            value_raw=value_raw,
            unit=unit,
            scale=scale,
            currency=currency,
        )

    @classmethod
    def from_normalized(
        cls,
        value_normalized: Decimal,
        unit: str,
        scale: int = 1,
        currency: str | None = None,
    ) -> "ValueWithUnits":
        """Create from normalized value, computing raw."""
        return cls(
            value_normalized=value_normalized,
            value_raw=value_normalized / scale if scale != 0 else value_normalized,
            unit=unit,
            scale=scale,
            currency=currency,
        )

    def in_millions(self) -> Decimal:
        """Get value in millions."""
        return self.value_normalized / Decimal("1000000")

    def in_billions(self) -> Decimal:
        """Get value in billions."""
        return self.value_normalized / Decimal("1000000000")

    def __str__(self) -> str:
        if self.currency:
            return f"{self.currency} {self.value_normalized:,.2f}"
        return f"{self.value_normalized:,.2f} {self.unit}"


# =============================================================================
# Observation - Core observation model
# =============================================================================


@dataclass(frozen=True, slots=True)
class Observation:
    """
    A single financial data point with full provenance.

    Captures not just the value but WHEN it was valid, WHEN we learned
    about it, WHERE it came from, and HOW confident we are.

    Time dimensions:
        1. **period**: What timeframe the number measures (Q4 FY2025 revenue)
        2. **as_of**: When it was known/published (10-K filing date)
        3. **captured_at**: When our system ingested it (staleness tracking)

    The supersession chain (supersedes_id/superseded_by_id) handles
    revisions without destructive updates.

    Consistent with entityspine ADR-006 bitemporal pattern:
        - captured_at ≈ system time
        - as_of ≈ business/valid time

    Attributes:
        entity_id: Entity being measured
        metric: MetricSpec — what's measured and how
        period: FiscalPeriod — measurement timeframe
        value: ValueWithUnits — the number with units
        observation_id: ULID primary key
        security_id: Optional security target
        observation_type: ACTUAL, ESTIMATE, CONSENSUS, GUIDANCE
        as_of: When value was known/published
        captured_at: When system ingested it
        provenance_ref: Document-level lineage
        source_key: Field-level lineage
        supersedes_id: Previous observation this supersedes
        superseded_by_id: Newer observation that supersedes this
        confidence: Quality score 0.0-1.0
    """

    # Required fields
    entity_id: str
    metric: MetricSpec
    period: FiscalPeriod
    value: ValueWithUnits

    # Primary key
    observation_id: str = field(default_factory=generate_ulid)

    # Optional target
    security_id: str | None = None

    # Observation type
    observation_type: ObservationType = ObservationType.ACTUAL

    # For non-numeric values
    value_string: str | None = None

    # Time semantics
    as_of: datetime | None = None
    captured_at: datetime = field(default_factory=utc_now)

    # Provenance
    provenance_ref: ProvenanceRef | None = None
    source_key: SourceKey | None = None

    # Supersession chain
    supersedes_id: str | None = None
    superseded_by_id: str | None = None

    # Quality
    confidence: float = 1.0

    # Raw data
    raw_value: str | None = None
    notes: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """Validate Observation."""
        if not self.entity_id or not self.entity_id.strip():
            raise ValueError("entity_id cannot be empty")

        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be between 0.0 and 1.0, got {self.confidence}")

    @property
    def observation_key(self) -> str:
        """
        Deterministic key for deduplication/idempotency.

        Same key = same logical observation (for upsert semantics).
        """
        parts = [
            self.entity_id,
            self.metric.canonical_key,
            self.period.canonical_key,
            self.as_of.isoformat() if self.as_of else "na",
        ]

        if self.provenance_ref:
            parts.append(self.provenance_ref.external_id)

        key_string = "|".join(parts)
        return sha256(key_string.encode()).hexdigest()[:32]

    def __repr__(self) -> str:
        return (
            f"Observation("
            f"entity={self.entity_id}, "
            f"metric={self.metric}, "
            f"period={self.period}, "
            f"type={self.observation_type.value}, "
            f"value={self.value.value_normalized:,.2f})"
        )


# =============================================================================
# ObservationSet - Collection for comparison
# =============================================================================


@dataclass
class ObservationSet:
    """
    Collection of observations for comparison/analysis.

    Useful for:
    - Comparing estimates to actuals
    - Cross-source validation
    - Consensus calculation

    Attributes:
        entity_id: Entity being tracked
        metric: Metric being tracked
        period: Period being tracked
        observations: List of observations
    """

    entity_id: str
    metric: MetricSpec
    period: FiscalPeriod
    observations: list[Observation] = field(default_factory=list)

    def get_by_type(self, obs_type: ObservationType) -> list[Observation]:
        """Filter by observation type."""
        return [o for o in self.observations if o.observation_type == obs_type]

    def get_estimates(self) -> list[Observation]:
        """Get all estimate observations."""
        return self.get_by_type(ObservationType.ESTIMATE)

    def get_actuals(self) -> list[Observation]:
        """Get all actual observations."""
        return self.get_by_type(ObservationType.ACTUAL)

    def get_consensus(self) -> Observation | None:
        """Get consensus observation if one exists."""
        consensus = self.get_by_type(ObservationType.CONSENSUS)
        return consensus[0] if consensus else None

    def get_latest_actual(self) -> Observation | None:
        """Get most recent actual (by as_of timestamp)."""
        actuals = self.get_actuals()
        if not actuals:
            return None
        return max(actuals, key=lambda o: o.as_of or datetime.min)

    def get_authoritative_actual(self) -> Observation | None:
        """
        Get authoritative actual (not superseded, prefer SEC).

        Priority:
        1. Most recent SEC filing (not superseded)
        2. Most recent vendor actual
        3. Any actual
        """
        actuals = [o for o in self.get_actuals() if o.superseded_by_id is None]

        # SEC filings first
        sec = [
            o
            for o in actuals
            if o.provenance_ref and o.provenance_ref.kind == ProvenanceKind.SEC_FILING
        ]
        if sec:
            return max(sec, key=lambda o: o.as_of or datetime.min)

        # Any non-superseded actual
        if actuals:
            return max(actuals, key=lambda o: o.as_of or datetime.min)

        return None
