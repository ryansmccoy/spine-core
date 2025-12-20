"""Backend and service specifications for deploy-spine.

Provides immutable registries of database backends and deployable
services. Each ``BackendSpec`` carries everything needed to start,
health-check, and connect to a database container. Each ``ServiceSpec``
describes a deployable Spine service (API, worker, infra).

Why This Matters — Financial Data Pipelines:
    Spine's schema must work identically across PostgreSQL (production),
    MySQL (partner integration), SQLite (local dev), and TimescaleDB
    (time-series analytics). Having each backend specified as a frozen
    dataclass with connection URL templates, health-check commands, and
    startup timeouts eliminates hand-crafted docker-compose files for
    every permutation.

Why This Matters — General Pipelines:
    The registry pattern ("add a spec, everything works") means adding a
    new database backend is a single dataclass instantiation — the testbed
    runner, compose generator, and CLI automatically pick it up.

Key Concepts:
    BackendSpec: Frozen dataclass — name, dialect, image, port, healthcheck,
        env, connection URL template. One per database engine.
    ServiceSpec: Frozen dataclass — name, category, image, ports, env,
        depends_on, compose_profiles. One per deployable service.
    BACKENDS: Registry dict mapping name → BackendSpec (6 entries).
    CONTAINER_BACKENDS: Subset requiring Docker (excludes SQLite).
    FREE_BACKENDS: Subset without license restrictions.
    SERVICES: Registry dict mapping name → ServiceSpec (10 entries).

Architecture Decisions:
    - Frozen dataclasses (not Pydantic): Specs are compile-time constants,
      not user input. Frozen prevents accidental mutation.
    - ``connection_url_template`` with ``{user}/{password}/{host}/{port}/{db}``
      placeholders: Defers binding until runtime when the actual port is known.
    - Case-insensitive lookup: ``get_backend("PostgreSQL")`` works.
    - ``requires_license`` flag: DB2 and Oracle need explicit license
      acceptance — CI can filter to free backends only.

Related Modules:
    - :mod:`spine.deploy.container` — Uses BackendSpec to start containers
    - :mod:`spine.deploy.compose` — Uses BackendSpec/ServiceSpec for YAML generation
    - :mod:`spine.deploy.config` — References backend names as strings

Tags:
    backends, database, docker, containers, services, registry, specs
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Database Backend Specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackendSpec:
    """Specification for a database backend container.

    Contains everything needed to run, health-check, and connect
    to a database container for testbed verification.
    """

    name: str
    """Short name (e.g., 'postgresql')."""

    dialect: str
    """Maps to spine.core.dialect registry name."""

    image: str
    """Docker image with pinned tag."""

    port: int
    """Internal container port."""

    healthcheck_cmd: list[str]
    """Docker HEALTHCHECK CMD arguments."""

    env: dict[str, str]
    """Environment variables for the container."""

    connection_url_template: str
    """URL template with {user}, {password}, {host}, {port}, {db} placeholders."""

    startup_timeout: int = 120
    """Seconds to wait for container to become healthy."""

    schema_dir: str = ""
    """Subdirectory under schema/ for dialect-specific SQL (e.g., 'postgresql')."""

    requires_license: bool = False
    """Whether the image requires license acceptance (DB2, Oracle)."""

    notes: str = ""
    """Any caveats or special considerations."""

    default_user: str = "spine"
    """Default database user."""

    default_password: str = "spine"
    """Default database password."""

    default_database: str = "spine"
    """Default database name."""

    def connection_url(self, host: str = "localhost", port: int | None = None) -> str:
        """Build a connection URL for a running container."""
        return self.connection_url_template.format(
            user=self.default_user,
            password=self.default_password,
            host=host,
            port=port or self.port,
            db=self.default_database,
        )


# ---------------------------------------------------------------------------
# Pre-defined database backends
# ---------------------------------------------------------------------------

SQLITE = BackendSpec(
    name="sqlite",
    dialect="sqlite",
    image="",  # In-process, no container
    port=0,
    healthcheck_cmd=[],
    env={},
    connection_url_template="sqlite:///{db}",
    startup_timeout=0,
    schema_dir="",  # Uses root schema/ directory
    notes="In-process, no container needed. Always available.",
)

POSTGRESQL = BackendSpec(
    name="postgresql",
    dialect="postgresql",
    image="postgres:16.4-alpine",
    port=5432,
    healthcheck_cmd=["pg_isready", "-U", "spine"],
    env={
        "POSTGRES_USER": "spine",
        "POSTGRES_PASSWORD": "spine",
        "POSTGRES_DB": "spine",
    },
    connection_url_template="postgresql://{user}:{password}@{host}:{port}/{db}",
    startup_timeout=30,
    schema_dir="postgresql",
)

MYSQL = BackendSpec(
    name="mysql",
    dialect="mysql",
    image="mysql:8.4-debian",
    port=3306,
    healthcheck_cmd=["mysqladmin", "ping", "-h", "localhost", "-u", "spine", "-pspine"],
    env={
        "MYSQL_ROOT_PASSWORD": "spine",
        "MYSQL_USER": "spine",
        "MYSQL_PASSWORD": "spine",
        "MYSQL_DATABASE": "spine",
    },
    connection_url_template="mysql+mysqlconnector://{user}:{password}@{host}:{port}/{db}",
    startup_timeout=60,
    schema_dir="mysql",
)

DB2 = BackendSpec(
    name="db2",
    dialect="db2",
    image="icr.io/db2_community/db2:11.5.9.0",
    port=50000,
    healthcheck_cmd=["su", "-", "db2inst1", "-c", "db2 connect to spine"],
    env={
        "LICENSE": "accept",
        "DB2INST1_PASSWORD": "spine",
        "DBNAME": "spine",
        "ARCHIVE_LOGS": "false",
        "AUTOCONFIG": "false",
    },
    connection_url_template="ibm_db_sa://{user}:{password}@{host}:{port}/{db}",
    startup_timeout=180,
    schema_dir="db2",
    requires_license=True,
    default_user="db2inst1",
    default_password="spine",
    notes="DB2 Community Edition. Requires LICENSE=accept. Slow startup (~2-3 min).",
)

ORACLE = BackendSpec(
    name="oracle",
    dialect="oracle",
    image="gvenzl/oracle-free:23-slim",
    port=1521,
    healthcheck_cmd=[
        "bash", "-c",
        'echo "SELECT 1 FROM DUAL;" | sqlplus -s spine/spine@localhost:1521/FREEPDB1',
    ],
    env={
        "ORACLE_PASSWORD": "spine",
        "APP_USER": "spine",
        "APP_USER_PASSWORD": "spine",
    },
    connection_url_template="oracle+oracledb://{user}:{password}@{host}:{port}/FREEPDB1",
    startup_timeout=120,
    schema_dir="oracle",
    requires_license=True,
    default_database="FREEPDB1",
    notes="Oracle Free 23ai. ~1-2 min startup.",
)

TIMESCALEDB = BackendSpec(
    name="timescaledb",
    dialect="postgresql",  # Uses PostgreSQL dialect
    image="timescale/timescaledb:2.17.2-pg16",
    port=5432,
    healthcheck_cmd=["pg_isready", "-U", "spine"],
    env={
        "POSTGRES_USER": "spine",
        "POSTGRES_PASSWORD": "spine",
        "POSTGRES_DB": "spine",
    },
    connection_url_template="postgresql://{user}:{password}@{host}:{port}/{db}",
    startup_timeout=30,
    schema_dir="postgresql",  # Shares PostgreSQL schema
    notes="TimescaleDB extension on PostgreSQL 16. Uses PostgreSQL dialect.",
)


# Registry of all pre-defined backends
BACKENDS: dict[str, BackendSpec] = {
    "sqlite": SQLITE,
    "postgresql": POSTGRESQL,
    "mysql": MYSQL,
    "db2": DB2,
    "oracle": ORACLE,
    "timescaledb": TIMESCALEDB,
}

# Backends that require a Docker container
CONTAINER_BACKENDS: dict[str, BackendSpec] = {
    k: v for k, v in BACKENDS.items() if v.image
}

# Backends available without license acceptance
FREE_BACKENDS: dict[str, BackendSpec] = {
    k: v for k, v in BACKENDS.items() if not v.requires_license
}


def get_backend(name: str) -> BackendSpec:
    """Look up a backend spec by name.

    Parameters
    ----------
    name
        Backend name (case-insensitive).

    Returns
    -------
    BackendSpec

    Raises
    ------
    ValueError
        If backend name is not recognized.
    """
    key = name.lower().strip()
    if key not in BACKENDS:
        available = ", ".join(sorted(BACKENDS.keys()))
        raise ValueError(f"Unknown backend: {name!r}. Available: {available}")
    return BACKENDS[key]


def get_backends(names: list[str]) -> list[BackendSpec]:
    """Look up multiple backend specs, with 'all' expansion.

    Parameters
    ----------
    names
        Backend names. Use ``["all"]`` for all backends.

    Returns
    -------
    list[BackendSpec]
    """
    if names == ["all"]:
        return list(BACKENDS.values())
    return [get_backend(n) for n in names]


# ---------------------------------------------------------------------------
# Service Specifications (for full Spine deployments)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServiceSpec:
    """Specification for a deployable Spine service.

    Describes an API server, worker, frontend, or infrastructure
    service that can be deployed via Docker Compose.
    """

    name: str
    """Service identifier (e.g., 'spine-core-api')."""

    category: str
    """Service category: infra, app, worker, frontend, docs, tool."""

    image: str
    """Docker image or build context."""

    port: int
    """Primary exposed port."""

    internal_port: int = 8000
    """Internal container port."""

    healthcheck_url: str = "/health"
    """Health endpoint path."""

    env: dict[str, str] = field(default_factory=dict)
    """Environment variables."""

    depends_on: list[str] = field(default_factory=list)
    """Service dependencies."""

    volumes: dict[str, str] = field(default_factory=dict)
    """Volume mounts (host_path: container_path)."""

    build_context: str | None = None
    """Build context directory (relative to workspace root)."""

    dockerfile: str | None = None
    """Dockerfile path (relative to build context)."""

    compose_profiles: list[str] = field(default_factory=list)
    """Docker Compose profiles this service belongs to."""

    description: str = ""
    """Human-readable description."""

    labels: dict[str, str] = field(default_factory=dict)
    """Docker labels."""


# ---------------------------------------------------------------------------
# Pre-defined Spine services
# ---------------------------------------------------------------------------

SPINE_CORE_API = ServiceSpec(
    name="spine-core-api",
    category="app",
    image="spine-core:latest",
    port=12000,
    internal_port=8000,
    healthcheck_url="/health/ready",
    env={
        "DATABASE_URL": "postgresql://spine:spine@postgres:5432/spine",
        "LOG_LEVEL": "INFO",
    },
    depends_on=["postgres"],
    build_context="spine-core",
    dockerfile="Dockerfile",
    compose_profiles=["apps", "full"],
    description="spine-core platform API",
    labels={
        "spine.service.name": "Spine Core",
        "spine.service.id": "spine-core",
        "spine.service.category": "apps",
    },
)

CAPTURE_SPINE_API = ServiceSpec(
    name="capture-spine-api",
    category="app",
    image="capture-spine:latest",
    port=11000,
    internal_port=8000,
    healthcheck_url="/health",
    env={
        "DATABASE_URL": "postgresql://spine:spine@postgres:5432/spine",
        "REDIS_URL": "redis://:spine@redis:6379/0",
        "ELASTICSEARCH_URL": "http://elasticsearch:9200",
    },
    depends_on=["postgres", "redis"],
    build_context="capture-spine",
    dockerfile="Dockerfile",
    compose_profiles=["apps", "minimal", "full"],
    description="Primary data capture and ingestion API",
)

GENAI_SPINE_API = ServiceSpec(
    name="genai-spine-api",
    category="app",
    image="genai-spine:latest",
    port=11100,
    internal_port=8100,
    healthcheck_url="/health",
    env={
        "DATABASE_URL": "postgresql://spine:spine@postgres:5432/genai",
        "OLLAMA_URL": "http://ollama:11434",
    },
    depends_on=["postgres", "redis"],
    build_context="genai-spine",
    dockerfile="Dockerfile",
    compose_profiles=["apps", "full"],
    description="Unified AI/LLM service",
)

ENTITYSPINE_API = ServiceSpec(
    name="entityspine-api",
    category="app",
    image="entityspine:latest",
    port=11200,
    internal_port=8200,
    healthcheck_url="/health",
    env={
        "DATABASE_URL": "postgresql://spine:spine@postgres:5432/entities",
    },
    depends_on=["postgres", "redis"],
    build_context="entityspine",
    dockerfile="Dockerfile",
    compose_profiles=["apps", "full"],
    description="Entity recognition and knowledge graph service",
)

OPS_SPINE_MCP = ServiceSpec(
    name="ops-spine-mcp",
    category="app",
    image="ops-spine:latest",
    port=12005,
    internal_port=8107,
    healthcheck_url="/health",
    env={
        "DATABASE_URL": "postgresql://spine:spine@postgres:5432/spine",
    },
    depends_on=["postgres", "redis"],
    build_context="ops-spine",
    dockerfile="Dockerfile",
    compose_profiles=["apps", "full"],
    description="Orchestration & operations intelligence MCP",
)

# Infrastructure services
POSTGRES_SERVICE = ServiceSpec(
    name="postgres",
    category="infra",
    image="postgres:16-alpine",
    port=10432,
    internal_port=5432,
    healthcheck_url="",  # Uses pg_isready, not HTTP
    env={
        "POSTGRES_USER": "spine",
        "POSTGRES_PASSWORD": "spine",
        "POSTGRES_DB": "spine",
    },
    volumes={"postgres-data": "/var/lib/postgresql/data"},
    compose_profiles=["infra", "apps", "minimal", "full"],
    description="Primary PostgreSQL database",
)

REDIS_SERVICE = ServiceSpec(
    name="redis",
    category="infra",
    image="redis:7-alpine",
    port=10379,
    internal_port=6379,
    healthcheck_url="",  # Uses redis-cli ping
    compose_profiles=["infra", "apps", "minimal", "full"],
    description="Cache and message broker",
)

ELASTICSEARCH_SERVICE = ServiceSpec(
    name="elasticsearch",
    category="infra",
    image="elasticsearch:8.12.0",
    port=10920,
    internal_port=9200,
    healthcheck_url="/_cluster/health",
    env={
        "discovery.type": "single-node",
        "xpack.security.enabled": "false",
    },
    compose_profiles=["infra", "full"],
    description="Full-text search and analytics engine",
)

QDRANT_SERVICE = ServiceSpec(
    name="qdrant",
    category="infra",
    image="qdrant/qdrant:latest",
    port=10633,
    internal_port=6333,
    healthcheck_url="/healthz",
    compose_profiles=["infra", "apps", "full"],
    description="Vector database",
)

OLLAMA_SERVICE = ServiceSpec(
    name="ollama",
    category="infra",
    image="ollama/ollama:latest",
    port=10434,
    internal_port=11434,
    healthcheck_url="/api/tags",
    compose_profiles=["infra", "full"],
    description="Local LLM server",
)


# Service registries
SERVICES: dict[str, ServiceSpec] = {
    "spine-core-api": SPINE_CORE_API,
    "capture-spine-api": CAPTURE_SPINE_API,
    "genai-spine-api": GENAI_SPINE_API,
    "entityspine-api": ENTITYSPINE_API,
    "ops-spine-mcp": OPS_SPINE_MCP,
    "postgres": POSTGRES_SERVICE,
    "redis": REDIS_SERVICE,
    "elasticsearch": ELASTICSEARCH_SERVICE,
    "qdrant": QDRANT_SERVICE,
    "ollama": OLLAMA_SERVICE,
}

APP_SERVICES: dict[str, ServiceSpec] = {
    k: v for k, v in SERVICES.items() if v.category == "app"
}

INFRA_SERVICES: dict[str, ServiceSpec] = {
    k: v for k, v in SERVICES.items() if v.category == "infra"
}


def get_service(name: str) -> ServiceSpec:
    """Look up a service spec by name.

    Parameters
    ----------
    name
        Service name (case-insensitive).

    Returns
    -------
    ServiceSpec

    Raises
    ------
    ValueError
        If service name is not recognized.
    """
    key = name.lower().strip()
    if key not in SERVICES:
        available = ", ".join(sorted(SERVICES.keys()))
        raise ValueError(f"Unknown service: {name!r}. Available: {available}")
    return SERVICES[key]


def get_services_by_profile(profile: str) -> list[ServiceSpec]:
    """Get all services belonging to a Docker Compose profile.

    Parameters
    ----------
    profile
        Profile name (infra, apps, full, minimal).

    Returns
    -------
    list[ServiceSpec]
    """
    return [s for s in SERVICES.values() if profile in s.compose_profiles]
