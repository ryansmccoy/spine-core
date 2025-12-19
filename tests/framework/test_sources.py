"""Tests for spine.framework.sources module."""

import json
import tempfile
from pathlib import Path

import pytest

from spine.core.errors import ParseError, SourceNotFoundError
from spine.framework.sources.protocol import (
    SourceType,
    SourceMetadata,
    SourceResult,
)
from spine.framework.sources.file import FileSource, FileFormat


class TestFileSource:
    """Test FileSource implementation."""

    def test_create_with_auto_detect_csv(self):
        """Auto-detect CSV format from extension."""
        source = FileSource(name="test", path="/data/file.csv")
        assert source.format == FileFormat.CSV

    def test_create_with_auto_detect_psv(self):
        """Auto-detect PSV format from extension."""
        source = FileSource(name="test", path="/data/file.psv")
        assert source.format == FileFormat.PSV

    def test_create_with_explicit_format(self):
        """Explicitly specify format."""
        source = FileSource(name="test", path="/data/file.txt", format="csv")
        assert source.format == FileFormat.CSV

    def test_fetch_csv_file(self):
        """Fetch data from CSV file."""
        # Create temp CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("name,age,city\n")
            f.write("Alice,30,NYC\n")
            f.write("Bob,25,LA\n")
            temp_path = f.name
        
        try:
            source = FileSource(name="test_csv", path=temp_path)
            result = source.fetch()
            
            assert result.success is True
            assert len(result.data) == 2
            assert result.data[0]["name"] == "Alice"
            assert result.data[0]["age"] == "30"
            assert result.data[1]["name"] == "Bob"
            assert result.metadata.row_count == 2
            assert result.metadata.content_hash is not None
        finally:
            Path(temp_path).unlink()

    def test_fetch_psv_file(self):
        """Fetch data from PSV file."""
        # Create temp PSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.psv', delete=False) as f:
            f.write("symbol|volume|price\n")
            f.write("AAPL|1000|150.00\n")
            f.write("GOOGL|500|2800.00\n")
            temp_path = f.name
        
        try:
            source = FileSource(name="test_psv", path=temp_path)
            result = source.fetch()
            
            assert result.success is True
            assert len(result.data) == 2
            assert result.data[0]["symbol"] == "AAPL"
            assert result.data[0]["volume"] == "1000"
        finally:
            Path(temp_path).unlink()

    def test_fetch_json_file(self):
        """Fetch data from JSON file."""
        # Create temp JSON file
        data = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(data, f)
            temp_path = f.name
        
        try:
            source = FileSource(name="test_json", path=temp_path)
            result = source.fetch()
            
            assert result.success is True
            assert len(result.data) == 2
            assert result.data[0]["id"] == 1
            assert result.data[0]["name"] == "Alice"
        finally:
            Path(temp_path).unlink()

    def test_fetch_jsonl_file(self):
        """Fetch data from JSON Lines file."""
        # Create temp JSONL file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"id": 1, "name": "Alice"}\n')
            f.write('{"id": 2, "name": "Bob"}\n')
            temp_path = f.name
        
        try:
            source = FileSource(name="test_jsonl", path=temp_path)
            result = source.fetch()
            
            assert result.success is True
            assert len(result.data) == 2
            assert result.data[0]["id"] == 1
        finally:
            Path(temp_path).unlink()

    def test_fetch_file_not_found(self):
        """Fetch raises error for missing file."""
        source = FileSource(name="test", path="/nonexistent/file.csv")
        result = source.fetch()
        
        assert result.success is False
        assert isinstance(result.error, SourceNotFoundError)

    def test_content_hash_changes_when_content_changes(self):
        """Content hash changes when file content changes."""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("name,age\n")
            f.write("Alice,30\n")
            temp_path = f.name
        
        try:
            source = FileSource(name="test", path=temp_path)
            
            # First fetch
            result1 = source.fetch()
            hash1 = result1.metadata.content_hash
            
            # Modify file
            with open(temp_path, 'w') as f:
                f.write("name,age\n")
                f.write("Alice,30\n")
                f.write("Bob,25\n")
            
            # Second fetch
            result2 = source.fetch()
            hash2 = result2.metadata.content_hash
            
            assert hash1 != hash2
        finally:
            Path(temp_path).unlink()

    def test_content_hash_same_for_identical_content(self):
        """Content hash is same for identical content."""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("name,age\n")
            f.write("Alice,30\n")
            temp_path = f.name
        
        try:
            source = FileSource(name="test", path=temp_path)
            
            # Fetch twice
            result1 = source.fetch()
            result2 = source.fetch()
            
            assert result1.metadata.content_hash == result2.metadata.content_hash
        finally:
            Path(temp_path).unlink()

    def test_streaming_large_file(self):
        """Stream large file in batches."""
        # Create temp file with many rows
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("id,value\n")
            for i in range(1000):
                f.write(f"{i},value_{i}\n")
            temp_path = f.name
        
        try:
            source = FileSource(name="test", path=temp_path)
            
            # Stream in batches
            batches = list(source.stream(batch_size=100))
            
            assert len(batches) == 10  # 1000 rows / 100 per batch
            assert len(batches[0]) == 100
            assert batches[0][0]["id"] == "0"
        finally:
            Path(temp_path).unlink()

    def test_custom_delimiter(self):
        """Use custom delimiter for CSV."""
        # Create temp file with semicolon delimiter
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("name;age;city\n")
            f.write("Alice;30;NYC\n")
            temp_path = f.name
        
        try:
            source = FileSource(
                name="test",
                path=temp_path,
                format="csv",
                delimiter=";",
            )
            result = source.fetch()
            
            assert result.success is True
            assert result.data[0]["name"] == "Alice"
            assert result.data[0]["age"] == "30"
        finally:
            Path(temp_path).unlink()


class TestSourceMetadata:
    """Test SourceMetadata dataclass."""

    def test_create_metadata(self):
        """Create metadata with required fields."""
        metadata = SourceMetadata(
            source_name="test_source",
            source_type=SourceType.FILE,
        )
        assert metadata.source_name == "test_source"
        assert metadata.source_type == SourceType.FILE
        assert metadata.content_changed is True

    def test_to_dict(self):
        """Convert metadata to dictionary."""
        metadata = SourceMetadata(
            source_name="test_source",
            source_type=SourceType.FILE,
            content_hash="abc123",
            row_count=100,
        )
        d = metadata.to_dict()
        
        assert d["source_name"] == "test_source"
        assert d["source_type"] == "file"
        assert d["content_hash"] == "abc123"
        assert d["row_count"] == 100


class TestSourceResult:
    """Test SourceResult dataclass."""

    def test_create_ok_result(self):
        """Create successful result."""
        metadata = SourceMetadata(
            source_name="test",
            source_type=SourceType.FILE,
        )
        data = [{"id": 1}, {"id": 2}]
        result = SourceResult.ok(data, metadata)
        
        assert result.success is True
        assert result.data == data
        assert result.metadata.row_count == 2

    def test_create_fail_result(self):
        """Create failed result."""
        from spine.core.errors import SourceError
        
        error = SourceError("Fetch failed")
        result = SourceResult.fail(error)
        
        assert result.success is False
        assert result.error == error
