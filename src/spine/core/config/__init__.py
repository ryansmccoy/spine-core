"""Centralized configuration, DI container, and profile management.

Manifesto:
    spine-core supports 3 deployment tiers (minimal/standard/full) with
    pluggable backends for database, cache, scheduler, metrics, and workers.
    Without centralized config, each module creates its own settings class
    and the same environment variable gets parsed 5 different ways.

    This package provides a **single validated source of truth** with:

    * **Component enums** -- ``DatabaseBackend``, ``SchedulerBackend``, etc.
    * **Environment-file loader** -- cascading ``.env`` discovery & parsing
    * **TOML profiles** -- inheritable configuration profiles
    * **Settings** -- validated ``SpineCoreSettings`` (Pydantic, cached)
    * **Factory functions** -- create engines, schedulers, cache clients
    * **DI container** -- :class:`SpineContainer` with lazy component init

Quick start::

    from spine.core.config import get_settings, SpineContainer

    settings = get_settings()
    print(settings.database_backend)   # DatabaseBackend.SQLITE
    print(settings.infer_tier())       # "minimal"

    with SpineContainer() as c:
        engine = c.engine

Architecture::

    settings.py       SpineCoreSettings (Pydantic) + get_settings() cache
    components.py     Backend enums + validate_component_combination()
    container.py      SpineContainer (lazy DI) + get_container()
    factory.py        create_database_engine / scheduler / cache / worker
    loader.py         .env file discovery + cascading load
    profiles.py       TOML profile inheritance (~/.spine/profiles/)

Guardrails:
    ❌ Parsing env vars ad-hoc in each module
    ✅ ``get_settings().database_url`` from the cached singleton
    ❌ Constructing engines/schedulers with raw ``create_engine()``
    ✅ ``create_database_engine(settings)`` via the factory layer
    ❌ Hard-coding backend choices in application code
    ✅ ``settings.infer_tier()`` with automatic backend selection

Tags:
    spine-core, configuration, dependency-injection, settings, profiles,
    factory-pattern, pydantic, env-files, TOML, deployment-tiers

Doc-Types:
    package-overview, architecture-map, module-index
"""

from .components import (
    CacheBackend,
    ComponentWarning,
    DatabaseBackend,
    MetricsBackend,
    SchedulerBackend,
    TracingBackend,
    WorkerBackend,
    validate_component_combination,
)
from .container import (
    SpineContainer,
    get_container,
)
from .factory import (
    create_cache_client,
    create_database_engine,
    create_scheduler_backend,
    create_worker_executor,
)
from .loader import (
    discover_env_files,
    find_project_root,
    get_effective_env,
    load_env_files,
)
from .settings import (
    SpineCoreSettings,
    clear_settings_cache,
    get_settings,
)

__all__ = [
    # Components
    "CacheBackend",
    "ComponentWarning",
    "DatabaseBackend",
    "MetricsBackend",
    "SchedulerBackend",
    "TracingBackend",
    "WorkerBackend",
    "validate_component_combination",
    # Settings
    "SpineCoreSettings",
    "get_settings",
    "clear_settings_cache",
    # Container
    "SpineContainer",
    "get_container",
    # Loader
    "find_project_root",
    "discover_env_files",
    "load_env_files",
    "get_effective_env",
    # Factory
    "create_database_engine",
    "create_scheduler_backend",
    "create_cache_client",
    "create_worker_executor",
]
