"""
Spine-Core Usage Examples for Intermediate Tier.

These examples demonstrate how to use spine-core primitives in the
intermediate tier context (PostgreSQL-backed with async support).

Examples:
    - error_handling: SpineError hierarchy and Result[T] pattern
    - sources: FileSource for CSV/PSV data ingestion
    - alerts: AlertChannel framework for notifications
    - workflow: Workflow orchestration v2 with data passing
    - finra_complete_demo: Complete FINRA pipeline example with mocks
    - otc_workflow: CORRECT pattern for using pipelines with workflows

IMPORTANT - Architecture Pattern:

    ┌─────────────────────────────────────────────────────────┐
    │                     WORKFLOW                             │
    │  (Orchestrates pipelines + lightweight validation)       │
    ├─────────────────────────────────────────────────────────┤
    │  Step.pipeline("ingest", "otc.ingest")   ──────────────►│──┐
    │  Step.lambda_("validate", validate_fn)                   │  │
    │  Step.pipeline("normalize", "otc.normalize") ──────────►│──┤
    │  Step.pipeline("summarize", "otc.summarize") ──────────►│──┤
    └─────────────────────────────────────────────────────────┘  │
                                                                  │
    ┌─────────────────────────────────────────────────────────┐  │
    │                 SPINE-CORE REGISTRY                      │◄─┘
    │  (Registered pipelines that do the actual work)          │
    ├─────────────────────────────────────────────────────────┤
    │  "otc.ingest"     → OTCIngestPipeline (adapted)          │
    │  "otc.normalize"  → OTCNormalizePipeline (adapted)       │
    │  "otc.summarize"  → OTCSummarizePipeline (adapted)       │
    └─────────────────────────────────────────────────────────┘
                              ▲
                              │ adapt_pipeline()
    ┌─────────────────────────────────────────────────────────┐
    │            INTERMEDIATE PIPELINES                        │
    │  (Your actual pipeline implementations)                  │
    ├─────────────────────────────────────────────────────────┤
    │  class OTCIngestPipeline(Pipeline):                      │
    │      def execute(self, params): ...                      │
    │                                                          │
    │  class OTCNormalizePipeline(Pipeline):                   │
    │      def execute(self, params): ...                      │
    └─────────────────────────────────────────────────────────┘

Key Rules:
    1. Pipelines do the ACTUAL WORK (fetch, parse, aggregate)
    2. Workflows ORCHESTRATE pipelines via Step.pipeline()
    3. Lambda steps do LIGHTWEIGHT validation/routing ONLY
    4. DON'T copy pipeline logic into workflow lambda steps!

Each example is designed to be run standalone:
    cd market-spine-intermediate
    uv run python -m examples.error_handling
    uv run python -m examples.otc_workflow
"""
