"""Tests for feature flags module."""

import os
import pytest
import threading
from unittest.mock import patch

from spine.core.feature_flags import (
    FeatureFlags,
    FlagDefinition,
    FlagType,
    FlagRegistry,
    FlagNotFoundError,
    feature_flag,
    ENV_PREFIX,
)


@pytest.fixture(autouse=True)
def clean_flags():
    """Clear all flags before and after each test."""
    FeatureFlags._clear_for_testing()
    yield
    FeatureFlags._clear_for_testing()


class TestFlagRegistration:
    """Tests for flag registration."""

    def test_register_bool_flag_default(self):
        """Test registering a boolean flag with default False."""
        flag = FeatureFlags.register("enable_feature")
        assert flag.name == "enable_feature"
        assert flag.default is False
        assert flag.flag_type == FlagType.BOOL

    def test_register_bool_flag_true(self):
        """Test registering a boolean flag with default True."""
        flag = FeatureFlags.register("enable_feature", default=True)
        assert flag.default is True
        assert flag.flag_type == FlagType.BOOL

    def test_register_int_flag(self):
        """Test registering an integer flag."""
        flag = FeatureFlags.register("max_workers", default=4)
        assert flag.default == 4
        assert flag.flag_type == FlagType.INT

    def test_register_float_flag(self):
        """Test registering a float flag."""
        flag = FeatureFlags.register("timeout_seconds", default=30.5)
        assert flag.default == 30.5
        assert flag.flag_type == FlagType.FLOAT

    def test_register_string_flag(self):
        """Test registering a string flag."""
        flag = FeatureFlags.register("log_level", default="INFO")
        assert flag.default == "INFO"
        assert flag.flag_type == FlagType.STRING

    def test_register_with_explicit_type(self):
        """Test registering with explicit type."""
        flag = FeatureFlags.register(
            "batch_size",
            default=100,
            flag_type=FlagType.INT,
            description="Maximum batch size",
        )
        assert flag.flag_type == FlagType.INT
        assert flag.description == "Maximum batch size"

    def test_register_invalid_name(self):
        """Test that invalid names are rejected."""
        with pytest.raises(ValueError, match="snake_case"):
            FeatureFlags.register("InvalidName")

        with pytest.raises(ValueError, match="snake_case"):
            FeatureFlags.register("kebab-case")

        with pytest.raises(ValueError, match="snake_case"):
            FeatureFlags.register("123starts_with_number")

    def test_register_duplicate_name(self):
        """Test that duplicate registration fails."""
        FeatureFlags.register("my_flag")
        with pytest.raises(ValueError, match="already registered"):
            FeatureFlags.register("my_flag")

    def test_is_registered(self):
        """Test checking if flag is registered."""
        assert not FeatureFlags.is_registered("my_flag")
        FeatureFlags.register("my_flag")
        assert FeatureFlags.is_registered("my_flag")

    def test_list_flags(self):
        """Test listing all registered flags."""
        FeatureFlags.register("flag_a")
        FeatureFlags.register("flag_b", default=10)

        flags = FeatureFlags.list_flags()
        names = [f.name for f in flags]
        assert "flag_a" in names
        assert "flag_b" in names


class TestFlagAccess:
    """Tests for flag value access."""

    def test_get_default_value(self):
        """Test getting default value."""
        FeatureFlags.register("my_flag", default=True)
        assert FeatureFlags.get("my_flag") is True

    def test_get_unregistered_flag(self):
        """Test accessing unregistered flag raises error."""
        with pytest.raises(FlagNotFoundError):
            FeatureFlags.get("nonexistent")

    def test_is_enabled_true(self):
        """Test is_enabled for truthy flags."""
        FeatureFlags.register("enabled_flag", default=True)
        assert FeatureFlags.is_enabled("enabled_flag")

    def test_is_enabled_false(self):
        """Test is_enabled for falsy flags."""
        FeatureFlags.register("disabled_flag", default=False)
        assert not FeatureFlags.is_enabled("disabled_flag")

    def test_is_enabled_int_truthy(self):
        """Test is_enabled with truthy int."""
        FeatureFlags.register("count", default=5)
        assert FeatureFlags.is_enabled("count")

    def test_is_enabled_int_zero(self):
        """Test is_enabled with zero."""
        FeatureFlags.register("zero_count", default=0)
        assert not FeatureFlags.is_enabled("zero_count")


class TestRuntimeOverrides:
    """Tests for runtime override functionality."""

    def test_set_override(self):
        """Test setting a runtime override."""
        FeatureFlags.register("my_flag", default=False)
        assert not FeatureFlags.is_enabled("my_flag")

        FeatureFlags.set("my_flag", True)
        assert FeatureFlags.is_enabled("my_flag")

    def test_reset_override(self):
        """Test resetting an override."""
        FeatureFlags.register("my_flag", default=False)
        FeatureFlags.set("my_flag", True)
        assert FeatureFlags.is_enabled("my_flag")

        FeatureFlags.reset("my_flag")
        assert not FeatureFlags.is_enabled("my_flag")

    def test_reset_all_overrides(self):
        """Test resetting all overrides."""
        FeatureFlags.register("flag_a", default=False)
        FeatureFlags.register("flag_b", default=False)

        FeatureFlags.set("flag_a", True)
        FeatureFlags.set("flag_b", True)

        FeatureFlags.reset_all()

        assert not FeatureFlags.is_enabled("flag_a")
        assert not FeatureFlags.is_enabled("flag_b")

    def test_override_context_manager(self):
        """Test temporary override via context manager."""
        FeatureFlags.register("my_flag", default=False)

        with FeatureFlags.override("my_flag", True):
            assert FeatureFlags.is_enabled("my_flag")

        assert not FeatureFlags.is_enabled("my_flag")

    def test_override_context_restores_previous(self):
        """Test context manager restores previous override."""
        FeatureFlags.register("my_flag", default=False)
        FeatureFlags.set("my_flag", True)

        with FeatureFlags.override("my_flag", False):
            assert not FeatureFlags.is_enabled("my_flag")

        assert FeatureFlags.is_enabled("my_flag")


class TestEnvironmentOverrides:
    """Tests for environment variable overrides."""

    def test_env_override_bool_true(self):
        """Test env var override for bool flag (true)."""
        FeatureFlags.register("my_flag", default=False)

        with patch.dict(os.environ, {"SPINE_FF_MY_FLAG": "true"}):
            FeatureFlags.clear_env_cache()
            assert FeatureFlags.is_enabled("my_flag")

    def test_env_override_bool_false(self):
        """Test env var override for bool flag (false)."""
        FeatureFlags.register("my_flag", default=True)

        with patch.dict(os.environ, {"SPINE_FF_MY_FLAG": "false"}):
            FeatureFlags.clear_env_cache()
            assert not FeatureFlags.is_enabled("my_flag")

    def test_env_override_int(self):
        """Test env var override for int flag."""
        FeatureFlags.register("batch_size", default=10)

        with patch.dict(os.environ, {"SPINE_FF_BATCH_SIZE": "50"}):
            FeatureFlags.clear_env_cache()
            assert FeatureFlags.get("batch_size") == 50

    def test_env_override_string(self):
        """Test env var override for string flag."""
        FeatureFlags.register("log_level", default="INFO")

        with patch.dict(os.environ, {"SPINE_FF_LOG_LEVEL": "DEBUG"}):
            FeatureFlags.clear_env_cache()
            assert FeatureFlags.get("log_level") == "DEBUG"

    def test_runtime_override_takes_precedence(self):
        """Test runtime override takes precedence over env var."""
        FeatureFlags.register("my_flag", default=False)

        with patch.dict(os.environ, {"SPINE_FF_MY_FLAG": "true"}):
            FeatureFlags.clear_env_cache()
            FeatureFlags.set("my_flag", False)
            assert not FeatureFlags.is_enabled("my_flag")


class TestFeatureFlagDecorator:
    """Tests for the feature_flag decorator."""

    def test_enabled_flag_runs_function(self):
        """Test decorator runs function when flag enabled."""
        FeatureFlags.register("my_feature", default=True)

        @feature_flag("my_feature")
        def my_function():
            return "executed"

        assert my_function() == "executed"

    def test_disabled_flag_returns_fallback(self):
        """Test decorator returns fallback when flag disabled."""
        FeatureFlags.register("my_feature", default=False)

        @feature_flag("my_feature", fallback="disabled")
        def my_function():
            return "executed"

        assert my_function() == "disabled"

    def test_disabled_flag_raises_error(self):
        """Test decorator raises error when configured."""
        FeatureFlags.register("my_feature", default=False)

        @feature_flag("my_feature", disabled_error=RuntimeError)
        def my_function():
            return "executed"

        with pytest.raises(RuntimeError, match="disabled"):
            my_function()

    def test_decorator_preserves_function_name(self):
        """Test decorator preserves function metadata."""
        FeatureFlags.register("my_feature", default=True)

        @feature_flag("my_feature")
        def my_named_function():
            """My docstring."""
            return "result"

        assert my_named_function.__name__ == "my_named_function"
        assert my_named_function.__doc__ == "My docstring."


class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_registration(self):
        """Test concurrent flag registration is safe."""
        errors = []

        def register_flag(name):
            try:
                FeatureFlags.register(name, default=True)
            except ValueError:
                # Expected for duplicate registration attempts
                pass
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=register_flag, args=(f"flag_{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_access(self):
        """Test concurrent flag access is safe."""
        FeatureFlags.register("shared_flag", default=0)
        errors = []
        results = []

        def access_flag():
            try:
                for _ in range(100):
                    FeatureFlags.set("shared_flag", FeatureFlags.get("shared_flag") + 1)
                    results.append(FeatureFlags.get("shared_flag"))
            except Exception as e:
                errors.append(e)

        threads = []
        for _ in range(5):
            t = threading.Thread(target=access_flag)
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(errors) == 0
        # Due to race conditions, final value might not be 500
        # but no errors should occur
