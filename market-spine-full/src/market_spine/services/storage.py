"""Storage service for file-based data."""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from market_spine.core.settings import get_settings
from market_spine.observability.logging import get_logger

logger = get_logger(__name__)


class StorageService(ABC):
    """Abstract storage service interface."""

    @abstractmethod
    def save(self, key: str, data: bytes | str) -> str:
        """Save data to storage. Returns the full path/URL."""
        pass

    @abstractmethod
    def load(self, key: str) -> bytes | None:
        """Load data from storage."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a key. Returns True if deleted."""
        pass

    @abstractmethod
    def list_keys(self, prefix: str = "") -> list[str]:
        """List keys with optional prefix."""
        pass


class LocalStorage(StorageService):
    """Local filesystem storage."""

    def __init__(self, base_path: str | Path | None = None):
        """Initialize with base path."""
        settings = get_settings()
        self.base_path = Path(base_path or settings.storage_local_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        """Resolve key to full path."""
        return self.base_path / key

    def save(self, key: str, data: bytes | str) -> str:
        """Save data to local file."""
        path = self._resolve_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, str):
            data = data.encode("utf-8")

        path.write_bytes(data)
        logger.debug("local_storage_saved", key=key, size=len(data))
        return str(path)

    def load(self, key: str) -> bytes | None:
        """Load data from local file."""
        path = self._resolve_path(key)
        if not path.exists():
            return None
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        """Check if file exists."""
        return self._resolve_path(key).exists()

    def delete(self, key: str) -> bool:
        """Delete a file."""
        path = self._resolve_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_keys(self, prefix: str = "") -> list[str]:
        """List files with prefix."""
        prefix_path = self.base_path / prefix
        if not prefix_path.exists():
            return []

        if prefix_path.is_file():
            return [prefix]

        return [str(p.relative_to(self.base_path)) for p in prefix_path.rglob("*") if p.is_file()]


class S3Storage(StorageService):
    """AWS S3 storage."""

    def __init__(
        self,
        bucket: str | None = None,
        prefix: str | None = None,
    ):
        """Initialize with bucket and prefix."""
        settings = get_settings()
        self.bucket = bucket or settings.storage_s3_bucket
        self.prefix = prefix or settings.storage_s3_prefix
        self._client = None

    @property
    def client(self):
        """Lazy-load boto3 client."""
        if self._client is None:
            import boto3

            self._client = boto3.client("s3")
        return self._client

    def _resolve_key(self, key: str) -> str:
        """Resolve key with prefix."""
        return f"{self.prefix.rstrip('/')}/{key}"

    def save(self, key: str, data: bytes | str) -> str:
        """Save data to S3."""
        full_key = self._resolve_key(key)

        if isinstance(data, str):
            data = data.encode("utf-8")

        self.client.put_object(
            Bucket=self.bucket,
            Key=full_key,
            Body=data,
        )

        url = f"s3://{self.bucket}/{full_key}"
        logger.debug("s3_storage_saved", key=full_key, size=len(data))
        return url

    def load(self, key: str) -> bytes | None:
        """Load data from S3."""
        full_key = self._resolve_key(key)

        try:
            response = self.client.get_object(
                Bucket=self.bucket,
                Key=full_key,
            )
            return response["Body"].read()
        except self.client.exceptions.NoSuchKey:
            return None

    def exists(self, key: str) -> bool:
        """Check if object exists."""
        full_key = self._resolve_key(key)

        try:
            self.client.head_object(Bucket=self.bucket, Key=full_key)
            return True
        except:
            return False

    def delete(self, key: str) -> bool:
        """Delete an object."""
        full_key = self._resolve_key(key)

        try:
            self.client.delete_object(Bucket=self.bucket, Key=full_key)
            return True
        except:
            return False

    def list_keys(self, prefix: str = "") -> list[str]:
        """List objects with prefix."""
        full_prefix = self._resolve_key(prefix)

        response = self.client.list_objects_v2(
            Bucket=self.bucket,
            Prefix=full_prefix,
        )

        keys = []
        for obj in response.get("Contents", []):
            # Remove the base prefix to return relative keys
            key = obj["Key"]
            if key.startswith(self.prefix):
                key = key[len(self.prefix) :].lstrip("/")
            keys.append(key)

        return keys


def get_storage_service() -> StorageService:
    """Get configured storage service."""
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage()
