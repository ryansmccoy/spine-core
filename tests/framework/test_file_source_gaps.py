"""Tests for framework/sources/file.py — gap coverage.

Covers:
- supports_streaming property
- get_cache_key()
- has_changed() (mtime, hash, missing-file)
- TSV read
- JSONL streaming
- JSON nested key extraction
- JSON single-object wrap
- Unknown extension error
- stream() on non-streamable format
- Parquet ImportError
- FileNotFound on fetch
"""

import json
from pathlib import Path

import pytest

from spine.core.errors import SourceError, SourceNotFoundError
from spine.framework.sources.file import FileFormat, FileSource


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: supports_streaming
# ---------------------------------------------------------------------------


class TestSupportsStreaming:
    def test_csv_streaming(self, tmp_dir):
        f = _write(tmp_dir / "a.csv", "a,b\n1,2\n")
        assert FileSource("s", f).supports_streaming is True

    def test_json_no_streaming(self, tmp_dir):
        f = _write(tmp_dir / "a.json", "[]")
        assert FileSource("s", f).supports_streaming is False

    def test_jsonl_streaming(self, tmp_dir):
        f = _write(tmp_dir / "a.jsonl", '{"a":1}\n')
        assert FileSource("s", f).supports_streaming is True


# ---------------------------------------------------------------------------
# Tests: get_cache_key
# ---------------------------------------------------------------------------


class TestGetCacheKey:
    def test_deterministic(self, tmp_dir):
        f = _write(tmp_dir / "a.csv", "a,b\n1,2\n")
        s = FileSource("s", f)
        k1 = s.get_cache_key()
        k2 = s.get_cache_key()
        assert k1 == k2

    def test_different_params(self, tmp_dir):
        f = _write(tmp_dir / "a.csv", "a,b\n1,2\n")
        s = FileSource("s", f)
        k1 = s.get_cache_key({"tier": "A"})
        k2 = s.get_cache_key({"tier": "B"})
        assert k1 != k2


# ---------------------------------------------------------------------------
# Tests: has_changed
# ---------------------------------------------------------------------------


class TestHasChanged:
    def test_missing_file(self, tmp_dir):
        s = FileSource("s", tmp_dir / "missing.csv", format="csv")
        assert s.has_changed() is True

    def test_same_mtime(self, tmp_dir):
        f = _write(tmp_dir / "a.csv", "x\n")
        s = FileSource("s", f)
        _, mtime = s._get_file_info()
        assert s.has_changed(last_modified=mtime.isoformat()) is False

    def test_different_hash(self, tmp_dir):
        f = _write(tmp_dir / "a.csv", "x\n")
        s = FileSource("s", f)
        assert s.has_changed(last_hash="0000") is True

    def test_same_hash(self, tmp_dir):
        f = _write(tmp_dir / "a.csv", "x\n")
        s = FileSource("s", f)
        h = s._compute_content_hash()
        assert s.has_changed(last_hash=h) is False


# ---------------------------------------------------------------------------
# Tests: TSV
# ---------------------------------------------------------------------------


class TestTSV:
    def test_fetch_tsv(self, tmp_dir):
        f = _write(tmp_dir / "a.tsv", "name\tage\nAlice\t30\nBob\t25\n")
        s = FileSource("s", f)
        result = s.fetch()
        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# Tests: JSONL streaming
# ---------------------------------------------------------------------------


class TestJSONLStreaming:
    def test_stream_jsonl(self, tmp_dir):
        lines = "\n".join(json.dumps({"i": i}) for i in range(5))
        f = _write(tmp_dir / "a.jsonl", lines + "\n")
        s = FileSource("s", f)
        batches = list(s.stream(batch_size=2))
        assert len(batches) == 3  # [2, 2, 1]
        total = sum(len(b) for b in batches)
        assert total == 5


# ---------------------------------------------------------------------------
# Tests: JSON edge cases
# ---------------------------------------------------------------------------


class TestJSONEdgeCases:
    def test_nested_data_key(self, tmp_dir):
        """JSON with {data: [...]} extracts the array."""
        f = _write(tmp_dir / "a.json", json.dumps({"data": [{"x": 1}, {"x": 2}]}))
        s = FileSource("s", f)
        result = s.fetch()
        assert result.success is True
        assert len(result.data) == 2

    def test_single_object_wrap(self, tmp_dir):
        """JSON with a single object wraps it in a list."""
        f = _write(tmp_dir / "a.json", json.dumps({"name": "Alice"}))
        s = FileSource("s", f)
        result = s.fetch()
        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0]["name"] == "Alice"


# ---------------------------------------------------------------------------
# Tests: Error paths
# ---------------------------------------------------------------------------


class TestErrors:
    def test_unknown_extension(self, tmp_dir):
        f = _write(tmp_dir / "a.xyz", "stuff")
        with pytest.raises(SourceError, match="Cannot detect format"):
            FileSource("s", f)

    def test_stream_unsupported_format(self, tmp_dir):
        f = _write(tmp_dir / "a.json", "[]")
        s = FileSource("s", f)
        with pytest.raises(SourceError, match="Streaming not supported"):
            list(s.stream())

    def test_fetch_file_not_found(self, tmp_dir):
        s = FileSource("s", tmp_dir / "missing.csv", format="csv")
        result = s.fetch()
        assert result.success is False

    def test_parquet_missing_pyarrow(self, tmp_dir):
        f = _write(tmp_dir / "a.parquet", b"\x00".decode("latin-1"))
        s = FileSource("s", f)
        result = s.fetch()
        # Should fail because pyarrow probably isn't installed
        # or the file isn't valid parquet — either way SourceResult.fail
        assert result.success is False


class TestStreamFileNotFound:
    def test_stream_missing_file(self, tmp_dir):
        s = FileSource("s", tmp_dir / "missing.csv", format="csv")
        with pytest.raises(SourceNotFoundError):
            list(s.stream())
