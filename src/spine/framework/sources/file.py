"""
File source adapter for local file ingestion.

Supports:
- CSV (comma-separated)
- PSV (pipe-separated)
- TSV (tab-separated)
- JSON (array of objects or newline-delimited)
- Parquet (requires pyarrow)

Design Principles:
- #4 Protocol over Inheritance: Implements Source protocol
- #6 Idempotency: Uses content hash for change detection
- #7 Explicit over Implicit: Clear format specification

Usage:
    from spine.framework.sources.file import FileSource
    
    # Auto-detect format from extension
    source = FileSource(name="trades", path="/data/trades.csv")
    result = source.fetch()
    
    # Explicit format and options
    source = FileSource(
        name="otc_data",
        path="/data/otc.psv",
        format="psv",
        encoding="utf-8",
        skip_header=True,
    )
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

from spine.core.errors import ParseError, SourceError, SourceNotFoundError
from spine.framework.sources.protocol import (
    BaseSource,
    SourceMetadata,
    SourceResult,
    SourceType,
    StreamingSource,
    CachingSource,
)


class FileFormat(str, Enum):
    """Supported file formats."""
    
    CSV = "csv"
    PSV = "psv"
    TSV = "tsv"
    JSON = "json"
    JSONL = "jsonl"  # JSON Lines (newline-delimited)
    PARQUET = "parquet"


# Extension to format mapping
EXTENSION_MAP = {
    ".csv": FileFormat.CSV,
    ".psv": FileFormat.PSV,
    ".tsv": FileFormat.TSV,
    ".json": FileFormat.JSON,
    ".jsonl": FileFormat.JSONL,
    ".ndjson": FileFormat.JSONL,
    ".parquet": FileFormat.PARQUET,
    ".pq": FileFormat.PARQUET,
}


@dataclass
class FileSourceConfig:
    """Configuration for file source."""
    
    path: str | Path
    format: FileFormat | None = None  # Auto-detect if None
    encoding: str = "utf-8"
    delimiter: str | None = None  # Override for CSV/PSV/TSV
    quote_char: str = '"'
    skip_header: bool = False  # Skip first row (for pre-processed files)
    column_names: list[str] | None = None  # Override column names
    
    # JSON options
    json_path: str | None = None  # JSONPath to extract array from
    
    # Change detection
    use_content_hash: bool = True
    use_mtime: bool = True


class FileSource(BaseSource, StreamingSource, CachingSource):
    """
    Source for reading data from local files.
    
    Supports streaming for large files and caching with
    content-based change detection.
    """
    
    def __init__(
        self,
        name: str,
        path: str | Path,
        *,
        format: FileFormat | str | None = None,
        encoding: str = "utf-8",
        delimiter: str | None = None,
        column_names: list[str] | None = None,
        domain: str | None = None,
        **kwargs: Any,
    ):
        super().__init__(name=name, source_type=SourceType.FILE, domain=domain)
        
        self._path = Path(path) if isinstance(path, str) else path
        self._encoding = encoding
        self._delimiter = delimiter
        self._column_names = column_names
        self._kwargs = kwargs
        
        # Determine format
        if format is None:
            self._format = self._detect_format()
        elif isinstance(format, str):
            self._format = FileFormat(format.lower())
        else:
            self._format = format
        
        # Set delimiter based on format if not specified
        if self._delimiter is None:
            self._delimiter = self._get_default_delimiter()
    
    @property
    def path(self) -> Path:
        """File path."""
        return self._path
    
    @property
    def format(self) -> FileFormat:
        """File format."""
        return self._format
    
    @property
    def supports_streaming(self) -> bool:
        """Streaming supported for CSV/PSV/TSV/JSONL."""
        return self._format in (
            FileFormat.CSV,
            FileFormat.PSV,
            FileFormat.TSV,
            FileFormat.JSONL,
        )
    
    def _detect_format(self) -> FileFormat:
        """Detect format from file extension."""
        ext = self._path.suffix.lower()
        if ext in EXTENSION_MAP:
            return EXTENSION_MAP[ext]
        raise SourceError(
            f"Cannot detect format for extension: {ext}",
        ).with_context(source_name=self._name, path=str(self._path))
    
    def _get_default_delimiter(self) -> str:
        """Get default delimiter for format."""
        match self._format:
            case FileFormat.CSV:
                return ","
            case FileFormat.PSV:
                return "|"
            case FileFormat.TSV:
                return "\t"
            case _:
                return ","
    
    def _get_file_info(self) -> tuple[int, datetime]:
        """Get file size and modification time."""
        stat = self._path.stat()
        return stat.st_size, datetime.fromtimestamp(stat.st_mtime)
    
    def _compute_content_hash(self) -> str:
        """Compute SHA-256 hash of file contents."""
        sha = hashlib.sha256()
        with open(self._path, "rb") as f:
            while chunk := f.read(8192):
                sha.update(chunk)
        return sha.hexdigest()
    
    def get_cache_key(self, params: dict[str, Any] | None = None) -> str:
        """Generate cache key for the file."""
        # Include path and any params in key
        key_parts = [str(self._path.absolute())]
        if params:
            key_parts.extend(f"{k}={v}" for k, v in sorted(params.items()))
        return hashlib.md5("|".join(key_parts).encode()).hexdigest()
    
    def has_changed(
        self,
        params: dict[str, Any] | None = None,
        last_hash: str | None = None,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> bool:
        """Check if file has changed since last fetch."""
        if not self._path.exists():
            return True  # File doesn't exist, will fail on fetch
        
        # Check modification time first (fast)
        if last_modified:
            try:
                _, mtime = self._get_file_info()
                if mtime.isoformat() == last_modified:
                    return False
            except OSError:
                pass
        
        # Check content hash (slower but accurate)
        if last_hash:
            current_hash = self._compute_content_hash()
            return current_hash != last_hash
        
        return True  # Unknown, assume changed
    
    def fetch(self, params: dict[str, Any] | None = None) -> SourceResult:
        """
        Fetch all data from the file.
        
        For large files, prefer stream() to avoid memory issues.
        """
        start_time = datetime.now()
        
        # Check file exists
        if not self._path.exists():
            error = SourceNotFoundError(
                f"File not found: {self._path}",
            ).with_context(source_name=self._name, path=str(self._path))
            return SourceResult.fail(error)
        
        try:
            # Get file info
            size, mtime = self._get_file_info()
            content_hash = self._compute_content_hash()
            
            # Read data based on format
            match self._format:
                case FileFormat.CSV | FileFormat.PSV | FileFormat.TSV:
                    data = self._read_delimited()
                case FileFormat.JSON:
                    data = self._read_json()
                case FileFormat.JSONL:
                    data = self._read_jsonl()
                case FileFormat.PARQUET:
                    data = self._read_parquet()
                case _:
                    raise SourceError(f"Unsupported format: {self._format}")
            
            # Create metadata
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            metadata = self._create_metadata(
                params=params,
                path=str(self._path),
                content_hash=content_hash,
                last_modified=mtime.isoformat(),
                bytes_fetched=size,
                duration_ms=duration_ms,
            )
            
            return SourceResult.ok(data, metadata)
            
        except SourceError:
            raise
        except Exception as e:
            error = self._wrap_error(e, f"Failed to read file: {self._path}")
            return SourceResult.fail(error)
    
    def stream(
        self,
        params: dict[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> Iterator[list[dict[str, Any]]]:
        """
        Stream data from file in batches.
        
        Only supported for CSV, PSV, TSV, and JSONL formats.
        """
        if not self.supports_streaming:
            raise SourceError(
                f"Streaming not supported for format: {self._format}",
            ).with_context(source_name=self._name)
        
        if not self._path.exists():
            raise SourceNotFoundError(
                f"File not found: {self._path}",
            ).with_context(source_name=self._name, path=str(self._path))
        
        match self._format:
            case FileFormat.CSV | FileFormat.PSV | FileFormat.TSV:
                yield from self._stream_delimited(batch_size)
            case FileFormat.JSONL:
                yield from self._stream_jsonl(batch_size)
    
    # -------------------------------------------------------------------------
    # FORMAT-SPECIFIC READERS
    # -------------------------------------------------------------------------
    
    def _read_delimited(self) -> list[dict[str, Any]]:
        """Read CSV/PSV/TSV file."""
        data = []
        with open(self._path, "r", encoding=self._encoding, newline="") as f:
            reader = csv.DictReader(
                f,
                delimiter=self._delimiter,
                fieldnames=self._column_names,
            )
            for row in reader:
                data.append(dict(row))
        return data
    
    def _stream_delimited(self, batch_size: int) -> Iterator[list[dict[str, Any]]]:
        """Stream CSV/PSV/TSV file."""
        batch = []
        with open(self._path, "r", encoding=self._encoding, newline="") as f:
            reader = csv.DictReader(
                f,
                delimiter=self._delimiter,
                fieldnames=self._column_names,
            )
            for row in reader:
                batch.append(dict(row))
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
    
    def _read_json(self) -> list[dict[str, Any]]:
        """Read JSON file (expects array of objects)."""
        with open(self._path, "r", encoding=self._encoding) as f:
            data = json.load(f)
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Try to find array in common locations
            for key in ("data", "items", "results", "records", "rows"):
                if key in data and isinstance(data[key], list):
                    return data[key]
            # Wrap single object in list
            return [data]
        else:
            raise ParseError(
                f"Expected JSON array or object, got: {type(data).__name__}",
            ).with_context(source_name=self._name, path=str(self._path))
    
    def _read_jsonl(self) -> list[dict[str, Any]]:
        """Read JSON Lines file."""
        data = []
        with open(self._path, "r", encoding=self._encoding) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ParseError(
                        f"Invalid JSON at line {line_num}: {e}",
                    ).with_context(source_name=self._name, path=str(self._path))
        return data
    
    def _stream_jsonl(self, batch_size: int) -> Iterator[list[dict[str, Any]]]:
        """Stream JSON Lines file."""
        batch = []
        with open(self._path, "r", encoding=self._encoding) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    batch.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ParseError(
                        f"Invalid JSON at line {line_num}: {e}",
                    ).with_context(source_name=self._name, path=str(self._path))
                
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
        if batch:
            yield batch
    
    def _read_parquet(self) -> list[dict[str, Any]]:
        """Read Parquet file (requires pyarrow)."""
        try:
            import pyarrow.parquet as pq
        except ImportError:
            raise SourceError(
                "pyarrow is required for Parquet support. "
                "Install with: pip install pyarrow",
            ).with_context(source_name=self._name)
        
        table = pq.read_table(self._path)
        return table.to_pylist()


__all__ = [
    "FileFormat",
    "FileSourceConfig",
    "FileSource",
]
