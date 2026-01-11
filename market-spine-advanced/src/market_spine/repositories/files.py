"""File repository - Metadata tracking for stored files."""

import ulid
import structlog

from market_spine.db import get_connection
from market_spine.storage.base import FileInfo

logger = structlog.get_logger()


class FileRepository:
    """Repository for file metadata."""

    @staticmethod
    def record(file_info: FileInfo, storage_type: str, metadata: dict | None = None) -> str:
        """Record file metadata in database."""
        file_id = str(ulid.new())
        metadata = metadata or {}

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO stored_files (id, path, storage_type, size_bytes, content_type, checksum, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (path) DO UPDATE
                SET storage_type = EXCLUDED.storage_type,
                    size_bytes = EXCLUDED.size_bytes,
                    content_type = EXCLUDED.content_type,
                    checksum = EXCLUDED.checksum,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    file_id,
                    file_info.path,
                    storage_type,
                    file_info.size_bytes,
                    file_info.content_type,
                    file_info.checksum,
                    metadata,
                ),
            )
            row = conn.fetchone()
            conn.commit()
            return row["id"] if row else file_id

    @staticmethod
    def get(path: str) -> dict | None:
        """Get file metadata by path."""
        with get_connection() as conn:
            result = conn.execute(
                """
                SELECT id, path, storage_type, size_bytes, content_type, 
                       checksum, metadata, created_at, updated_at
                FROM stored_files
                WHERE path = %s
                """,
                (path,),
            )
            row = result.fetchone()
            return dict(row) if row else None

    @staticmethod
    def list_files(
        prefix: str | None = None,
        storage_type: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """List file metadata with optional filters."""
        conditions = []
        params = []

        if prefix:
            conditions.append("path LIKE %s")
            params.append(f"{prefix}%")
        if storage_type:
            conditions.append("storage_type = %s")
            params.append(storage_type)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with get_connection() as conn:
            result = conn.execute(
                f"""
                SELECT id, path, storage_type, size_bytes, content_type, created_at
                FROM stored_files
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (*params, limit),
            )
            return [dict(row) for row in result.fetchall()]

    @staticmethod
    def delete(path: str) -> bool:
        """Delete file metadata."""
        with get_connection() as conn:
            result = conn.execute(
                "DELETE FROM stored_files WHERE path = %s RETURNING id",
                (path,),
            )
            deleted = result.fetchone() is not None
            conn.commit()
            return deleted
