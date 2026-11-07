"""S3-compatible object storage (MinIO in development). Blocking boto3 calls run in worker threads.

Originals are write-once: keys embed the document UUID, so no key is ever overwritten, and the
bucket has versioning enabled (docker-compose ``minio-init``)."""

import asyncio
from collections.abc import Iterator
from functools import lru_cache
from typing import IO, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.errors import NotFoundError, ServiceUnavailableError

CHUNK = 1024 * 1024


class ObjectStore(Protocol):
    async def put(
        self, key: str, fileobj: IO[bytes], *, content_type: str, sha256: str
    ) -> None: ...
    def iter_chunks(self, key: str) -> Iterator[bytes]: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...


class S3ObjectStore:
    def __init__(
        self, *, endpoint: str, access_key: str, secret_key: str, bucket: str, region: str
    ) -> None:
        self._bucket = bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=60,
            ),
        )

    async def put(self, key: str, fileobj: IO[bytes], *, content_type: str, sha256: str) -> None:
        def _put() -> None:
            fileobj.seek(0)
            self._s3.upload_fileobj(
                fileobj,
                self._bucket,
                key,
                ExtraArgs={"ContentType": content_type, "Metadata": {"sha256": sha256}},
            )

        try:
            await asyncio.to_thread(_put)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("File storage is temporarily unavailable") from exc

    def iter_chunks(self, key: str) -> Iterator[bytes]:
        """Synchronous generator; consume it with ``iterate_in_threadpool``."""
        try:
            body = self._s3.get_object(Bucket=self._bucket, Key=key)["Body"]
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                raise NotFoundError("File content not found") from exc
            raise ServiceUnavailableError("File storage is temporarily unavailable") from exc
        except BotoCoreError as exc:
            raise ServiceUnavailableError("File storage is temporarily unavailable") from exc
        try:
            yield from body.iter_chunks(CHUNK)
        finally:
            body.close()

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._s3.delete_object, Bucket=self._bucket, Key=key)
        except (BotoCoreError, ClientError) as exc:
            raise ServiceUnavailableError("File storage is temporarily unavailable") from exc

    async def exists(self, key: str) -> bool:
        try:
            await asyncio.to_thread(self._s3.head_object, Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise ServiceUnavailableError("File storage is temporarily unavailable") from exc
        return True


@lru_cache
def get_object_store() -> ObjectStore:
    s = get_settings()
    return S3ObjectStore(
        endpoint=s.minio_endpoint,
        access_key=s.minio_access_key.get_secret_value(),
        secret_key=s.minio_secret_key.get_secret_value(),
        bucket=s.minio_bucket,
        region=s.s3_region,
    )
