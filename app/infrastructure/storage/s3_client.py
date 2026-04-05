"""
Amazon S3 storage client.

Handles upload, download, presigned URL generation, and deletion
of original document files. Uses boto3 with async-friendly patterns
(boto3 is synchronous; for high-throughput, consider aioboto3).
"""
from __future__ import annotations

import io
import mimetypes
import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import boto3
from botocore.exceptions import ClientError
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.exceptions import StorageUploadError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class UploadResult:
    """Result of a successful S3 upload."""
    bucket: str
    key: str           # full S3 key (path within bucket)
    url: str           # s3://bucket/key URI
    size_bytes: int


class S3StorageClient:
    """
    S3 adapter for storing and retrieving original document files.

    Responsibilities:
    - upload_file: stores raw bytes; returns UploadResult
    - download_file: returns raw bytes
    - get_presigned_url: generate a time-limited download URL
    - delete_file: removes a file by key

    Key format: {prefix}{agent_id}/{document_id}/{filename}
    Example:    uploads/agent-abc/doc-xyz/manual.pdf
    """

    def __init__(
        self,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
        prefix: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
    ) -> None:
        self._bucket = bucket or settings.s3_bucket_name
        self._region = region or settings.s3_region
        self._prefix = prefix or settings.s3_prefix

        session = boto3.Session(
            aws_access_key_id=aws_access_key_id or settings.aws_access_key_id or None,
            aws_secret_access_key=aws_secret_access_key or settings.aws_secret_access_key or None,
            region_name=self._region,
        )
        self._s3 = session.client("s3")

        logger.info(
            "S3StorageClient initialized",
            bucket=self._bucket,
            region=self._region,
            prefix=self._prefix,
        )

    def _build_key(self, agent_id: str, document_id: str, filename: str) -> str:
        """Construct the S3 object key."""
        safe_filename = os.path.basename(filename)
        return f"{self._prefix}{agent_id}/{document_id}/{safe_filename}"

    # ── Upload ────────────────────────────────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    async def upload_file(
        self,
        file_content: bytes,
        agent_id: str,
        document_id: str,
        filename: str,
        content_type: Optional[str] = None,
    ) -> UploadResult:
        """
        Upload raw file bytes to S3.

        Args:
            file_content: Raw bytes of the file.
            agent_id: Used to namespace the S3 path.
            document_id: Used to namespace the S3 path.
            filename: Original filename (sanitized for S3).
            content_type: MIME type (auto-detected if not provided).

        Returns:
            UploadResult with bucket, key, url and size.
        """
        key = self._build_key(agent_id, document_id, filename)
        detected_type = content_type or (
            mimetypes.guess_type(filename)[0] or "application/octet-stream"
        )

        try:
            self._s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=file_content,
                ContentType=detected_type,
                # Enable server-side encryption
                ServerSideEncryption="AES256",
            )

            size = len(file_content)
            url = f"s3://{self._bucket}/{key}"

            logger.info(
                "File uploaded to S3",
                bucket=self._bucket,
                key=key,
                size_bytes=size,
            )

            return UploadResult(
                bucket=self._bucket,
                key=key,
                url=url,
                size_bytes=size,
            )

        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error(
                "S3 upload failed",
                key=key,
                error_code=error_code,
                error=str(exc),
            )
            raise StorageUploadError(filename=filename, detail=str(exc)) from exc

    # ── Download ──────────────────────────────────────────────────────────────

    async def download_file(self, key: str) -> bytes:
        """Download a file from S3 by its full key. Returns raw bytes."""
        try:
            response = self._s3.get_object(Bucket=self._bucket, Key=key)
            content: bytes = response["Body"].read()
            logger.info("File downloaded from S3", key=key, size=len(content))
            return content

        except ClientError as exc:
            error_code = exc.response["Error"]["Code"]
            logger.error("S3 download failed", key=key, error_code=error_code)
            raise StorageUploadError(filename=key, detail=str(exc)) from exc

    # ── Presigned URL ─────────────────────────────────────────────────────────

    async def get_presigned_url(self, key: str, expiry_seconds: int = 3600) -> str:
        """
        Generate a presigned URL for time-limited direct download.
        Default expiry: 1 hour.
        """
        try:
            url: str = self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiry_seconds,
            )
            return url
        except ClientError as exc:
            logger.error("Failed to generate presigned URL", key=key, error=str(exc))
            raise StorageUploadError(filename=key, detail=str(exc)) from exc

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_file(self, key: str) -> None:
        """Delete a single file from S3 by its key."""
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
            logger.info("File deleted from S3", key=key)
        except ClientError as exc:
            logger.error("S3 delete failed", key=key, error=str(exc))
            raise StorageUploadError(filename=key, detail=str(exc)) from exc

    async def delete_agent_folder(self, agent_id: str) -> int:
        """
        Delete all files under the agent's prefix.
        Returns the number of deleted objects.
        """
        prefix = f"{self._prefix}{agent_id}/"
        deleted = 0
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                objects = page.get("Contents", [])
                if not objects:
                    continue
                delete_payload = {"Objects": [{"Key": obj["Key"]} for obj in objects]}
                self._s3.delete_objects(Bucket=self._bucket, Delete=delete_payload)
                deleted += len(objects)

            logger.info(
                "Agent folder deleted from S3",
                prefix=prefix,
                deleted_count=deleted,
            )
            return deleted

        except ClientError as exc:
            logger.error("S3 delete_agent_folder failed", prefix=prefix, error=str(exc))
            raise StorageUploadError(filename=prefix, detail=str(exc)) from exc
