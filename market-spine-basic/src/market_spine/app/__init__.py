"""
Market Spine Application Layer.

This package contains the shared command and service layer that both
CLI and API call. It sits between the I/O adapters (CLI, API) and the
framework/domain layer (spine-core, spine-domains).

Structure:
    app/
    ├── commands/     # Use-case implementations (ListPipelines, RunPipeline, etc.)
    ├── services/     # Shared logic (TierNormalizer, ParameterResolver, etc.)
    └── models.py     # Shared data structures (Result, CommandError)

Design principles:
    1. Commands return Result objects, never raise for control flow
    2. Services are stateless and pure
    3. No CLI/API imports - this layer is adapter-agnostic
    4. No direct database access - use spine.framework.db
"""
