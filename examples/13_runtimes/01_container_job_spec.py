#!/usr/bin/env python3
"""ContainerJobSpec — complete field reference with all 30+ parameters.

================================================================================
WHY THIS DEEP DIVE?
================================================================================

``ContainerJobSpec`` is the universal job description — every runtime adapter
receives one.  Understanding every field (and which ones actually work today)
is crucial for writing correct specs.

This example constructs specs with EVERY field documented and annotated.

================================================================================
FIELD INVENTORY (30+ fields)
================================================================================

::

    REQUIRED
    ────────
    name                str         Job name (must be unique per submission)
    image               str         Container image (ignored by LocalProcessAdapter)

    COMMAND
    ───────
    command             list[str]   Executable + args (subprocess argv)
    args                list[str]   Additional arguments appended to command
    working_dir         str|None    Working directory inside container/subprocess

    ENVIRONMENT
    ────────────
    env                 dict        Environment variables (key=value)
    secret_refs         list[str]   Secret names to inject (NOT YET IMPLEMENTED)

    RESOURCES
    ──────────
    resources           ResourceRequirements   CPU, memory, GPU limits
    volumes             list[VolumeMount]      Volume mounts
    artifacts_dir       str|None               Default: "/artifacts"

    CONTAINER FEATURES
    ───────────────────
    sidecars            list[SidecarSpec]      Sidecar containers
    init_containers     list[InitContainerSpec] Init containers
    ports               list[PortMapping]      Port mappings
    network             str|None               Docker network name

    SCHEDULING
    ───────────
    runtime             str|None    Pin to specific runtime adapter
    namespace           str|None    Kubernetes namespace
    node_selector       dict        K8s node selector labels
    priority            Literal     'realtime'|'high'|'normal'|'low'|'slow'
    lane                str         Execution lane (default: 'default')

    METADATA
    ─────────
    labels              dict        User-defined labels
    annotations         dict        User-defined annotations
    metadata            dict        Arbitrary metadata

    LIFECYCLE
    ──────────
    timeout_seconds     int         Kill after N seconds (default: 3600)
    max_retries         int         Retry on failure (default: 3)
    retry_delay_seconds int         Delay between retries (default: 60)

    COST
    ─────
    max_cost_usd        float|None  Budget cap (MVP-1: validation only)
    budget_tag          str|None    Cost allocation tag

    TRACING
    ────────
    idempotency_key     str|None    De-duplicate submissions
    correlation_id      str|None    Trace across services
    parent_execution_id str|None    Link parent/child jobs
    trigger_source      str         'api'|'cli'|'schedule'|'webhook'

    IMAGE
    ──────
    image_pull_policy   Literal     'always'|'if_not_present'|'never'
    image_pull_secret   str|None    Registry auth secret name


================================================================================
RUN IT
================================================================================

::

    python examples/13_runtimes/01_container_job_spec.py

"""

from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ResourceRequirements,
    VolumeMount,
    SidecarSpec,
    InitContainerSpec,
    PortMapping,
)


def demo_minimal_spec():
    """Minimum viable spec — just name + image."""
    print("=" * 70)
    print("SECTION 1 — Minimal Spec (2 required fields)")
    print("=" * 70)

    spec = ContainerJobSpec(name="hello", image="python:3.12-slim")
    print(f"  name:            {spec.name}")
    print(f"  image:           {spec.image}")
    print(f"  command:         {spec.command}")
    print(f"  timeout:         {spec.timeout_seconds}s")
    print(f"  max_retries:     {spec.max_retries}")
    print(f"  priority:        {spec.priority}")
    print(f"  lane:            {spec.lane}")
    print(f"  artifacts_dir:   {spec.artifacts_dir}")
    print(f"  trigger_source:  {spec.trigger_source}")
    print("  ✓ Minimal spec created with sensible defaults\n")


def demo_command_variants():
    """Different ways to specify commands."""
    print("=" * 70)
    print("SECTION 2 — Command Variants")
    print("=" * 70)

    # Simple command
    s1 = ContainerJobSpec(
        name="simple", image="python:3.12",
        command=["python", "-c", "print('hello')"],
    )
    print(f"  Simple:   command={s1.command}")

    # Command + args (args appended)
    s2 = ContainerJobSpec(
        name="with-args", image="python:3.12",
        command=["python"],
        args=["-c", "print('hello')"],
    )
    print(f"  With args: command={s2.command}, args={s2.args}")

    # Working directory
    s3 = ContainerJobSpec(
        name="cwd", image="python:3.12",
        command=["python", "main.py"],
        working_dir="/app",
    )
    print(f"  With cwd:  working_dir={s3.working_dir}")
    print("  ✓ Command variants shown\n")


def demo_environment():
    """Environment variables and secret references."""
    print("=" * 70)
    print("SECTION 3 — Environment & Secrets")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="env-demo", image="python:3.12",
        command=["python", "app.py"],
        env={
            "DATABASE_URL": "postgresql://localhost/mydb",
            "LOG_LEVEL": "DEBUG",
            "API_TIMEOUT": "30",
        },
        secret_refs=["db-password", "api-key"],  # NOT YET IMPLEMENTED
    )
    print(f"  env variables:  {len(spec.env)} defined")
    for k, v in spec.env.items():
        print(f"    {k}={v}")
    print(f"  secret_refs:    {spec.secret_refs}")
    print("  ⚠ NOTE: secret_refs are defined in the spec but NOT")
    print("    yet resolved by any adapter. See CONTAINER_EXECUTION_AUDIT.md")
    print("  ✓ Environment configured\n")


def demo_resources():
    """CPU, memory, and GPU resource requirements."""
    print("=" * 70)
    print("SECTION 4 — Resource Requirements")
    print("=" * 70)

    # Default resources
    s1 = ContainerJobSpec(name="default", image="python:3.12")
    print(f"  Default resources: {s1.resources}")

    # Custom resources
    s2 = ContainerJobSpec(
        name="heavy", image="nvidia/cuda:12.0",
        resources=ResourceRequirements(
            cpu="4.0",
            memory="8Gi",
            gpu=1,
        ),
    )
    print(f"  Custom:  cpu={s2.resources.cpu}, mem={s2.resources.memory}, gpu={s2.resources.gpu}")
    print("  ⚠ NOTE: Resource limits are spec-only — LocalProcessAdapter")
    print("    ignores them. Docker/K8s adapters (TBD) will enforce them.")
    print("  ✓ Resources configured\n")


def demo_volumes_and_artifacts():
    """Volume mounts and artifact directory."""
    print("=" * 70)
    print("SECTION 5 — Volumes & Artifacts")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="data-job", image="python:3.12",
        command=["python", "process.py"],
        volumes=[
            VolumeMount(name="input", mount_path="/data/input", host_path="/mnt/raw"),
            VolumeMount(name="output", mount_path="/data/output", host_path="/mnt/processed"),
        ],
        artifacts_dir="/outputs",  # Override default "/artifacts"
    )
    print(f"  Volumes ({len(spec.volumes)}):")
    for v in spec.volumes:
        print(f"    {v.name}: {v.host_path} → {v.mount_path}")
    print(f"  artifacts_dir:  {spec.artifacts_dir}")
    print("  ⚠ NOTE: Volumes require supports_volumes capability.")
    print("    LocalProcessAdapter does NOT support volumes.")
    print("  ✓ Volumes configured\n")


def demo_scheduling():
    """Runtime pinning, priority, and lane configuration."""
    print("=" * 70)
    print("SECTION 6 — Scheduling (Runtime, Priority, Lane)")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="scheduled-job", image="python:3.12",
        command=["python", "batch.py"],
        runtime="local",           # Pin to specific adapter
        priority="high",           # realtime > high > normal > low > slow
        lane="batch-processing",   # Execution lane
        namespace="production",    # K8s namespace (ignored by local)
        node_selector={"gpu": "true", "zone": "us-east-1a"},
    )
    print(f"  runtime:        {spec.runtime}")
    print(f"  priority:       {spec.priority}")
    print(f"  lane:           {spec.lane}")
    print(f"  namespace:      {spec.namespace}")
    print(f"  node_selector:  {spec.node_selector}")
    print("  ✓ Scheduling configured\n")


def demo_lifecycle():
    """Timeout, retry, and cost controls."""
    print("=" * 70)
    print("SECTION 7 — Lifecycle (Timeout, Retry, Cost)")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="reliable-job", image="python:3.12",
        command=["python", "etl.py"],
        timeout_seconds=1800,      # 30 minutes
        max_retries=5,
        retry_delay_seconds=120,   # 2 minutes between retries
        max_cost_usd=10.0,
        budget_tag="data-team",
    )
    print(f"  timeout:          {spec.timeout_seconds}s ({spec.timeout_seconds // 60}m)")
    print(f"  max_retries:      {spec.max_retries}")
    print(f"  retry_delay:      {spec.retry_delay_seconds}s")
    print(f"  max_cost_usd:     ${spec.max_cost_usd}")
    print(f"  budget_tag:       {spec.budget_tag}")
    print("  ⚠ NOTE: max_cost_usd is validated (must be ≥ 0) but")
    print("    actual cost estimation not yet implemented.")
    print("  ✓ Lifecycle configured\n")


def demo_tracing():
    """Idempotency, correlation, and parent-child tracing."""
    print("=" * 70)
    print("SECTION 8 — Tracing (Idempotency, Correlation, Parent)")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="traceable-job", image="python:3.12",
        command=["python", "step2.py"],
        idempotency_key="operation-run-2026-02-16-step2",
        correlation_id="trace-abc-123",
        parent_execution_id="exec-parent-456",
        trigger_source="schedule",
    )
    print(f"  idempotency_key:     {spec.idempotency_key}")
    print(f"  correlation_id:      {spec.correlation_id}")
    print(f"  parent_execution_id: {spec.parent_execution_id}")
    print(f"  trigger_source:      {spec.trigger_source}")
    print("  ✓ Tracing configured\n")


def demo_metadata():
    """Labels, annotations, and metadata."""
    print("=" * 70)
    print("SECTION 9 — Metadata (Labels, Annotations)")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="labeled-job", image="python:3.12",
        command=["python", "process.py"],
        labels={"team": "data-eng", "env": "staging", "version": "2.1"},
        annotations={"description": "Daily ETL for financial data"},
        metadata={"source_system": "SEC EDGAR", "filing_type": "10-K"},
    )
    print(f"  labels ({len(spec.labels)}):")
    for k, v in spec.labels.items():
        print(f"    {k}={v}")
    print(f"  annotations:    {spec.annotations}")
    print(f"  metadata:       {spec.metadata}")
    print("  ✓ Metadata configured\n")


def demo_image_settings():
    """Image pull policy and secrets."""
    print("=" * 70)
    print("SECTION 10 — Image Settings")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="private-image", image="registry.internal/ml-model:v3",
        command=["python", "predict.py"],
        image_pull_policy="always",
        image_pull_secret="registry-creds",
    )
    print(f"  image:             {spec.image}")
    print(f"  image_pull_policy: {spec.image_pull_policy}")
    print(f"  image_pull_secret: {spec.image_pull_secret}")
    print("  ⚠ NOTE: Image settings only relevant for Docker/K8s adapters.")
    print("    LocalProcessAdapter ignores image entirely.")
    print("  ✓ Image settings configured\n")


def demo_spec_hash():
    """Compute a deterministic hash of the spec for dedup."""
    print("=" * 70)
    print("SECTION 11 — Spec Hash (Deterministic)")
    print("=" * 70)

    spec = ContainerJobSpec(
        name="hash-test", image="python:3.12",
        command=["echo", "hello"],
    )
    hash1 = spec.spec_hash()
    hash2 = spec.spec_hash()
    print(f"  Hash 1: {hash1}")
    print(f"  Hash 2: {hash2}")
    assert hash1 == hash2, "Hashes should be deterministic!"

    # Different spec → different hash
    spec2 = ContainerJobSpec(
        name="hash-test", image="python:3.12",
        command=["echo", "world"],
    )
    hash3 = spec2.spec_hash()
    print(f"  Hash 3: {hash3} (different command)")
    assert hash1 != hash3, "Different specs should have different hashes!"
    print("  ✓ Spec hashing is deterministic and unique\n")


def demo_full_spec():
    """Complete spec with ALL fields populated."""
    print("=" * 70)
    print("SECTION 12 — Full Spec (ALL Fields)")
    print("=" * 70)

    spec = ContainerJobSpec(
        # Required
        name="full-example",
        image="python:3.12-slim",
        # Command
        command=["python", "-c"],
        args=["print('hello from full spec')"],
        working_dir="/app",
        # Environment
        env={"ENV": "production", "DEBUG": "false"},
        secret_refs=["api-key"],
        # Resources
        resources=ResourceRequirements(cpu="2.0", memory="4Gi", gpu=0),
        volumes=[VolumeMount(name="data", mount_path="/data", host_path="/mnt/data")],
        artifacts_dir="/outputs",
        # Container features
        sidecars=[SidecarSpec(name="logger", image="fluent/fluentd:v1.16")],
        init_containers=[InitContainerSpec(name="migrate", image="flyway:10", command=["flyway", "migrate"])],
        ports=[PortMapping(container_port=8080, host_port=8080)],
        network="spine-net",
        # Scheduling
        runtime="local",
        namespace="default",
        node_selector={"tier": "compute"},
        priority="high",
        lane="etl",
        # Metadata
        labels={"team": "data", "cost-center": "engineering"},
        annotations={"owner": "data-eng@company.com"},
        metadata={"operation_version": "3.2.1"},
        # Lifecycle
        timeout_seconds=1800,
        max_retries=3,
        retry_delay_seconds=60,
        max_cost_usd=5.0,
        budget_tag="data-team",
        # Tracing
        idempotency_key="daily-etl-2026-02-16",
        correlation_id="trace-123",
        parent_execution_id=None,
        trigger_source="schedule",
        # Image
        image_pull_policy="if_not_present",
        image_pull_secret=None,
    )

    # Count populated fields
    from dataclasses import fields
    populated = sum(1 for f in fields(spec) if getattr(spec, f.name) is not None)
    print(f"  Fields populated: {populated}/{len(fields(spec))}")
    print(f"  Spec hash:        {spec.spec_hash()[:16]}...")
    print("  ✓ Full spec created with all fields\n")


# ── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_minimal_spec()
    demo_command_variants()
    demo_environment()
    demo_resources()
    demo_volumes_and_artifacts()
    demo_scheduling()
    demo_lifecycle()
    demo_tracing()
    demo_metadata()
    demo_image_settings()
    demo_spec_hash()
    demo_full_spec()
    print("=" * 70)
    print("ALL SECTIONS PASSED ✓")
    print("=" * 70)
