"""
Reusable financial primitives for the Spine ecosystem.

This package provides domain-agnostic financial building blocks that
any downstream project (market-spine, feedspine, capture-spine) can
compose.  Market-spine-specific domain models (CorporateAction,
BiTemporalQueryEngine) live in market-spine, not here.

Why This Matters:
    Financial data pipelines have unique correctness requirements that
    general-purpose tools miss:

    - **Adjustments**: A stock split doubles the share count and halves
      the price.  Historical per-share metrics (EPS, dividends, prices)
      must be adjusted to remain comparable across time.  Without a
      composable adjustment chain, every project invents its own split
      math — and gets it wrong for edge cases like reverse splits,
      spin-offs, or multiple events in one quarter.

    - **Corrections**: When a company restates earnings, or a vendor
      like Bloomberg issues a correction notice, the old value doesn't
      disappear — it needs an auditable record showing what changed,
      why, and by how much.  The ``CorrectionRecord`` pattern captures
      this as a first-class concept instead of silently overwriting
      the old value.

    These patterns originate from real problems encountered in the
    estimates-vs-actuals pipeline (see ``feedspine/docs/features/
    estimates-vs-actuals/01_DESIGN.md``) where different sources
    (Bloomberg, FactSet, Zacks) report *different* values for the
    same metric, and corrections arrive days or weeks after initial
    publication.

Modules:
    adjustments: Factor-based adjustment math (splits, dividends, etc.)
    corrections: Why-an-observation-changed taxonomy with audit trail

Related Modules:
    - :mod:`spine.core.temporal_envelope` — wraps financial observations
      with 4-timestamp semantics for PIT-correct queries
    - :mod:`spine.core.watermarks` — tracks how far each data source
      has been ingested
    - :mod:`spine.core.backfill` — structured recovery when gaps or
      corrections are detected

STDLIB ONLY — no Pydantic.
"""

from spine.core.finance.adjustments import (
    AdjustmentChain,
    AdjustmentFactor,
    AdjustmentMethod,
)
from spine.core.finance.corrections import CorrectionReason, CorrectionRecord

__all__ = [
    "AdjustmentChain",
    "AdjustmentFactor",
    "AdjustmentMethod",
    "CorrectionReason",
    "CorrectionRecord",
]
