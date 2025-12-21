"""Runtime adapters for the Job Engine.

This package contains the runtime adapter protocol, types, concrete
adapters, and the ``JobEngine`` facade for executing container jobs
across different compute backends.

Architecture:

    .. code-block:: text

        spine.execution.runtimes
        ├── __init__.py      ← Public API (this file)
        ├── _types.py        ← RuntimeAdapter protocol + all types
        ├── _base.py         ← BaseRuntimeAdapter + StubRuntimeAdapter
        ├── validator.py     ← SpecValidator (pre-submit gate)
        ├── router.py        ← RuntimeAdapterRouter (adapter registry)
        ├── engine.py        ← JobEngine (central facade)
        ├── local_process.py ← LocalProcessAdapter (no Docker needed)
        ├── docker.py        ← DockerAdapter (MVP-1)
        └── (future)         ← k8s.py, podman.py, ecs.py, ...

    RuntimeAdapter is the canonical protocol for *container-level* execution.
    It is distinct from the Executor protocol (execution.executors.protocol),
    which handles *in-process* async work scheduling.

    RuntimeAdapter operates on ContainerJobSpec (image + resources).
    Executor operates on WorkSpec (name + params).

    .. mermaid::

        graph TB
            subgraph runtimes[\"spine.execution.runtimes\"]
                TYPES[\"_types.py<br/>Protocol + Types\"]
                BASE[\"_base.py<br/>BaseRuntimeAdapter\"]
                VALID[\"validator.py<br/>SpecValidator\"]
                ROUTER[\"router.py<br/>Router\"]
                ENGINE[\"engine.py<br/>JobEngine\"]
                LOCAL[\"local_process.py<br/>LocalProcessAdapter\"]
                DOCKER[\"docker.py<br/>DockerAdapter\"]
                STUB[\"StubRuntimeAdapter\"]
            end

            subgraph executors[\"spine.execution.executors\"]
                EP[\"protocol.py<br/>Executor Protocol\"]
                MEM[\"MemoryExecutor\"]
                CEL[\"CeleryExecutor\"]
            end

            TYPES --> BASE --> DOCKER & LOCAL & STUB
            TYPES --> VALID
            BASE --> ROUTER
            VALID & ROUTER --> ENGINE
            EP --> MEM & CEL

            style runtimes fill:#fce4ec,stroke:#c62828
            style executors fill:#e3f2fd,stroke:#1565c0

Modules:
    _types      - RuntimeAdapter protocol, ContainerJobSpec, RuntimeCapabilities,
                  RuntimeConstraints, JobError, JobArtifact, etc.
    _base       - BaseRuntimeAdapter with shared lifecycle logic
    validator   - SpecValidator (pre-submit capability/constraint checks)
    router      - RuntimeAdapterRouter (adapter registry and routing)
    engine      - JobEngine (central facade for job lifecycle)
    local_process - LocalProcessAdapter (subprocess-based, no Docker needed)
    docker      - Docker Engine adapter (MVP-1)
    stub        - StubRuntimeAdapter for testing

See Also:
    spine-workspace/prompts/04_project/spine-core/job-engine.prompt.md
    spine-core/docs/architecture/JOB_ENGINE_ARCHITECTURE.md

Manifesto:
    Runtime adapters abstract the "where" of execution — local
    process, Docker, Kubernetes, or Lambda — behind a single
    protocol.  Operations declare what they need; the engine
    picks the adapter.

Tags:
    spine-core, execution, runtimes, job-engine, adapter-protocol

Doc-Types:
    api-reference
"""

from spine.execution.runtimes._base import (
    BaseRuntimeAdapter,
    StubRuntimeAdapter,
)
from spine.execution.runtimes._types import (
    ContainerJobSpec,
    ErrorCategory,
    JobArtifact,
    JobError,
    JobStatus,
    ResourceRequirements,
    RuntimeAdapter,
    RuntimeCapabilities,
    RuntimeConstraints,
    RuntimeHealth,
    VolumeMount,
    job_external_name,
    redact_spec,
)
from spine.execution.runtimes.engine import JobEngine, SubmitResult
from spine.execution.runtimes.hot_reload import HotReloadAdapter
from spine.execution.runtimes.local_process import LocalProcessAdapter
from spine.execution.runtimes.mock_adapters import (
    FailingAdapter,
    FlakeyAdapter,
    LatencyAdapter,
    SequenceAdapter,
    SlowAdapter,
)
from spine.execution.runtimes.router import RuntimeAdapterRouter
from spine.execution.runtimes.validator import SpecValidator

__all__ = [
    # Types & Protocol
    "ContainerJobSpec",
    "ErrorCategory",
    "JobArtifact",
    "JobError",
    "JobStatus",
    "ResourceRequirements",
    "RuntimeAdapter",
    "RuntimeCapabilities",
    "RuntimeConstraints",
    "RuntimeHealth",
    "VolumeMount",
    # Utilities
    "job_external_name",
    "redact_spec",
    # Base classes
    "BaseRuntimeAdapter",
    "StubRuntimeAdapter",
    # Engine layer (Phase 4)
    "JobEngine",
    "HotReloadAdapter",
    "LocalProcessAdapter",
    "RuntimeAdapterRouter",
    "SpecValidator",
    "SubmitResult",
    # Mock adapters (testing)
    "FailingAdapter",
    "FlakeyAdapter",
    "LatencyAdapter",
    "SequenceAdapter",
    "SlowAdapter",
]
