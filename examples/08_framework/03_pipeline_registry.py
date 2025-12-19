"""
Pipeline Registry — Registering and discovering pipelines.

WHY A REGISTRY
──────────────
Without a registry, adding a new pipeline means editing a dispatch
table somewhere.  The registry lets you decorate a class with
@register_pipeline("name") and it's instantly available to
PipelineRunner, CLI commands, API endpoints, **and the Workflow
engine** — Step.pipeline("name") resolves through this same registry.

TWO REGISTRIES IN SPINE
───────────────────────
    Registry               Module               Stores
    ────────────────────── ──────────────────── ──────────────────────
    Pipeline Registry      spine.framework      Pipeline subclasses
    Workflow Registry      spine.orchestration   Workflow definitions

    @register_pipeline("finra.otc.ingest")  ← this example
    @register_workflow("finra.weekly")       ← 04_orchestration/12

    Both use the same pattern: dotted names, decorator registration,
    KeyError on lookup failure, clear_*() for test isolation.

ARCHITECTURE
────────────
    @register_pipeline("finra.otc.ingest")
    class OTCIngestPipeline(Pipeline): ...
         │
         ▼
    ┌────────────────────────────────────┐
    │ Global Pipeline Registry           │
    │  {"finra.otc.ingest": OTCIngest..} │
    │  {"finra.otc.normalize": OTCNorm..}│
    │  {"sec.filings.ingest": SECFili..} │
    └─────────────┬──────────────────────┘
                  │
       ┌──────────┼────────────┐
       ▼          ▼            ▼
    get_pipeline  list_pipelines  clear_registry
    ("name")      ()               ()
       │
       └──── also used by ────▶  Step.pipeline("name")
                                  inside Workflows

    list_pipelines() enables domain-prefix discovery:
    finra_pipes = [p for p in list_pipelines() if p.startswith("finra.")]

BEST PRACTICES
──────────────
• Use dotted, lowercase names: "domain.subsystem.verb".
• Duplicate names raise ValueError — catch at startup.
• Call clear_registry() in tests to avoid cross-test leaks.
• Use list_pipelines() to build dynamic CLI menus.
• Register pipelines early — before building Workflows that reference them.

Run: python examples/08_framework/03_pipeline_registry.py

See Also:
    01_pipeline_basics — Pipeline base class
    02_pipeline_runner — executing registered pipelines
    04_orchestration/10_workflow_registry_yaml — the Workflow registry
"""

from datetime import datetime, timezone

from spine.framework import (
    Pipeline,
    PipelineResult,
    PipelineStatus,
    register_pipeline,
    get_pipeline,
    list_pipelines,
    clear_registry,
)


def main():
    """Demonstrate pipeline registry for discovery."""
    print("=" * 60)
    print("Pipeline Registry - Registration and Discovery")
    print("=" * 60)
    
    # Clear registry for clean demo
    clear_registry()
    
    print("\n1. Registering pipelines with decorator...")
    
    @register_pipeline("finra.otc.ingest")
    class OTCIngestPipeline(Pipeline):
        """Ingest OTC transparency data."""
        
        name = "finra.otc.ingest"
        description = "Ingest FINRA OTC transparency data"
        
        def run(self) -> PipelineResult:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                metrics={"rows": 1000},
            )
    
    @register_pipeline("finra.otc.normalize")
    class OTCNormalizePipeline(Pipeline):
        """Normalize OTC data."""
        
        name = "finra.otc.normalize"
        description = "Normalize FINRA OTC data"
        
        def run(self) -> PipelineResult:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
    
    @register_pipeline("sec.filings.ingest")
    class SECFilingsPipeline(Pipeline):
        """Ingest SEC filings."""
        
        name = "sec.filings.ingest"
        description = "Ingest SEC EDGAR filings"
        
        def run(self) -> PipelineResult:
            return PipelineResult(
                status=PipelineStatus.COMPLETED,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
    
    print("   ✓ Registered 3 pipelines")
    
    print("\n2. Listing registered pipelines...")
    
    pipelines = list_pipelines()
    print(f"   Found {len(pipelines)} pipelines:")
    for name in pipelines:
        print(f"     - {name}")
    
    print("\n3. Getting a pipeline by name...")
    
    pipeline_cls = get_pipeline("finra.otc.ingest")
    print(f"   Got: {pipeline_cls.__name__}")
    print(f"   Description: {pipeline_cls.description}")
    
    # Instantiate and run
    pipeline = pipeline_cls(params={"tier": "NMS_TIER_1"})
    result = pipeline.run()
    print(f"   Executed: {result.status.value}")
    
    print("\n4. Handling unknown pipelines...")
    
    try:
        get_pipeline("nonexistent.pipeline")
    except KeyError as e:
        print(f"   ✓ KeyError raised for unknown pipeline")
        print(f"     {e}")
    
    print("\n5. Preventing duplicate registration...")
    
    try:
        @register_pipeline("finra.otc.ingest")  # Already registered!
        class DuplicatePipeline(Pipeline):
            def run(self):
                pass
    except ValueError as e:
        print(f"   ✓ ValueError raised for duplicate")
        print(f"     {e}")
    
    print("\n6. Pipeline discovery pattern...")
    
    # Find all pipelines in a domain
    finra_pipelines = [p for p in list_pipelines() if p.startswith("finra.")]
    sec_pipelines = [p for p in list_pipelines() if p.startswith("sec.")]
    
    print(f"   FINRA domain: {finra_pipelines}")
    print(f"   SEC domain: {sec_pipelines}")
    
    print("\n7. Dynamic pipeline execution...")
    
    # Execute all pipelines in a domain
    print("   Running all FINRA pipelines:")
    for name in finra_pipelines:
        cls = get_pipeline(name)
        instance = cls(params={})
        result = instance.run()
        print(f"     {name}: {result.status.value}")
    
    print("\n8. Registry cleanup...")
    
    clear_registry()
    print(f"   Cleared registry")
    print(f"   Pipelines remaining: {len(list_pipelines())}")
    
    print("\n" + "=" * 60)
    print("Pipeline Registry demo complete!")


if __name__ == "__main__":
    main()
