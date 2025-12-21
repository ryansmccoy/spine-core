"""Tests for spine.framework.sources.protocol — missed coverage lines.

Covers register_source helper and Protocol type-checking.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from spine.framework.sources.protocol import (
    BaseSource,
    Source,
    SourceRegistry,
    SourceType,
    register_source,
    source_registry,
)


class TestRegisterSource:
    def test_register_returns_source(self):
        src = MagicMock(spec=Source)
        src.name = "test-src"
        result = register_source(src)
        assert result is src

    def test_registered_in_global_registry(self):
        src = MagicMock(spec=Source)
        src.name = "global-test-src"
        register_source(src)
        assert "global-test-src" in source_registry.list_sources()


class TestSourceRegistryListByType:
    def test_list_by_type_filters(self):
        registry = SourceRegistry()
        src_http = MagicMock(spec=Source)
        src_http.name = "http-1"
        src_http.source_type = SourceType.HTTP
        src_file = MagicMock(spec=Source)
        src_file.name = "file-1"
        src_file.source_type = SourceType.FILE

        registry.register(src_http)
        registry.register(src_file)

        http_list = registry.list_by_type(SourceType.HTTP)
        assert "http-1" in http_list
        assert "file-1" not in http_list
