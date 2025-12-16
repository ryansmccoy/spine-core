"""Tests for core.settings module.

Covers:
- SpineBaseSettings instantiation with defaults
- Environment variable override
- Subclass with custom env_prefix
- Field types and validation
"""

from pathlib import Path

import pytest

from spine.core.settings import SpineBaseSettings


class TestSpineBaseSettingsDefaults:
    def test_default_host(self):
        s = SpineBaseSettings()
        assert s.host == "0.0.0.0"

    def test_default_port(self):
        s = SpineBaseSettings()
        assert s.port == 8000

    def test_default_debug_false(self):
        s = SpineBaseSettings()
        assert s.debug is False

    def test_default_log_level(self):
        s = SpineBaseSettings()
        assert s.log_level == "INFO"

    def test_default_data_dir_is_home_spine(self):
        s = SpineBaseSettings()
        assert s.data_dir == Path.home() / ".spine"
        assert isinstance(s.data_dir, Path)


class TestSpineBaseSettingsEnvOverride:
    def test_port_from_env(self, monkeypatch):
        monkeypatch.setenv("PORT", "9090")
        s = SpineBaseSettings()
        assert s.port == 9090

    def test_debug_from_env(self, monkeypatch):
        monkeypatch.setenv("DEBUG", "true")
        s = SpineBaseSettings()
        assert s.debug is True

    def test_log_level_from_env(self, monkeypatch):
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        s = SpineBaseSettings()
        assert s.log_level == "DEBUG"

    def test_host_from_env(self, monkeypatch):
        monkeypatch.setenv("HOST", "127.0.0.1")
        s = SpineBaseSettings()
        assert s.host == "127.0.0.1"


class TestSpineBaseSettingsSubclass:
    def test_subclass_with_custom_prefix(self, monkeypatch):
        class KnowledgeSettings(SpineBaseSettings):
            model_config = {"env_prefix": "KNOWLEDGE_", "extra": "ignore"}
            graph_backend: str = "memory"

        monkeypatch.setenv("KNOWLEDGE_GRAPH_BACKEND", "neo4j")
        monkeypatch.setenv("KNOWLEDGE_PORT", "8888")
        s = KnowledgeSettings()
        assert s.graph_backend == "neo4j"
        assert s.port == 8888

    def test_subclass_inherits_defaults(self):
        class SearchSettings(SpineBaseSettings):
            model_config = {"env_prefix": "SEARCH_", "extra": "ignore"}
            index_name: str = "default"

        s = SearchSettings()
        assert s.host == "0.0.0.0"
        assert s.debug is False
        assert s.index_name == "default"

    def test_extra_fields_ignored(self, monkeypatch):
        """Extra env vars should not raise."""
        monkeypatch.setenv("UNRELATED_SETTING", "foo")
        s = SpineBaseSettings()
        assert not hasattr(s, "UNRELATED_SETTING")
