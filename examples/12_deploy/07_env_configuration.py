#!/usr/bin/env python3
"""Environment Configuration — Build config from environment variables.

Both DeploymentConfig and TestbedConfig can be driven entirely by
environment variables (``SPINE_DEPLOY_*`` and ``SPINE_TESTBED_*``).
This is essential for CI/CD operations where configuration is injected
via the environment.

Demonstrates:
    1. DeploymentConfig.from_env() with env var overrides
    2. TestbedConfig.from_env() with env var overrides
    3. Merging env vars with explicit keyword arguments
    4. Default values when no env vars are set

Key Concepts:
    - **from_env()**: Classmethod that reads SPINE_DEPLOY_* / SPINE_TESTBED_*
    - **Override precedence**: Keyword args > env vars > defaults
    - **Comma-separated lists**: SPINE_DEPLOY_TARGETS="api,db" → ["api", "db"]

See Also:
    - ``01_quickstart.py`` — Config basics
    - ``spine.deploy.config`` — Module source

Run:
    python examples/12_deploy/07_env_configuration.py

Expected Output:
    Config objects created from simulated environment variables.
"""

import os

from spine.deploy.config import DeploymentConfig, TestbedConfig


def main() -> None:
    """Demonstrate environment-variable-driven configuration."""

    # ═══════════════════════════════════════════════════════════
    print("=" * 60)
    print("Deploy-Spine — Environment Configuration")
    print("=" * 60)

    # --- 1. DeploymentConfig.from_env() ---
    print("\n--- 1. DeploymentConfig.from_env() ---")

    # Save and set env vars
    saved = {}
    env_vars = {
        "SPINE_DEPLOY_TARGETS": "spine-core-api,postgresql,redis",
        "SPINE_DEPLOY_PROFILE": "apps",
        "SPINE_DEPLOY_MODE": "up",
        "SPINE_DEPLOY_TIMEOUT_SECONDS": "900",
        "SPINE_DEPLOY_VERBOSE": "true",
    }
    for k, v in env_vars.items():
        saved[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        config = DeploymentConfig.from_env()
        print(f"  targets  : {config.targets}")
        print(f"  profile  : {config.profile}")
        print(f"  mode     : {config.mode.value}")
        print(f"  timeout  : {config.timeout_seconds}s")
        print(f"  verbose  : {config.verbose}")
    finally:
        # Restore env
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- 2. TestbedConfig.from_env() ---
    print("\n--- 2. TestbedConfig.from_env() ---")

    saved2 = {}
    env_vars2 = {
        "SPINE_TESTBED_BACKENDS": "postgresql,mysql,timescaledb",
        "SPINE_TESTBED_PARALLEL": "true",
        "SPINE_TESTBED_TIMEOUT_SECONDS": "1200",
        "SPINE_TESTBED_KEEP_CONTAINERS": "false",
        "SPINE_TESTBED_IMAGE": "spine-core:ci-latest",
    }
    for k, v in env_vars2.items():
        saved2[k] = os.environ.get(k)
        os.environ[k] = v

    try:
        testbed = TestbedConfig.from_env()
        print(f"  backends        : {testbed.backends}")
        print(f"  parallel        : {testbed.parallel}")
        print(f"  timeout         : {testbed.timeout_seconds}s")
        print(f"  keep_containers : {testbed.keep_containers}")
        print(f"  spine_image     : {testbed.spine_image}")
    finally:
        for k, v in saved2.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- 3. Override precedence ---
    print("\n--- 3. Override Precedence (kwargs > env) ---")

    saved3 = {}
    os.environ["SPINE_TESTBED_BACKENDS"] = "postgresql"
    saved3["SPINE_TESTBED_BACKENDS"] = os.environ.get("SPINE_TESTBED_BACKENDS")

    try:
        # Keyword args override env vars
        testbed_override = TestbedConfig.from_env(
            backends=["mysql", "db2"],
            timeout_seconds=600,
        )
        print(f"  env BACKENDS    : postgresql")
        print(f"  kwarg backends  : ['mysql', 'db2']")
        print(f"  resolved        : {testbed_override.backends}")
        print(f"  timeout (kwarg) : {testbed_override.timeout_seconds}s")
    finally:
        for k, v in saved3.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- 4. Defaults (no env vars) ---
    print("\n--- 4. Defaults (No Env Vars) ---")
    # Clean environment
    for prefix in ("SPINE_DEPLOY_", "SPINE_TESTBED_"):
        for k in list(os.environ.keys()):
            if k.startswith(prefix):
                os.environ.pop(k, None)

    default_deploy = DeploymentConfig.from_env()
    default_testbed = TestbedConfig.from_env()
    print(f"  Deploy targets  : {default_deploy.targets} (empty = all)")
    print(f"  Deploy mode     : {default_deploy.mode.value}")
    print(f"  Deploy timeout  : {default_deploy.timeout_seconds}s")
    print(f"  Testbed backends: {default_testbed.backends}")
    print(f"  Testbed parallel: {default_testbed.parallel}")

    # ═══════════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print("✓ Environment configuration demo complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
