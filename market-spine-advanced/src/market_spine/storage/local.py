"""Local filesystem storage backend."""

import hashlib
import mimetypes
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Iterator

import structlog

from market_spine.storage.base import FileInfo, Storage

logger = structlog.get_logger()


class LocalStorage(Storage):
    """
    Local filesystem storage backend.

    Stores files in a configurable base directory with
    the path structure preserved.
    """

    def __init__(self, base_path: str | Path = "./data"):
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("local_storage_initialized", base_path=str(self.base_path))

    def _resolve_path(self, path: str) -> Path:
        """Resolve a storage path to absolute filesystem path."""
        # Normalize and validate path
        clean_path = Path(path).as_posix().lstrip("/")
        full_path = self.base_path / clean_path

        # Security: ensure path is within base_path
        try:
            full_path.resolve().relative_to(self.base_path.resolve())
        except ValueError:
            raise ValueError(f"Invalid path: {path} (outside base directory)")

        return full_path

    def _compute_checksum(self, content: bytes) -> str:
        """Compute SHA256 checksum."""
        return hashlib.sha256(content).hexdigest()

    def _detect_content_type(self, path: str) -> str | None:
        """Detect content type from file extension."""
        content_type, _ = mimetypes.guess_type(path)
        return content_type

    def write(self, path: str, content: bytes | str, content_type: str | None = None) -> FileInfo:
        """Write content to local filesystem."""
        full_path = self._resolve_path(path)

        # Ensure parent directory exists
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert string to bytes if needed
        if isinstance(content, str):
            content = content.encode("utf-8")

        # Write file
        full_path.write_bytes(content)

        # Auto-detect content type if not provided
        if content_type is None:
            content_type = self._detect_content_type(path)

        logger.info("file_written", path=path, size=len(content))

        return FileInfo(
            path=path,
            size_bytes=len(content),
            content_type=content_type,
            last_modified=datetime.now(),
            checksum=self._compute_checksum(content),
        )

    def write_stream(
        self, path: str, stream: BinaryIO, content_type: str | None = None
    ) -> FileInfo:
        """Write a stream to local filesystem."""
        content = stream.read()
        return self.write(path, content, content_type)

    def read(self, path: str) -> bytes:
        """Read content from local filesystem."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        return full_path.read_bytes()

    def read_stream(self, path: str) -> BinaryIO:
        """Read content as a stream."""
        content = self.read(path)
        return BytesIO(content)

    def exists(self, path: str) -> bool:
        """Check if file exists."""
        full_path = self._resolve_path(path)
        return full_path.exists() and full_path.is_file()

    def delete(self, path: str) -> bool:
        """Delete a file."""
        full_path = self._resolve_path(path)

        if not full_path.exists():
            return False

        full_path.unlink()
        logger.info("file_deleted", path=path)
        return True

    def list(self, prefix: str = "") -> Iterator[FileInfo]:
        """List files with the given prefix."""
        if prefix:
            search_path = self._resolve_path(prefix)
            if search_path.is_file():
                info = self.info(prefix)
                if info:
                    yield info
                return
            search_dir = search_path if search_path.is_dir() else search_path.parent
        else:
            search_dir = self.base_path

        if not search_dir.exists():
            return

        for file_path in search_dir.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(self.base_path).as_posix()
                if rel_path.startswith(prefix):
                    stat = file_path.stat()
                    yield FileInfo(
                        path=rel_path,
                        size_bytes=stat.st_size,
                        content_type=None,
                        last_modified=datetime.fromtimestamp(stat.st_mtime),
                    )

    def info(self, path: str) -> FileInfo | None:
        """Get information about a file."""
        full_path = self._resolve_path(path)

        if not full_path.exists() or not full_path.is_file():
            return None

        stat = full_path.stat()
        return FileInfo(
            path=path,
            size_bytes=stat.st_size,
            content_type=None,
            last_modified=datetime.fromtimestamp(stat.st_mtime),
        )
