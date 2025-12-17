"""Tests for secrets resolver module."""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

from spine.core.secrets import (
    SecretBackend,
    EnvSecretBackend,
    FileSecretBackend,
    DictSecretBackend,
    SecretsResolver,
    SecretValue,
    resolve_secret,
    resolve_config_secrets,
    get_resolver,
    MissingSecretError,
    SecretResolutionError,
)


class TestSecretValue:
    """Tests for SecretValue wrapper."""

    def test_secret_value_creation(self):
        """Test creating a secret value."""
        sv = SecretValue("my_secret_value")
        assert sv.get_secret() == "my_secret_value"

    def test_secret_value_str_redacted(self):
        """Test string representation is redacted."""
        sv = SecretValue("my_secret_value")
        assert str(sv) == "[REDACTED]"
        assert "my_secret_value" not in str(sv)

    def test_secret_value_repr_redacted(self):
        """Test repr is redacted."""
        sv = SecretValue("my_secret_value")
        assert "my_secret_value" not in repr(sv)
        assert "SecretValue" in repr(sv)

    def test_secret_value_len(self):
        """Test length of secret value."""
        sv = SecretValue("12345")
        assert len(sv) == 5

    def test_secret_value_bool(self):
        """Test truthiness of secret value."""
        assert SecretValue("secret")
        assert not SecretValue("")

    def test_secret_value_equality(self):
        """Test equality comparison."""
        sv1 = SecretValue("secret")
        sv2 = SecretValue("secret")
        sv3 = SecretValue("different")

        assert sv1 == sv2
        assert sv1 != sv3


class TestDictSecretBackend:
    """Tests for DictSecretBackend."""

    def test_basic_get(self):
        """Test basic secret retrieval."""
        backend = DictSecretBackend({"api_key": "12345"})
        assert backend.get("api_key") == "12345"

    def test_missing_key(self):
        """Test missing key returns None."""
        backend = DictSecretBackend({"api_key": "12345"})
        assert backend.get("missing") is None

    def test_case_sensitive(self):
        """Test keys are case-sensitive."""
        backend = DictSecretBackend({"API_KEY": "12345"})
        assert backend.get("api_key") is None
        assert backend.get("API_KEY") == "12345"

    def test_contains(self):
        """Test contains check."""
        backend = DictSecretBackend({"api_key": "12345"})
        assert backend.contains("api_key")
        assert not backend.contains("missing")


class TestEnvSecretBackend:
    """Tests for EnvSecretBackend."""

    def test_direct_env_var(self):
        """Test reading direct env var."""
        backend = EnvSecretBackend()
        with patch.dict(os.environ, {"API_KEY": "secret123"}):
            assert backend.get("API_KEY") == "secret123"

    def test_spine_secret_prefix(self):
        """Test SPINE_SECRET_ prefix is tried."""
        backend = EnvSecretBackend()
        with patch.dict(os.environ, {"SPINE_SECRET_API_KEY": "secret123"}):
            assert backend.get("API_KEY") == "secret123"

    def test_secret_suffix(self):
        """Test _SECRET suffix is tried."""
        backend = EnvSecretBackend()
        with patch.dict(os.environ, {"API_KEY_SECRET": "secret123"}):
            assert backend.get("API_KEY") == "secret123"

    def test_priority_order(self):
        """Test resolution priority order."""
        backend = EnvSecretBackend()
        # Direct name takes precedence
        with patch.dict(os.environ, {
            "API_KEY": "direct",
            "SPINE_SECRET_API_KEY": "prefixed",
            "API_KEY_SECRET": "suffixed",
        }):
            assert backend.get("API_KEY") == "direct"

    def test_missing_env_var(self):
        """Test missing env var returns None."""
        backend = EnvSecretBackend()
        with patch.dict(os.environ, {}, clear=True):
            assert backend.get("NONEXISTENT_KEY") is None


class TestFileSecretBackend:
    """Tests for FileSecretBackend."""

    def test_read_secret_file(self):
        """Test reading secret from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_file = Path(tmpdir) / "api_key"
            secret_file.write_text("file_secret_123")

            backend = FileSecretBackend(secrets_dir=tmpdir)
            assert backend.get("api_key") == "file_secret_123"

    def test_strips_whitespace(self):
        """Test whitespace is stripped from secret files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_file = Path(tmpdir) / "api_key"
            secret_file.write_text("  secret_with_whitespace  \n")

            backend = FileSecretBackend(secrets_dir=tmpdir)
            assert backend.get("api_key") == "secret_with_whitespace"

    def test_missing_file(self):
        """Test missing secret file returns None."""
        with tempfile.TemporaryDirectory() as tmpdir:
            backend = FileSecretBackend(secrets_dir=tmpdir)
            assert backend.get("nonexistent") is None

    def test_nonexistent_directory(self):
        """Test nonexistent directory returns None."""
        backend = FileSecretBackend(secrets_dir="/nonexistent/path")
        assert backend.get("any_secret") is None

    def test_contains(self):
        """Test contains check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_file = Path(tmpdir) / "api_key"
            secret_file.write_text("secret")

            backend = FileSecretBackend(secrets_dir=tmpdir)
            assert backend.contains("api_key")
            assert not backend.contains("missing")


class TestSecretsResolver:
    """Tests for SecretsResolver."""

    def test_single_backend(self):
        """Test resolver with single backend."""
        resolver = SecretsResolver([
            DictSecretBackend({"api_key": "secret123"})
        ])
        assert resolver.resolve("api_key") == "secret123"

    def test_multiple_backends_priority(self):
        """Test first backend with secret wins."""
        resolver = SecretsResolver([
            DictSecretBackend({"api_key": "first"}),
            DictSecretBackend({"api_key": "second"}),
        ])
        assert resolver.resolve("api_key") == "first"

    def test_fallback_to_second_backend(self):
        """Test fallback to second backend."""
        resolver = SecretsResolver([
            DictSecretBackend({}),
            DictSecretBackend({"api_key": "second"}),
        ])
        assert resolver.resolve("api_key") == "second"

    def test_missing_secret_raises(self):
        """Test missing secret raises MissingSecretError."""
        resolver = SecretsResolver([DictSecretBackend({})])
        with pytest.raises(MissingSecretError) as exc_info:
            resolver.resolve("missing")
        assert "missing" in str(exc_info.value)

    def test_missing_secret_with_default(self):
        """Test default value for missing secret."""
        resolver = SecretsResolver([DictSecretBackend({})])
        result = resolver.resolve("missing", default="fallback")
        assert result == "fallback"

    def test_resolve_as_secret_value(self):
        """Test resolving as SecretValue wrapper."""
        resolver = SecretsResolver([
            DictSecretBackend({"api_key": "secret123"})
        ])
        sv = resolver.resolve_secret_value("api_key")
        assert isinstance(sv, SecretValue)
        assert sv.get_secret() == "secret123"

    def test_add_backend(self):
        """Test adding backend dynamically."""
        resolver = SecretsResolver([DictSecretBackend({})])
        resolver.add_backend(DictSecretBackend({"api_key": "added"}))
        assert resolver.resolve("api_key") == "added"

    def test_contains(self):
        """Test checking if secret exists."""
        resolver = SecretsResolver([
            DictSecretBackend({"api_key": "secret"})
        ])
        assert resolver.contains("api_key")
        assert not resolver.contains("missing")


class TestSecretReferences:
    """Tests for secret reference syntax parsing."""

    def test_parse_env_reference(self):
        """Test parsing secret:env:KEY reference."""
        resolver = SecretsResolver([])
        with patch.dict(os.environ, {"MY_API_KEY": "env_secret"}):
            result = resolver.resolve_reference("secret:env:MY_API_KEY")
            assert result == "env_secret"

    def test_parse_file_reference(self):
        """Test parsing secret:file:/path reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            secret_file = Path(tmpdir) / "api_key"
            secret_file.write_text("file_secret")

            resolver = SecretsResolver([])
            result = resolver.resolve_reference(f"secret:file:{secret_file}")
            assert result == "file_secret"

    def test_invalid_reference_format(self):
        """Test invalid reference format raises error."""
        resolver = SecretsResolver([])
        with pytest.raises(SecretResolutionError, match="Invalid"):
            resolver.resolve_reference("secret:invalid")


class TestResolveConfigSecrets:
    """Tests for resolve_config_secrets function."""

    def test_resolve_nested_dict(self):
        """Test resolving secrets in nested dict."""
        config = {
            "database": {
                "host": "localhost",
                "password": "secret:value",
            },
            "api_key": "secret:value",
        }
        resolver = SecretsResolver([
            DictSecretBackend({"value": "resolved_secret"})
        ])

        result = resolve_config_secrets(config, resolver)

        assert result["database"]["host"] == "localhost"
        assert result["database"]["password"] == "resolved_secret"
        assert result["api_key"] == "resolved_secret"

    def test_resolve_list_values(self):
        """Test resolving secrets in lists."""
        config = {
            "keys": ["secret:key1", "secret:key2", "plain_value"]
        }
        resolver = SecretsResolver([
            DictSecretBackend({"key1": "secret1", "key2": "secret2"})
        ])

        result = resolve_config_secrets(config, resolver)

        assert result["keys"][0] == "secret1"
        assert result["keys"][1] == "secret2"
        assert result["keys"][2] == "plain_value"

    def test_prefixed_secret_reference(self):
        """Test prefixed secret references."""
        config = {"value": "secret:my_key"}
        resolver = SecretsResolver([
            DictSecretBackend({"my_key": "found"})
        ])

        result = resolve_config_secrets(config, resolver)
        assert result["value"] == "found"

    def test_passthrough_non_secret_strings(self):
        """Test non-secret strings pass through unchanged."""
        config = {"host": "localhost", "port": 5432}
        resolver = SecretsResolver([DictSecretBackend({})])

        result = resolve_config_secrets(config, resolver)

        assert result["host"] == "localhost"
        assert result["port"] == 5432


class TestGlobalResolver:
    """Tests for global resolver functions."""

    def test_resolve_secret_function(self):
        """Test resolve_secret module function."""
        with patch.dict(os.environ, {"TEST_SECRET": "value123"}):
            result = resolve_secret("TEST_SECRET")
            assert result == "value123"

    def test_resolve_secret_missing_with_default(self):
        """Test resolve_secret with default value."""
        result = resolve_secret("NONEXISTENT_SECRET", default="fallback")
        assert result == "fallback"

    def test_get_resolver_singleton(self):
        """Test get_resolver returns configured resolver."""
        resolver = get_resolver()
        assert isinstance(resolver, SecretsResolver)
        # Should have env backend by default
        assert len(resolver._backends) >= 1


class TestSecretBackendAbstract:
    """Tests for SecretBackend abstract base class."""

    def test_cannot_instantiate_abstract(self):
        """Test abstract class cannot be instantiated."""
        with pytest.raises(TypeError):
            SecretBackend()

    def test_custom_backend(self):
        """Test creating custom backend implementation."""

        class CustomBackend(SecretBackend):
            def get(self, name: str) -> str | None:
                if name == "custom":
                    return "custom_value"
                return None

        backend = CustomBackend()
        assert backend.get("custom") == "custom_value"
        assert backend.get("other") is None
        assert backend.contains("custom")
        assert not backend.contains("other")
