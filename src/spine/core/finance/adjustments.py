"""
Factor-based adjustment math for financial time-series.

Provides composable adjustment factors that convert raw per-share
metrics (price, EPS, dividends) between different adjustment bases.
Common use-cases: stock splits, reverse splits, spin-offs, rights
issues, and special dividends.

Why This Matters — Financial Pipelines:
    When Apple executed a 4-for-1 stock split in August 2020, every
    historical price, EPS, and dividend figure had to be divided by 4
    to remain comparable with post-split figures.  If your pipeline
    stores both adjusted and unadjusted values (common for audit and
    reconciliation), you need the adjustment factors themselves — not
    just the result.

    Real-world complexity:
    - **Multiple events**: TSLA had a 5-for-1 (2020) then a 3-for-1
      (2022).  The composite factor is 15, and ``adjust_as_of()``
      must apply only the factors effective up to a given date.
    - **Different metrics**: Splits affect price and EPS, but revenue
      and market cap are unaffected.  The caller decides which fields
      to adjust — this module supplies the math.
    - **Vendor reconciliation**: Bloomberg and FactSet may disagree
      on the exact adjustment factor for a spin-off.  Keeping factors
      as first-class objects (with provenance via ``metadata``) lets
      you audit the discrepancy.

Why This Matters — General Pipelines:
    Any time-series with unit changes over time (currency redenomination,
    sensor recalibration, API version migration) benefits from composable
    factor chains.  The ``adjust_as_of()`` pattern generalises to "apply
    only the corrections relevant up to this point in time".

Key Concepts:
    AdjustmentMethod: Why an adjustment was applied (SPLIT, DIVIDEND, etc.)
    AdjustmentFactor: A single (date, factor, method) triple.
    AdjustmentChain: An ordered sequence of factors with composite
        multiplication and inversion.

Related Modules:
    - :mod:`spine.core.finance.corrections` — records *why* a value
      changed (restatement, data error) — complementary to adjustments
      which handle *structural* changes (splits, dividends)
    - :mod:`spine.core.temporal_envelope` — ensures adjusted values
      carry correct temporal context

Example:
    >>> from datetime import date
    >>> from spine.core.finance.adjustments import (
    ...     AdjustmentChain, AdjustmentFactor, AdjustmentMethod,
    ... )
    >>> chain = AdjustmentChain(factors=[
    ...     AdjustmentFactor(
    ...         effective_date=date(2025, 6, 15),
    ...         factor=2.0,
    ...         method=AdjustmentMethod.SPLIT,
    ...         description="2-for-1 stock split",
    ...     ),
    ...     AdjustmentFactor(
    ...         effective_date=date(2025, 9, 1),
    ...         factor=4.0,
    ...         method=AdjustmentMethod.SPLIT,
    ...         description="4-for-1 stock split",
    ...     ),
    ... ])
    >>> chain.composite_factor
    8.0
    >>> chain.adjust(100.0)  # pre-split price → post-split
    800.0
    >>> chain.unadjust(800.0)  # post-split → pre-split
    100.0

STDLIB ONLY — no Pydantic.

Tags:
    finance, adjustment, split, dividend, per-share, spine-core,
    corporate-action, time-series, reconciliation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AdjustmentMethod(str, Enum):
    """Why a per-share adjustment was applied.

    Each value corresponds to a corporate action class that changes the
    number of shares outstanding and therefore requires historical
    per-share figures to be restated.
    """

    SPLIT = "split"
    REVERSE_SPLIT = "reverse_split"
    STOCK_DIVIDEND = "stock_dividend"
    CASH_DIVIDEND = "cash_dividend"
    SPIN_OFF = "spin_off"
    RIGHTS_ISSUE = "rights_issue"
    SPECIAL_DIVIDEND = "special_dividend"
    MERGER = "merger"
    OTHER = "other"


# ---------------------------------------------------------------------------
# AdjustmentFactor
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdjustmentFactor:
    """A single adjustment event on a specific date.

    Attributes:
        effective_date: Date the adjustment takes effect (ex-date).
        factor: Multiplicative factor.  For a 2-for-1 split this is
            ``2.0``; for a 1-for-10 reverse split this is ``0.1``.
        method: The type of corporate action that caused the adjustment.
        description: Human-readable label (e.g. "2-for-1 stock split").
        entity_key: Optional entity identifier (e.g. ticker).
        metadata: Arbitrary extras for audit / lineage.

    Examples:
        >>> f = AdjustmentFactor(
        ...     effective_date=date(2025, 6, 15),
        ...     factor=2.0,
        ...     method=AdjustmentMethod.SPLIT,
        ... )
        >>> f.inverse_factor
        0.5
    """

    effective_date: date
    factor: float
    method: AdjustmentMethod
    description: str = ""
    entity_key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def inverse_factor(self) -> float:
        """Reciprocal factor for reversing the adjustment."""
        if self.factor == 0:
            raise ZeroDivisionError("Cannot invert a zero adjustment factor")
        return 1.0 / self.factor

    def adjust(self, value: float) -> float:
        """Apply this factor: ``value * factor``."""
        return value * self.factor

    def unadjust(self, value: float) -> float:
        """Reverse this factor: ``value / factor``."""
        return value * self.inverse_factor


# ---------------------------------------------------------------------------
# AdjustmentChain
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AdjustmentChain:
    """An ordered sequence of adjustment factors.

    Factors are applied in order (oldest → newest by convention).
    The ``composite_factor`` is the product of all individual factors.

    Attributes:
        factors: Ordered list of :class:`AdjustmentFactor`.
        entity_key: Optional entity identifier (e.g. ticker).

    Examples:
        >>> chain = AdjustmentChain(factors=[
        ...     AdjustmentFactor(date(2025, 1, 1), 2.0, AdjustmentMethod.SPLIT),
        ...     AdjustmentFactor(date(2025, 6, 1), 3.0, AdjustmentMethod.SPLIT),
        ... ])
        >>> chain.composite_factor
        6.0
    """

    factors: list[AdjustmentFactor] = field(default_factory=list)
    entity_key: str = ""

    # -- properties ----------------------------------------------------------

    @property
    def composite_factor(self) -> float:
        """Product of all factors in the chain."""
        result = 1.0
        for f in self.factors:
            result *= f.factor
        return result

    @property
    def inverse_composite_factor(self) -> float:
        """Reciprocal of the composite factor."""
        cf = self.composite_factor
        if cf == 0:
            raise ZeroDivisionError("Composite factor is zero")
        return 1.0 / cf

    @property
    def sorted_factors(self) -> list[AdjustmentFactor]:
        """Factors sorted by effective_date (ascending)."""
        return sorted(self.factors, key=lambda f: f.effective_date)

    # -- adjustment operations -----------------------------------------------

    def adjust(self, value: float) -> float:
        """Apply the full chain: ``value * composite_factor``."""
        return value * self.composite_factor

    def unadjust(self, value: float) -> float:
        """Reverse the full chain: ``value / composite_factor``."""
        return value * self.inverse_composite_factor

    def adjust_as_of(self, value: float, as_of: date) -> float:
        """Apply only factors effective on or before *as_of*.

        Args:
            value: The raw value to adjust.
            as_of: Only factors with ``effective_date <= as_of`` are applied.

        Returns:
            The adjusted value.
        """
        partial = 1.0
        for f in self.factors:
            if f.effective_date <= as_of:
                partial *= f.factor
        return value * partial

    # -- chain composition ---------------------------------------------------

    def append(self, factor: AdjustmentFactor) -> AdjustmentChain:
        """Return a new chain with *factor* appended.

        AdjustmentChain is frozen, so this returns a copy.

        Args:
            factor: The factor to add.

        Returns:
            New :class:`AdjustmentChain` with the additional factor.
        """
        return AdjustmentChain(
            factors=[*self.factors, factor],
            entity_key=self.entity_key,
        )

    def merge(self, other: AdjustmentChain) -> AdjustmentChain:
        """Combine two chains (e.g. from different sources).

        Factors are concatenated and de-duplicated is NOT performed
        (caller must ensure no overlap).

        Args:
            other: Another chain to merge with.

        Returns:
            New :class:`AdjustmentChain` with factors from both chains.
        """
        return AdjustmentChain(
            factors=[*self.factors, *other.factors],
            entity_key=self.entity_key or other.entity_key,
        )

    def factors_between(self, start: date, end: date) -> list[AdjustmentFactor]:
        """Return factors with effective_date in ``[start, end]`` inclusive.

        Args:
            start: Start date (inclusive).
            end: End date (inclusive).

        Returns:
            List of matching factors.
        """
        return [
            f for f in self.factors
            if start <= f.effective_date <= end
        ]
