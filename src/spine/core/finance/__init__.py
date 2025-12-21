"""
Reusable financial primitives for the Spine ecosystem.

Manifesto:
    Financial data operations have unique correctness requirements that
    general-purpose tools miss.  Adjustments (splits, dividends) alter
    the meaning of per-share metrics across time.  Corrections (restatements,
    vendor fixes) change published values after the fact.  Without shared,
    auditable primitives, every project invents its own split math and
    silently overwrites corrected values.

    These patterns originate from real problems in the estimates-vs-actuals
    operation where different sources (Bloomberg, FactSet, Zacks) report
    *different* values for the same metric, and corrections arrive days
    or weeks after initial publication.

Modules:
    adjustments: Factor-based adjustment math (splits, dividends, etc.)
    corrections: Why-an-observation-changed taxonomy with audit trail

Related Modules:
    - :mod:`spine.core.temporal_envelope` — wraps financial observations
      with 4-timestamp semantics for PIT-correct queries
    - :mod:`spine.core.watermarks` — tracks how far each data source
      has been ingested
    - :mod:`spine.core.backfill` -- structured recovery when gaps or
      corrections are detected

STDLIB ONLY -- no Pydantic.

Tags:
    spine-core, finance, adjustments, corrections, audit-trail,
    stdlib-only, domain-agnostic, composable

Doc-Types:
    package-overview, domain-model
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
