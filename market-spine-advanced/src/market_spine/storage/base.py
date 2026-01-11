"""Base storage interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import BinaryIO, Iterator


@dataclass
class FileInfo:
    """Information about a stored file."""

    path: str
    size_bytes: int
    content_type: str | None
    last_modified: datetime | None
    checksum: str | None = None
    metadata: dict | None = None


class Storage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def write(self, path: str, content: bytes | str, content_type: str | None = None) -> FileInfo:
        """
        Write content to storage.

        Args:
            path: Storage path (e.g., "data/trades/2024-01-15.csv")
            content: File content (bytes or string)
            content_type: Optional MIME type

        Returns:
            FileInfo with details about the stored file
        """
        ...

    @abstractmethod
    def write_stream(
        self, path: str, stream: BinaryIO, content_type: str | None = None
    ) -> FileInfo:
        """
        Write a stream to storage.

        Args:
            path: Storage path
            stream: Binary stream to write
            content_type: Optional MIME type

        Returns:
            FileInfo with details about the stored file
        """
        ...

    @abstractmethod
    def read(self, path: str) -> bytes:
        """
        Read content from storage.

        Args:
            path: Storage path

        Returns:
            File content as bytes

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        ...

    @abstractmethod
    def read_stream(self, path: str) -> BinaryIO:
        """
        Read content as a stream.

        Args:
            path: Storage path

        Returns:
            Binary stream
        """
        ...

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Check if a file exists."""
        ...

    @abstractmethod
    def delete(self, path: str) -> bool:
        """
        Delete a file.

        Returns:
            True if deleted, False if didn't exist
        """
        ...

    @abstractmethod
    def list(self, prefix: str = "") -> Iterator[FileInfo]:
        """
        List files with the given prefix.

        Args:
            prefix: Path prefix to filter by

        Yields:
            FileInfo for each matching file
        """
        ...

    @abstractmethod
    def info(self, path: str) -> FileInfo | None:
        """
        Get information about a file.

        Returns:
            FileInfo or None if file doesn't exist
        """
        ...

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Read content as text."""
        return self.read(path).decode(encoding)

    def write_text(self, path: str, content: str, encoding: str = "utf-8") -> FileInfo:
        """Write text content."""
        return self.write(path, content.encode(encoding), content_type="text/plain")
