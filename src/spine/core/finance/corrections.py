"""
Correction taxonomy and records for financial observations.

When an observation (price, EPS, ratio, etc.) changes after initial
publication, a CorrectionRecord captures **why** it changed, what the
old and new values were, and who/what made the correction.

Why This Matters — Financial Pipelines:
    Financial data changes after publication more often than people
    expect.  SEC-mandated restatements (10-K/A filings), vendor
    correction notices from Bloomberg or FactSet, late-arriving actuals
    that replace preliminary estimates, and methodology changes all
    produce corrections that must be tracked.

    Real-world examples:
    - **EPS restatement**: Apple files a 10-K/A that revises diluted
      EPS from $1.52 to $1.46.  Without a CorrectionRecord, consumers
      have no idea the number changed, or why.
    - **Vendor disagreement**: Bloomberg and Zacks report different
      "actual" EPS values for the same quarter (see the feedspine
      estimates-vs-actuals design doc).  When one vendor later corrects
      their figure, the CorrectionRecord captures which vendor, when,
      and the delta.
    - **Late reporting**: A preliminary revenue estimate of $0 gets
      replaced by the actual figure of $1.5M once the quarterly
      report is filed.  ``pct_change`` returns ``None`` for the zero-
      original case, preventing division-by-zero surprises.

Why This Matters — General Pipelines:
    Any system where published values are later revised — reference
    data, configuration snapshots, telemetry — benefits from an
    auditable correction trail.  The pattern is: never silently
    overwrite; always capture old value, new value, reason, and
    who/what triggered the change.

Key Concepts:
    CorrectionReason: Enumeration of reasons an observation may be
        corrected (RESTATEMENT, DATA_ERROR, METHODOLOGY_CHANGE, etc.).
    CorrectionRecord: Immutable record pairing old/new values with a
        reason, timestamps, and optional provenance.

Related Modules:
    - :mod:`spine.core.finance.adjustments` — handles *structural*
      changes (splits, dividends) to per-share metrics; complementary
      to corrections which handle *value* changes
    - :mod:`spine.core.temporal_envelope` — BiTemporalRecord supersede()
      workflow uses corrections to close old versions and open new ones
    - :mod:`spine.core.backfill` — CORRECTION-reason backfills are
      triggered when corrections require re-processing downstream data

Example:
    >>> from spine.core.finance.corrections import (
    ...     CorrectionReason, CorrectionRecord,
    ... )
    >>> rec = CorrectionRecord.create(
    ...     entity_key="AAPL",
    ...     field_name="eps_diluted",
    ...     original_value=1.52,
    ...     corrected_value=1.46,
    ...     reason=CorrectionReason.RESTATEMENT,
    ...     corrected_by="sec_filing_parser",
    ...     source_ref="10-K/A filed 2025-03-15",
    ... )
    >>> rec.delta
    -0.06000...
    >>> rec.pct_change  # (1.46 - 1.52) / 1.52
    -0.0394...

STDLIB ONLY — no Pydantic.

Tags:
    finance, correction, restatement, audit, spine-core,
    observation, vendor-reconciliation, audit-trail
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from spine.core.timestamps import generate_ulid, utc_now

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class CorrectionReason(str, Enum):
    """Why a previously-published observation was corrected.

    Each value maps to a distinct operational cause.  Downstream
    systems can filter or weight corrections by reason (e.g. treat
    RESTATEMENT differently from ROUNDING).
    """

    RESTATEMENT = "restatement"
    """Company or regulator restated the original figure."""

    DATA_ERROR = "data_error"
    """Upstream data-feed delivered incorrect data."""

    METHODOLOGY_CHANGE = "methodology_change"
    """Calculation methodology was revised (e.g. new GAAP rule)."""

    LATE_REPORTING = "late_reporting"
    """Original value was estimated; actuals arrived later."""

    ROUNDING = "rounding"
    """Rounding precision was changed or corrected."""

    UNIT_CONVERSION = "unit_conversion"
    """Value was originally in wrong units (e.g. thousands vs millions)."""

    VENDOR_CORRECTION = "vendor_correction"
    """Third-party vendor issued a correction notice."""

    MANUAL = "manual"
    """Human analyst made a manual correction."""

    OTHER = "other"
    """Does not fit any standard category."""


# ---------------------------------------------------------------------------
# CorrectionRecord
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CorrectionRecord:
    """Immutable record of a single value correction.

    Captures the full context of why an observation changed: the entity,
    field, old value, new value, reason, who corrected it, and when.

    Attributes:
        correction_id: ULID-based unique identifier.
        entity_key: The entity whose observation was corrected
            (e.g. ticker, CIK, FIGI).
        field_name: The specific field that was corrected
            (e.g. ``"eps_diluted"``, ``"revenue"``).
        original_value: The value before correction.
        corrected_value: The value after correction.
        reason: Why the correction was made.
        corrected_at: UTC timestamp of the correction.
        corrected_by: Identifier of the agent/system that made the
            correction (e.g. ``"sec_filing_parser"``).
        source_ref: Reference to the source document or event that
            triggered the correction (e.g. an amended filing ID).
        notes: Free-form notes for audit trail.
        metadata: Arbitrary extras for lineage / enrichment.

    Examples:
        >>> rec = CorrectionRecord.create(
        ...     entity_key="MSFT",
        ...     field_name="revenue",
        ...     original_value=56_189_000_000,
        ...     corrected_value=56_517_000_000,
        ...     reason=CorrectionReason.RESTATEMENT,
        ... )
        >>> rec.delta
        328000000
    """

    correction_id: str
    entity_key: str
    field_name: str
    original_value: float
    corrected_value: float
    reason: CorrectionReason
    corrected_at: datetime
    corrected_by: str = ""
    source_ref: str = ""
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # -- factories -----------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        entity_key: str,
        field_name: str,
        original_value: float,
        corrected_value: float,
        reason: CorrectionReason,
        corrected_by: str = "",
        source_ref: str = "",
        notes: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> CorrectionRecord:
        """Create a new CorrectionRecord with auto-generated ID and timestamp.

        Args:
            entity_key: Entity identifier.
            field_name: Name of the corrected field.
            original_value: Old value.
            corrected_value: New value.
            reason: Correction reason.
            corrected_by: Correcting agent/system.
            source_ref: Source document reference.
            notes: Free-form notes.
            metadata: Optional extra metadata.

        Returns:
            A new :class:`CorrectionRecord`.
        """
        return cls(
            correction_id=generate_ulid(),
            entity_key=entity_key,
            field_name=field_name,
            original_value=original_value,
            corrected_value=corrected_value,
            reason=reason,
            corrected_at=utc_now(),
            corrected_by=corrected_by,
            source_ref=source_ref,
            notes=notes,
            metadata=metadata or {},
        )

    # -- derived properties --------------------------------------------------

    @property
    def delta(self) -> float:
        """Absolute change: ``corrected_value - original_value``."""
        return self.corrected_value - self.original_value

    @property
    def pct_change(self) -> float | None:
        """Percentage change relative to original value.

        Returns ``None`` if original_value is zero.
        """
        if self.original_value == 0:
            return None
        return (self.corrected_value - self.original_value) / self.original_value

    @property
    def abs_pct_change(self) -> float | None:
        """Absolute percentage change.

        Returns ``None`` if original_value is zero.
        """
        pct = self.pct_change
        return abs(pct) if pct is not None else None

    # -- serialisation -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a plain dict suitable for JSON / DB storage.

        Returns:
            Dict with all fields; ``corrected_at`` is ISO-8601 string,
            ``reason`` is its string value.
        """
        return {
            "correction_id": self.correction_id,
            "entity_key": self.entity_key,
            "field_name": self.field_name,
            "original_value": self.original_value,
            "corrected_value": self.corrected_value,
            "reason": self.reason.value,
            "corrected_at": self.corrected_at.isoformat(),
            "corrected_by": self.corrected_by,
            "source_ref": self.source_ref,
            "notes": self.notes,
            "metadata": self.metadata,
        }
