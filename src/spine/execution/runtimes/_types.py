"""Runtime adapter types and protocols for the Job Engine.

This module defines the canonical abstractions for container-level execution:

- RuntimeAdapter: Protocol for submitting and managing container jobs
- ContainerJobSpec: Full spec for a container job (image, resources, env, etc.)
- RuntimeCapabilities: Boolean feature flags per runtime
- RuntimeConstraints: Numeric limits per runtime
- JobError: Structured error taxonomy for retry decisions
- JobStatus: Observed status from a runtime adapter
- JobArtifact: Output file metadata
- RuntimeHealth: Runtime reachability check result

Design Notes:
    RuntimeAdapter is for *external container lifecycles* (Docker, K8s, ECS).
    Executor (execution.executors.protocol) is for *in-process async work*.
    These are deliberately separate protocols at different abstraction levels.

    ContainerJobSpec extends the WorkSpec concept with container-native fields.
    It does NOT inherit from WorkSpec — it's a parallel spec for a different
    execution model.

Architecture:

    .. code-block:: text

        ┌─────────────────────────────────────────────────────────────┐
        │                    _types.py Module Map                     │
        ├─────────────────────────────────────────────────────────────┤
        │                                                             │
        │  ┌─────────────────┐    ┌──────────────────────────────┐   │
        │  │  ErrorCategory  │    │     ContainerJobSpec          │   │
        │  │  (Enum: 10 cats)│    │     name, image, command      │   │
        │  └────────┬────────┘    │     env, resources, volumes   │   │
        │           │             │     timeout, budget, labels    │   │
        │  ┌────────▼────────┐    │     + to_dict(), spec_hash()  │   │
        │  │    JobError     │    └──────────┬───────────────────┘   │
        │  │  (Exception +   │               │                       │
        │  │   dataclass)    │    ┌──────────▼──────────────────┐    │
        │  └─────────────────┘    │  redact_spec(spec) → dict   │    │
        │                         │  job_external_name() → str   │    │
        │  ┌─────────────────┐    └─────────────────────────────┘    │
        │  │ RuntimeAdapter  │                                        │
        │  │  (Protocol)     │    ┌─────────────────────────────┐    │
        │  │  7 async methods│    │  RuntimeCapabilities        │    │
        │  └─────────────────┘    │  (boolean feature flags)    │    │
        │                         ├─────────────────────────────┤    │
        │  ┌─────────────────┐    │  RuntimeConstraints         │    │
        │  │   JobStatus     │    │  (numeric limits)           │    │
        │  │   JobArtifact   │    │  + validate_spec() → []     │    │
        │  │   RuntimeHealth │    └─────────────────────────────┘    │
        │  └─────────────────┘                                       │
        └─────────────────────────────────────────────────────────────┘

    .. mermaid::

        graph LR
            CJS[ContainerJobSpec] -->|"submitted to"| RA[RuntimeAdapter]
            RA -->|"returns"| JS[JobStatus]
            RA -->|"raises"| JE[JobError]
            RA -->|"produces"| JA[JobArtifact]
            RA -->|"reports"| RH[RuntimeHealth]
            RC[RuntimeCapabilities] -->|"checked before"| RA
            RCO[RuntimeConstraints] -->|"validated against"| RA

See Also:
    execution.spec.WorkSpec — In-process work specification
    execution.executors.protocol.Executor — In-process async protocol
    execution.models.ExecutionStatus — Canonical status enum
    execution.models.EventType — Canonical event type enum
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, AsyncIterator, Literal, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


def _generate_id() -> str:
    """Generate a unique ID for an entity."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------

class ErrorCategory(str, Enum):
    """Normalized error categories for structured retry decisions.

    Every job error is classified into one of these categories.
    Retry logic uses ``category`` + ``retryable`` instead of message parsing.
    The UI groups errors by category for dashboards.

    .. mermaid::

        graph TB
            JE[JobError] --> AUTH[AUTH - credentials]
            JE --> QUOTA[QUOTA - resource limits]
            JE --> NF[NOT_FOUND - image missing]
            JE --> RU[RUNTIME_UNAVAILABLE]
            JE --> IP[IMAGE_PULL - pull failed]
            JE --> OOM[OOM - memory killed]
            JE --> TO[TIMEOUT - deadline exceeded]
            JE --> UC[USER_CODE - non-zero exit]
            JE --> VAL[VALIDATION - spec invalid]
            JE --> UNK[UNKNOWN - unclassified]

    Retryable by default: AUTH, RUNTIME_UNAVAILABLE, IMAGE_PULL, UNKNOWN.
    Non-retryable by default: QUOTA, NOT_FOUND, OOM, TIMEOUT, USER_CODE, VALIDATION.
    """

    AUTH = "auth"                           # Credentials invalid/expired
    QUOTA = "quota"                         # Resource quota exceeded
    NOT_FOUND = "not_found"                 # Image, runtime, or resource not found
    RUNTIME_UNAVAILABLE = "runtime_unavailable"  # Runtime unreachable
    IMAGE_PULL = "image_pull"               # Image pull failed
    OOM = "oom"                             # Out of memory killed
    TIMEOUT = "timeout"                     # Exceeded timeout
    USER_CODE = "user_code"                 # Non-zero exit from user code
    VALIDATION = "validation"               # Spec validation failed
    UNKNOWN = "unknown"                     # Unclassified


@dataclass(frozen=True)
class JobError(Exception):
    """Structured error from a job execution.

    Both a dataclass AND an Exception — can be raised and caught.
    Immutable after creation. Retry decisions use ``category`` + ``retryable``,
    not string matching on ``message``.

    Example:
        >>> err = JobError(
        ...     category=ErrorCategory.OOM,
        ...     message="Container killed: OOM (used 4096MB, limit 2048MB)",
        ...     retryable=False,
        ...     exit_code=137,
        ...     runtime="docker",
        ... )
        >>> err.retryable
        False
        >>> raise err  # Can be raised
    """

    category: ErrorCategory
    message: str
    retryable: bool
    provider_code: str | None = None    # e.g., "ErrImagePull", "CannotPullContainer"
    exit_code: int | None = None
    runtime: str | None = None

    def __str__(self) -> str:
        """Human-readable representation."""
        parts = [f"[{self.category.value}] {self.message}"]
        if self.provider_code:
            parts.append(f"(provider: {self.provider_code})")
        if self.exit_code is not None:
            parts.append(f"(exit: {self.exit_code})")
        return " ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON storage."""
        return {
            "category": self.category.value,
            "message": self.message,
            "retryable": self.retryable,
            "provider_code": self.provider_code,
            "exit_code": self.exit_code,
            "runtime": self.runtime,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JobError:
        """Deserialize from JSON storage."""
        return cls(
            category=ErrorCategory(data["category"]),
            message=data["message"],
            retryable=data["retryable"],
            provider_code=data.get("provider_code"),
            exit_code=data.get("exit_code"),
            runtime=data.get("runtime"),
        )

    @classmethod
    def unknown(cls, message: str, *, runtime: str | None = None) -> JobError:
        """Create an UNKNOWN error (retryable by default)."""
        return cls(
            category=ErrorCategory.UNKNOWN,
            message=message,
            retryable=True,
            runtime=runtime,
        )


# ---------------------------------------------------------------------------
# Resource specifications
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceRequirements:
    """CPU, memory, and GPU requirements for a container.

    All fields are optional — adapters fill in defaults from runtime config.

    Example:
        >>> resources = ResourceRequirements(cpu="2.0", memory="4Gi", gpu=1)
    """

    cpu: str | None = None             # K8s-style: "0.5", "2.0"
    memory: str | None = None          # K8s-style: "256Mi", "4Gi"
    gpu: int | None = None             # Number of GPUs
    gpu_type: str | None = None        # "nvidia.com/gpu", "amd.com/gpu"
    ephemeral_storage: str | None = None  # Scratch disk: "10Gi"

    def to_dict(self) -> dict[str, Any]:
        """Serialize non-None fields."""
        return {k: v for k, v in {
            "cpu": self.cpu,
            "memory": self.memory,
            "gpu": self.gpu,
            "gpu_type": self.gpu_type,
            "ephemeral_storage": self.ephemeral_storage,
        }.items() if v is not None}


@dataclass(frozen=True)
class VolumeMount:
    """Volume mount specification.

    Adapters translate this into their native volume model:
    - Docker: bind mount or named volume
    - K8s: PVC, emptyDir, hostPath
    - ECS: EFS mount point
    """

    name: str
    mount_path: str                     # Container-internal path
    host_path: str | None = None        # For bind mounts (Docker, Podman)
    read_only: bool = False
    size: str | None = None             # Requested size: "10Gi"


@dataclass(frozen=True)
class PortMapping:
    """Port mapping for exposed container ports."""

    container_port: int
    host_port: int | None = None        # None = random assignment
    protocol: Literal["tcp", "udp"] = "tcp"


@dataclass(frozen=True)
class SidecarSpec:
    """Sidecar container definition.

    Sidecars run alongside the main container (K8s pods, ECS task definitions).
    Docker/Podman use podman pods or docker-compose.
    """

    name: str
    image: str
    command: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)
    ports: list[PortMapping] = field(default_factory=list)


@dataclass(frozen=True)
class InitContainerSpec:
    """Init container that runs before the main container."""

    name: str
    image: str
    command: list[str] | None = None
    env: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ContainerJobSpec — the main spec
# ---------------------------------------------------------------------------

@dataclass
class ContainerJobSpec:
    """Full specification for a container job.

    This is the canonical input to ``RuntimeAdapter.submit()``. It describes
    *what* to run (image, command), *how much* (resources), and *where*
    (runtime hint, namespace). The adapter translates this into its native
    format (docker run, K8s Job YAML, ECS RunTask, etc.).

    .. code-block:: text

        ContainerJobSpec
        ├── Identity: name, image
        ├── What: command, args, working_dir
        ├── Environment: env, secret_refs
        ├── Resources: cpu, memory, gpu
        ├── Storage: volumes, artifacts_dir
        ├── Multi-container: sidecars, init_containers
        ├── Networking: ports, network
        ├── Scheduling: runtime, namespace, node_selector, labels
        ├── Policy: timeout, max_retries, retry_delay
        ├── Budget: max_cost_usd, budget_tag
        ├── Tracking: idempotency_key, correlation_id, parent_execution_id
        └── Image: image_pull_policy, image_pull_secret

    .. mermaid::

        flowchart LR
            SPEC[ContainerJobSpec] --> VAL{Validator}
            VAL -->|pass| RED[redact_spec]
            RED --> DB[(core_executions)]
            VAL -->|pass| ROUTER[Router]
            ROUTER --> ADAPTER[RuntimeAdapter.submit]
            ADAPTER --> REF[external_ref]

    Example:
        >>> spec = ContainerJobSpec(
        ...     name="finra-otc-ingest",
        ...     image="spine-worker:latest",
        ...     command=["python", "-m", "spine.pipelines.finra_otc"],
        ...     resources=ResourceRequirements(cpu="1.0", memory="2Gi"),
        ...     timeout_seconds=1800,
        ... )
    """

    # === Identity ===
    name: str
    """Human-readable job name (also used for deterministic external naming)."""

    image: str
    """OCI image reference: registry/repo:tag or repo@sha256:digest."""

    # === What to run ===
    command: list[str] | None = None
    """Container command override (ENTRYPOINT equivalent)."""

    args: list[str] | None = None
    """Container args override (CMD equivalent)."""

    working_dir: str | None = None
    """Working directory inside the container."""

    # === Environment ===
    env: dict[str, str] = field(default_factory=dict)
    """Environment variables. Secrets should use secret_refs instead."""

    secret_refs: list[str] = field(default_factory=list)
    """References to secrets (resolved by CredentialBroker at submit time).
    Format is adapter-specific: Vault path, SSM parameter name, etc."""

    # === Resources ===
    resources: ResourceRequirements = field(default_factory=ResourceRequirements)
    """CPU, memory, GPU requirements."""

    # === Storage ===
    volumes: list[VolumeMount] = field(default_factory=list)
    """Volume mounts (bind mounts, PVCs, etc.)."""

    artifacts_dir: str | None = "/artifacts"
    """Container-internal directory for output artifacts. None = no artifacts."""

    # === Multi-container ===
    sidecars: list[SidecarSpec] = field(default_factory=list)
    """Sidecar containers (K8s pods, ECS task definitions)."""

    init_containers: list[InitContainerSpec] = field(default_factory=list)
    """Init containers that run before the main container."""

    # === Networking ===
    ports: list[PortMapping] = field(default_factory=list)
    """Exposed ports (for sidecars, debugging, or service endpoints)."""

    network: str | None = None
    """Network hint: 'host', 'bridge', or a named network. Adapter translates."""

    # === Scheduling ===
    runtime: str | None = None
    """Preferred runtime: 'docker', 'k8s', 'ecs', etc. None = router picks."""

    namespace: str | None = None
    """K8s namespace, ECS cluster, etc."""

    node_selector: dict[str, str] = field(default_factory=dict)
    """Node selection hints (K8s: nodeSelector, ECS: placement constraints)."""

    labels: dict[str, str] = field(default_factory=dict)
    """Labels/tags applied to the runtime resource."""

    annotations: dict[str, str] = field(default_factory=dict)
    """Annotations (K8s) or additional metadata."""

    # === Execution policy ===
    timeout_seconds: int = 3600
    """Maximum execution time. Runtime validates against its constraints."""

    max_retries: int = 3
    """Maximum retry attempts on failure."""

    retry_delay_seconds: int = 60
    """Delay between retries."""

    # === Budget ===
    max_cost_usd: float | None = None
    """Budget gate — reject if estimated cost exceeds this."""

    budget_tag: str | None = None
    """Cost attribution tag for grouping costs."""

    # === Tracking ===
    idempotency_key: str | None = None
    """Prevent duplicate job execution."""

    correlation_id: str | None = None
    """Link related jobs (e.g., all steps in a workflow)."""

    parent_execution_id: str | None = None
    """For workflow steps, the execution_id of the parent workflow."""

    trigger_source: str = "api"
    """How this job was triggered: api, cli, schedule, workflow, etc."""

    priority: Literal["realtime", "high", "normal", "low", "slow"] = "normal"
    """Priority for queue ordering."""

    lane: str = "default"
    """Queue/lane name for routing (e.g., 'gpu', 'cpu', 'io-bound')."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """Additional context (tenant_id, user_id, trace_id, etc.)."""

    # === Image pull ===
    image_pull_policy: Literal["always", "if_not_present", "never"] = "if_not_present"
    """When to pull the image."""

    image_pull_secret: str | None = None
    """Secret ref for private registry authentication."""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        d: dict[str, Any] = {
            "name": self.name,
            "image": self.image,
        }
        if self.command:
            d["command"] = self.command
        if self.args:
            d["args"] = self.args
        if self.working_dir:
            d["working_dir"] = self.working_dir
        if self.env:
            d["env"] = dict(self.env)
        if self.secret_refs:
            d["secret_refs"] = list(self.secret_refs)
        if self.resources != ResourceRequirements():
            d["resources"] = self.resources.to_dict()
        if self.volumes:
            d["volumes"] = [
                {"name": v.name, "mount_path": v.mount_path,
                 "host_path": v.host_path, "read_only": v.read_only,
                 "size": v.size}
                for v in self.volumes
            ]
        if self.artifacts_dir and self.artifacts_dir != "/artifacts":
            d["artifacts_dir"] = self.artifacts_dir
        if self.sidecars:
            d["sidecars"] = [
                {"name": s.name, "image": s.image, "command": s.command,
                 "env": s.env}
                for s in self.sidecars
            ]
        if self.init_containers:
            d["init_containers"] = [
                {"name": c.name, "image": c.image, "command": c.command,
                 "env": c.env}
                for c in self.init_containers
            ]
        if self.runtime:
            d["runtime"] = self.runtime
        if self.namespace:
            d["namespace"] = self.namespace
        if self.timeout_seconds != 3600:
            d["timeout_seconds"] = self.timeout_seconds
        if self.max_retries != 3:
            d["max_retries"] = self.max_retries
        if self.max_cost_usd is not None:
            d["max_cost_usd"] = self.max_cost_usd
        if self.budget_tag:
            d["budget_tag"] = self.budget_tag
        if self.idempotency_key:
            d["idempotency_key"] = self.idempotency_key
        if self.correlation_id:
            d["correlation_id"] = self.correlation_id
        if self.parent_execution_id:
            d["parent_execution_id"] = self.parent_execution_id
        if self.priority != "normal":
            d["priority"] = self.priority
        if self.lane != "default":
            d["lane"] = self.lane
        if self.labels:
            d["labels"] = dict(self.labels)
        if self.annotations:
            d["annotations"] = dict(self.annotations)
        if self.metadata:
            d["metadata"] = dict(self.metadata)
        d["trigger_source"] = self.trigger_source
        d["image_pull_policy"] = self.image_pull_policy
        return d

    def spec_hash(self) -> str:
        """SHA-256 hash of the canonical spec for integrity verification."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Spec redaction
# ---------------------------------------------------------------------------

_SENSITIVE_ENV_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(password|secret|token|key|credential|api.key|auth)"),
]

_REDACTED = "***REDACTED***"


def redact_spec(spec: ContainerJobSpec) -> dict[str, Any]:
    """Create a redacted copy of the spec safe for database persistence.

    - Env var values matching sensitive patterns are masked
    - ``image_pull_secret`` is removed
    - ``secret_refs`` values are masked but keys remain for audit trail

    The original spec is not modified.

    .. code-block:: text

        Input ContainerJobSpec              Output dict (redacted)
        ┌───────────────────┐               ┌───────────────────┐
        │ DB_PASSWORD=hunter2│    ────►      │ DB_PASSWORD=***   │
        │ LOG_LEVEL=debug    │               │ LOG_LEVEL=debug   │
        │ API_KEY=sk-abc123  │               │ API_KEY=***       │
        │ image_pull_secret  │               │ (removed)         │
        │ secret_refs=[...]  │               │ secret_refs=[***] │
        └───────────────────┘               └───────────────────┘

    .. mermaid::

        flowchart LR
            A[ContainerJobSpec] -->|to_dict| B[Full dict]
            B -->|mask sensitive env| C[Redacted dict]
            B -->|SHA-256| D[spec_hash]
            C --> DB[(Database)]
            D --> DB

    Example:
        >>> spec = ContainerJobSpec(
        ...     name="test", image="alpine",
        ...     env={"DB_PASSWORD": "hunter2", "LOG_LEVEL": "debug"},
        ... )
        >>> redacted = redact_spec(spec)
        >>> redacted["env"]["DB_PASSWORD"]
        '***REDACTED***'
        >>> redacted["env"]["LOG_LEVEL"]
        'debug'
    """
    d = spec.to_dict()

    # Redact sensitive env values
    if "env" in d:
        for key in d["env"]:
            if any(p.search(key) for p in _SENSITIVE_ENV_PATTERNS):
                d["env"][key] = _REDACTED

    # Remove image pull secret value
    d.pop("image_pull_secret", None)

    # Mask secret_refs (keep names for audit trail)
    if "secret_refs" in d:
        d["secret_refs"] = [_REDACTED] * len(d["secret_refs"])

    return d


# ---------------------------------------------------------------------------
# Deterministic naming
# ---------------------------------------------------------------------------

_SLUG_PATTERN = re.compile(r"[^a-z0-9-]")


def job_external_name(execution_id: str, work_name: str) -> str:
    """Generate deterministic external resource name.

    Format: ``spine-{exec_id_prefix}-{slugified_work_name}``
    Max length: 63 chars (K8s label constraint)

    Example:
        >>> job_external_name("a1b2c3d4-5678-...", "finra-otc-ingest")
        'spine-a1b2c3d4-finra-otc-ingest'
        >>> job_external_name("abc", "My Long Pipeline Name!!!")
        'spine-abc-----m-my-long-pipeline-name---'
    """
    prefix = execution_id[:8]
    slug = _SLUG_PATTERN.sub("-", work_name.lower())[:40]
    # Strip leading/trailing hyphens from slug
    slug = slug.strip("-") or "job"
    name = f"spine-{prefix}-{slug}"
    return name[:63]


# ---------------------------------------------------------------------------
# Runtime capabilities and constraints
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeCapabilities:
    """Boolean feature flags for a runtime adapter.

    The validator checks these before submission. If a spec requires GPU
    but the runtime doesn't support it, submission is rejected with a clear
    error message.

    .. code-block:: text

        Capability Check Matrix (example)
        ┌──────────────────┬────────┬────────┬───────┬───────┐
        │ Capability        │ Docker │ Podman │  K8s  │  ECS  │
        ├──────────────────┼────────┼────────┼───────┼───────┤
        │ supports_gpu      │   ✓    │   ✓    │   ✓   │   ✓   │
        │ supports_volumes  │   ✓    │   ✓    │   ✓   │   ✓   │
        │ supports_sidecars │   ✓*   │   ✓*   │   ✓   │   ✓   │
        │ supports_spot     │   ✗    │   ✗    │   ✓   │   ✓   │
        │ supports_exec     │   ✓    │   ✓    │   ✓   │   ✓   │
        └──────────────────┴────────┴────────┴───────┴───────┘
    """

    supports_gpu: bool = False
    supports_volumes: bool = False
    supports_sidecars: bool = False
    supports_init_containers: bool = False
    supports_log_streaming: bool = False
    supports_exec_into: bool = False       # Exec into running container
    supports_spot: bool = False            # Spot/preemptible instances
    supports_artifacts: bool = True        # Can collect output files
    supports_health_check: bool = False    # Container health checks

    def to_dict(self) -> dict[str, bool]:
        """Serialize all capabilities."""
        return {
            "supports_gpu": self.supports_gpu,
            "supports_volumes": self.supports_volumes,
            "supports_sidecars": self.supports_sidecars,
            "supports_init_containers": self.supports_init_containers,
            "supports_log_streaming": self.supports_log_streaming,
            "supports_exec_into": self.supports_exec_into,
            "supports_spot": self.supports_spot,
            "supports_artifacts": self.supports_artifacts,
            "supports_health_check": self.supports_health_check,
        }


@dataclass(frozen=True)
class RuntimeConstraints:
    """Numeric limits for a runtime.

    The validator checks both capabilities (boolean flags) AND constraints
    (numeric limits) before submission. Rejection messages are specific:
    "Lambda max timeout is 900s but spec requests 3600s".

    None means "unlimited" or "not applicable".

    .. mermaid::

        flowchart TD
            SPEC[ContainerJobSpec] --> V{Validator}
            V -->|check booleans| CAP[RuntimeCapabilities]
            V -->|check numbers| CON[RuntimeConstraints]
            CAP -->|pass/fail| R[Result]
            CON -->|violations list| R
            R -->|empty| OK[Submit to adapter]
            R -->|non-empty| ERR[JobError VALIDATION]
    """

    max_timeout_seconds: int | None = None
    max_memory_mb: int | None = None
    max_cpu_cores: float | None = None
    max_env_count: int | None = None
    max_env_bytes: int | None = None
    max_artifact_bytes: int | None = None
    max_log_bytes_per_execution: int | None = None
    max_concurrent: int | None = None
    supports_privileged: bool = False
    supports_host_network: bool = False
    supports_workload_identity: bool = False

    def validate_spec(self, spec: ContainerJobSpec) -> list[str]:
        """Validate spec against constraints. Returns list of violation messages.

        Empty list = all checks pass.

        Example:
            >>> constraints = RuntimeConstraints(max_timeout_seconds=900)
            >>> spec = ContainerJobSpec(name="test", image="x", timeout_seconds=3600)
            >>> constraints.validate_spec(spec)
            ['Timeout 3600s exceeds runtime max of 900s']
        """
        violations: list[str] = []

        if self.max_timeout_seconds is not None:
            if spec.timeout_seconds > self.max_timeout_seconds:
                violations.append(
                    f"Timeout {spec.timeout_seconds}s exceeds "
                    f"runtime max of {self.max_timeout_seconds}s"
                )

        if self.max_env_count is not None:
            if len(spec.env) > self.max_env_count:
                violations.append(
                    f"Env var count {len(spec.env)} exceeds "
                    f"runtime max of {self.max_env_count}"
                )

        if self.max_env_bytes is not None:
            total_bytes = sum(
                len(k.encode()) + len(v.encode())
                for k, v in spec.env.items()
            )
            if total_bytes > self.max_env_bytes:
                violations.append(
                    f"Total env size {total_bytes} bytes exceeds "
                    f"runtime max of {self.max_env_bytes} bytes"
                )

        return violations

    def to_dict(self) -> dict[str, Any]:
        """Serialize non-None fields."""
        return {k: v for k, v in {
            "max_timeout_seconds": self.max_timeout_seconds,
            "max_memory_mb": self.max_memory_mb,
            "max_cpu_cores": self.max_cpu_cores,
            "max_env_count": self.max_env_count,
            "max_env_bytes": self.max_env_bytes,
            "max_artifact_bytes": self.max_artifact_bytes,
            "max_log_bytes_per_execution": self.max_log_bytes_per_execution,
            "max_concurrent": self.max_concurrent,
            "supports_privileged": self.supports_privileged,
            "supports_host_network": self.supports_host_network,
            "supports_workload_identity": self.supports_workload_identity,
        }.items() if v is not None and v is not False}


# ---------------------------------------------------------------------------
# Runtime health / status
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuntimeHealth:
    """Result of a runtime adapter health check.

    Example:
        >>> health = RuntimeHealth(healthy=True, runtime="docker", version="24.0.7")
    """

    healthy: bool
    runtime: str
    version: str | None = None
    message: str | None = None
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        d: dict[str, Any] = {
            "healthy": self.healthy,
            "runtime": self.runtime,
        }
        if self.version:
            d["version"] = self.version
        if self.message:
            d["message"] = self.message
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        return d


@dataclass(frozen=True)
class JobStatus:
    """Observed status from a runtime adapter.

    This represents the runtime's view of the job (Docker container status,
    K8s Pod phase, ECS task status). The engine maps this to ExecutionStatus.
    """

    state: Literal[
        "pending", "pulling", "creating", "running",
        "succeeded", "failed", "cancelled", "unknown",
    ]
    exit_code: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str | None = None
    node: str | None = None             # Host/node where job ran

    @property
    def is_terminal(self) -> bool:
        """Whether the job has reached a final state."""
        return self.state in ("succeeded", "failed", "cancelled")

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        d: dict[str, Any] = {"state": self.state}
        if self.exit_code is not None:
            d["exit_code"] = self.exit_code
        if self.started_at:
            d["started_at"] = self.started_at.isoformat()
        if self.finished_at:
            d["finished_at"] = self.finished_at.isoformat()
        if self.message:
            d["message"] = self.message
        if self.node:
            d["node"] = self.node
        return d


@dataclass(frozen=True)
class JobArtifact:
    """Metadata for an output artifact from a container job.

    Example:
        >>> artifact = JobArtifact(
        ...     name="report.csv",
        ...     path="/artifacts/report.csv",
        ...     size_bytes=1024,
        ...     checksum="sha256:abc...",
        ... )
    """

    name: str
    path: str                           # Container-internal path
    size_bytes: int | None = None
    checksum: str | None = None         # "sha256:..." or "md5:..."
    content_type: str | None = None     # MIME type
    storage_uri: str | None = None      # External storage location after collection

    def to_dict(self) -> dict[str, Any]:
        """Serialize for API response."""
        d: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
        }
        if self.size_bytes is not None:
            d["size_bytes"] = self.size_bytes
        if self.checksum:
            d["checksum"] = self.checksum
        if self.content_type:
            d["content_type"] = self.content_type
        if self.storage_uri:
            d["storage_uri"] = self.storage_uri
        return d


# ---------------------------------------------------------------------------
# RuntimeAdapter — the core protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class RuntimeAdapter(Protocol):
    """Protocol for container runtime adapters.

    Every compute backend (Docker, Podman, K8s, ECS, Lambda, Cloud Run,
    etc.) implements this protocol. The engine interacts with runtimes
    exclusively through these 7 methods.

    All methods are async — even Docker operations use asyncio for
    consistency and to avoid blocking the event loop.

    Lifecycle:
        submit → status/logs (polling or streaming) → cleanup
        cancel can be called at any time before terminal state.

    .. code-block:: text

        RuntimeAdapter Protocol — 7 Methods
        ┌────────────────────────────────────────────────────────┐
        │  submit(spec) → external_ref    Start a container job │
        │  status(ref) → JobStatus        Poll current state    │
        │  cancel(ref) → bool             Stop a running job    │
        │  logs(ref, follow) → lines      Stream/fetch output   │
        │  artifacts(ref) → list          List output files     │
        │  cleanup(ref) → None            Remove resources      │
        │  health() → RuntimeHealth       Check reachability    │
        └────────────────────────────────────────────────────────┘

    .. mermaid::

        sequenceDiagram
            participant C as Client
            participant A as RuntimeAdapter
            C->>A: submit(spec)
            A-->>C: external_ref
            loop Poll or stream
                C->>A: status(ref)
                A-->>C: JobStatus
                C->>A: logs(ref, follow=True)
                A-->>C: log lines
            end
            alt Cancellation
                C->>A: cancel(ref)
            end
            C->>A: artifacts(ref)
            A-->>C: JobArtifact[]
            C->>A: cleanup(ref)

    Example implementation::

        class DockerAdapter:
            @property
            def runtime_name(self) -> str:
                return "docker"

            async def submit(self, spec: ContainerJobSpec) -> str:
                container = self.client.containers.run(
                    spec.image, spec.command, detach=True, ...
                )
                return container.id

            async def status(self, external_ref: str) -> JobStatus:
                container = self.client.containers.get(external_ref)
                return JobStatus(state=self._map_status(container.status))
    """

    @property
    def runtime_name(self) -> str:
        """Unique name for this runtime (e.g., 'docker', 'k8s', 'ecs')."""
        ...

    @property
    def capabilities(self) -> RuntimeCapabilities:
        """What this runtime supports (boolean feature flags)."""
        ...

    @property
    def constraints(self) -> RuntimeConstraints:
        """Numeric limits for this runtime."""
        ...

    async def submit(self, spec: ContainerJobSpec) -> str:
        """Submit a container job. Returns external reference (container ID, pod name, ARN).

        The external_ref is used for all subsequent operations (status, logs,
        cancel, cleanup). It must be stable for the lifetime of the job.

        Raises:
            JobError: If submission fails (validation, auth, quota, etc.)
        """
        ...

    async def status(self, external_ref: str) -> JobStatus:
        """Get current job status from the runtime.

        This is the runtime's view of the job. The engine maps it to
        ExecutionStatus and persists via ExecutionLedger.
        """
        ...

    async def cancel(self, external_ref: str) -> bool:
        """Cancel a running job. Returns True if cancellation was initiated.

        Idempotent — cancelling an already-cancelled or completed job
        returns True without error.
        """
        ...

    async def logs(
        self,
        external_ref: str,
        *,
        follow: bool = False,
        tail: int | None = None,
    ) -> AsyncIterator[str]:
        """Stream or fetch log lines from the job.

        Args:
            external_ref: The external reference from submit().
            follow: If True, stream logs in real-time until job completes.
            tail: If set, return only the last N lines.

        Yields:
            Log lines (without trailing newline).
        """
        ...

    async def artifacts(self, external_ref: str) -> list[JobArtifact]:
        """List output artifacts from the job's artifacts directory.

        Returns empty list if no artifacts or if the runtime doesn't
        support artifact collection.
        """
        ...

    async def cleanup(self, external_ref: str) -> None:
        """Remove runtime resources (container, pod, task).

        Idempotent — cleaning up already-removed resources is a no-op.
        """
        ...

    async def health(self) -> RuntimeHealth:
        """Check runtime reachability and version.

        Used by the reconciler and runtime list command.
        """
        ...


# ---------------------------------------------------------------------------
# Convenience constructors
# ---------------------------------------------------------------------------

def container_job_spec(
    name: str,
    image: str,
    command: list[str] | None = None,
    **kwargs: Any,
) -> ContainerJobSpec:
    """Convenience constructor for ContainerJobSpec.

    Example:
        >>> spec = container_job_spec(
        ...     "my-job",
        ...     "python:3.12",
        ...     ["python", "-c", "print(42)"],
        ...     timeout_seconds=300,
        ... )
    """
    return ContainerJobSpec(name=name, image=image, command=command, **kwargs)


def quick_docker_spec(
    name: str,
    image: str,
    command: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    timeout_seconds: int = 3600,
) -> ContainerJobSpec:
    """Minimal spec for a quick Docker job.

    Example:
        >>> spec = quick_docker_spec("test", "alpine", ["echo", "hello"])
    """
    return ContainerJobSpec(
        name=name,
        image=image,
        command=command,
        env=env or {},
        timeout_seconds=timeout_seconds,
        runtime="docker",
    )
