"""Storage abstraction for file management."""

from market_spine.storage.base import Storage
from market_spine.storage.local import LocalStorage
from market_spine.storage.s3 import S3Storage

__all__ = ["Storage", "LocalStorage", "S3Storage", "get_storage"]


_storage: Storage | None = None


def get_storage() -> Storage:
    """Get or create storage instance based on configuration."""
    global _storage
    if _storage is None:
        from market_spine.config import get_settings

        settings = get_settings()

        if settings.storage_type == "s3":
            _storage = S3Storage(
                bucket=settings.storage_s3_bucket,
                endpoint_url=settings.storage_s3_endpoint,
                region=settings.storage_s3_region,
                access_key=settings.storage_s3_access_key,
                secret_key=settings.storage_s3_secret_key,
            )
        else:
            _storage = LocalStorage(base_path=settings.storage_local_path)

    return _storage


def reset_storage() -> None:
    """Reset storage instance (for testing)."""
    global _storage
    _storage = None
