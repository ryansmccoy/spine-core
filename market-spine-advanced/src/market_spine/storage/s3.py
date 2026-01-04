"""S3-compatible object storage backend."""

import hashlib
from datetime import datetime
from io import BytesIO
from typing import BinaryIO, Iterator

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import structlog

from market_spine.storage.base import FileInfo, Storage

logger = structlog.get_logger()


class S3Storage(Storage):
    """
    S3-compatible object storage backend.

    Works with AWS S3, MinIO, LocalStack, and other S3-compatible services.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
    ):
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.region = region

        # Build client config
        client_kwargs = {
            "service_name": "s3",
            "region_name": region,
            "config": Config(signature_version="s3v4"),
        }

        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        if access_key and secret_key:
            client_kwargs["aws_access_key_id"] = access_key
            client_kwargs["aws_secret_access_key"] = secret_key

        self.client = boto3.client(**client_kwargs)

        logger.info(
            "s3_storage_initialized",
            bucket=bucket,
            endpoint=endpoint_url,
            region=region,
        )

    def _compute_checksum(self, content: bytes) -> str:
        """Compute SHA256 checksum."""
        return hashlib.sha256(content).hexdigest()

    def write(self, path: str, content: bytes | str, content_type: str | None = None) -> FileInfo:
        """Write content to S3."""
        # Normalize path
        key = path.lstrip("/")

        # Convert string to bytes if needed
        if isinstance(content, str):
            content = content.encode("utf-8")

        # Upload
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            **extra_args,
        )

        logger.info("s3_file_written", bucket=self.bucket, key=key, size=len(content))

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
        """Write a stream to S3."""
        key = path.lstrip("/")

        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type

        self.client.upload_fileobj(
            stream,
            self.bucket,
            key,
            ExtraArgs=extra_args if extra_args else None,
        )

        # Get file info after upload
        info = self.info(path)
        if info:
            return info

        return FileInfo(
            path=path,
            size_bytes=0,
            content_type=content_type,
            last_modified=datetime.now(),
        )

    def read(self, path: str) -> bytes:
        """Read content from S3."""
        key = path.lstrip("/")

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {path}")
            raise

    def read_stream(self, path: str) -> BinaryIO:
        """Read content as a stream."""
        key = path.lstrip("/")

        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise FileNotFoundError(f"File not found: {path}")
            raise

    def exists(self, path: str) -> bool:
        """Check if file exists."""
        key = path.lstrip("/")

        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def delete(self, path: str) -> bool:
        """Delete a file."""
        key = path.lstrip("/")

        if not self.exists(path):
            return False

        self.client.delete_object(Bucket=self.bucket, Key=key)
        logger.info("s3_file_deleted", bucket=self.bucket, key=key)
        return True

    def list(self, prefix: str = "") -> Iterator[FileInfo]:
        """List files with the given prefix."""
        prefix = prefix.lstrip("/")

        paginator = self.client.get_paginator("list_objects_v2")

        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                yield FileInfo(
                    path=obj["Key"],
                    size_bytes=obj["Size"],
                    content_type=None,
                    last_modified=obj["LastModified"],
                )

    def info(self, path: str) -> FileInfo | None:
        """Get information about a file."""
        key = path.lstrip("/")

        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
            return FileInfo(
                path=path,
                size_bytes=response["ContentLength"],
                content_type=response.get("ContentType"),
                last_modified=response["LastModified"],
                checksum=response.get("ETag", "").strip('"'),
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return None
            raise
