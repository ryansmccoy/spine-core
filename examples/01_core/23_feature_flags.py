#!/usr/bin/env python3
"""Feature Flags — Runtime Feature Toggling with Environment Overrides.

================================================================================
WHY FEATURE FLAGS?
================================================================================

Feature flags decouple **deployment** from **release**::

    # Without flags: deploy = release (risky)
    def ingest_filing(filing):
        use_new_parser(filing)  # Deployed to all users at once

    # With flags: deploy safely, enable gradually
    def ingest_filing(filing):
        if FeatureFlags.is_enabled("use_new_parser"):
            use_new_parser(filing)
        else:
            use_old_parser(filing)

Use cases in data operations:
    - **Gradual rollout** — Enable new EDGAR parser for 10% of filings first
    - **Kill switches** — Disable expensive enrichment during outages
    - **A/B testing** — Compare two normalization strategies
    - **Environment override** — ``SPINE_FLAG_USE_NEW_PARSER=true`` in staging


================================================================================
ARCHITECTURE
================================================================================

::

    ┌─────────────────────────────────────────────────────────────────────────┐
    │  Flag Resolution Order (highest priority wins)                          │
    ├─────────────────────────────────────────────────────────────────────────┤
    │  1. Environment variable  SPINE_FLAG_MY_FLAG=true                      │
    │  2. Runtime override      FeatureFlags.set("my_flag", True)            │
    │  3. Default value         feature_flag("my_flag", default=False)       │
    └─────────────────────────────────────────────────────────────────────────┘

    Flag Types:
    ┌─────────────┬──────────────────────────────────────────────────────────┐
    │ BOOLEAN     │ Simple on/off toggle                                    │
    │ PERCENTAGE  │ Enabled for N% of evaluations (gradual rollout)        │
    │ STRING      │ Multi-variant flags ("parser_v1", "parser_v2")          │
    └─────────────┴──────────────────────────────────────────────────────────┘


================================================================================
BEST PRACTICES
================================================================================

1. **Name flags descriptively**::

       "use_new_edgar_parser"   not "flag_1"
       "enable_llm_enrichment"  not "feature_a"

2. **Use context managers for testing**::

       with FeatureFlags.override("use_new_parser", True):
           result = ingest_filing(filing)  # Uses new parser
       # Automatically reverts after block

3. **Clean up old flags** — Remove flags that are permanently enabled


================================================================================
EXAMPLE USAGE
================================================================================

Run this example:
    python examples/01_core/23_feature_flags.py

See Also:
    - :mod:`spine.core.feature_flags` — FeatureFlags, FlagType, feature_flag
"""
import os
from spine.core.feature_flags import (
    FeatureFlags,
    FlagType,
    feature_flag,
)


def main():
    print("=" * 60)
    print("Feature Flag Examples")
    print("=" * 60)

    # Clean slate
    FeatureFlags._clear_for_testing()

    # === 1. Basic boolean flags ===
    print("\n[1] Boolean Feature Flags")

    FeatureFlags.register("enable_cache", default=True, description="Enable caching layer")
    FeatureFlags.register("enable_experimental", default=False, description="Experimental features")

    print(f"  enable_cache: {FeatureFlags.is_enabled('enable_cache')}")
    print(f"  enable_experimental: {FeatureFlags.is_enabled('enable_experimental')}")

    # === 2. Typed flags ===
    print("\n[2] Typed Flags (int, float, string)")

    FeatureFlags.register("max_workers", default=4, flag_type=FlagType.INT)
    FeatureFlags.register("timeout_seconds", default=30.5, flag_type=FlagType.FLOAT)
    FeatureFlags.register("log_level", default="INFO", flag_type=FlagType.STRING)

    print(f"  max_workers: {FeatureFlags.get('max_workers')} (int)")
    print(f"  timeout_seconds: {FeatureFlags.get('timeout_seconds')} (float)")
    print(f"  log_level: {FeatureFlags.get('log_level')} (string)")

    # === 3. Runtime overrides ===
    print("\n[3] Runtime Overrides")

    print(f"  Before override: enable_cache = {FeatureFlags.is_enabled('enable_cache')}")
    FeatureFlags.set("enable_cache", False)
    print(f"  After override:  enable_cache = {FeatureFlags.is_enabled('enable_cache')}")
    FeatureFlags.reset("enable_cache")
    print(f"  After reset:     enable_cache = {FeatureFlags.is_enabled('enable_cache')}")

    # === 4. Context manager scoping ===
    print("\n[4] Temporary Override via Context Manager")

    print(f"  Outside context: enable_experimental = {FeatureFlags.is_enabled('enable_experimental')}")
    with FeatureFlags.override("enable_experimental", True):
        print(f"  Inside context:  enable_experimental = {FeatureFlags.is_enabled('enable_experimental')}")
    print(f"  After context:   enable_experimental = {FeatureFlags.is_enabled('enable_experimental')}")

    # === 5. Environment variable overrides ===
    print("\n[5] Environment Variable Overrides (SPINE_FF_*)")

    os.environ["SPINE_FF_MAX_WORKERS"] = "16"
    FeatureFlags.clear_env_cache()
    print(f"  SPINE_FF_MAX_WORKERS=16 → max_workers = {FeatureFlags.get('max_workers')}")
    del os.environ["SPINE_FF_MAX_WORKERS"]
    FeatureFlags.clear_env_cache()

    # === 6. Feature-gated functions ===
    print("\n[6] Feature Flag Decorator")

    @feature_flag("enable_experimental", fallback="Feature disabled")
    def experimental_feature():
        return "Experimental result!"

    result = experimental_feature()
    print(f"  experimental_feature() = {result}")

    FeatureFlags.set("enable_experimental", True)
    result = experimental_feature()
    print(f"  (After enabling) = {result}")
    FeatureFlags.reset("enable_experimental")

    # === 7. Listing registered flags ===
    print("\n[7] List All Registered Flags")

    for flag in FeatureFlags.list_flags():
        current = FeatureFlags.get(flag.name)
        print(f"  {flag.name}: {current} (type={flag.flag_type.value}, default={flag.default})")

    # Clean up
    FeatureFlags._clear_for_testing()

    print("\n" + "=" * 60)
    print("All feature flag examples completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
