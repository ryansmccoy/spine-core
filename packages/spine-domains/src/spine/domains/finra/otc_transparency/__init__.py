"""
FINRA OTC Weekly Transparency Domain.

A thin domain built on spine.core primitives:
- schema: Tables, stages, tiers, natural keys
- connector: Parse FINRA PSV files
- normalizer: Validate and normalize records
- calculations: Pure aggregation functions
- pipelines: Orchestration over core primitives

For documentation see:
- docs/overview.md - What is FINRA OTC Transparency data
- docs/data_dictionary.md - Field definitions
- docs/timing_and_clocks.md - Publication cadence and clock model
- docs/pipelines.md - Pipeline reference
"""

from spine.domains.finra.otc_transparency import pipelines  # noqa: F401 - registers pipelines
