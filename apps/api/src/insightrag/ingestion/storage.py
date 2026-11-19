"""Private S3-compatible object access: server-owned keys and KMS-required writes."""

import asyncio
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]


class StorageUnavailable(RuntimeError):
    pass


class ObjectStore(Protocol):
    async def put(self, key: str, data: bytes, media_type: str) -> None: ...
    async def get(self, key: str, maximum: int) -> bytes: ...
    async def delete(self, key: str) -> None: ...


class S3ObjectStore:
    def __init__(
        self, *, bucket: str, region: str, kms_key_id: str, endpoint_url: str | None = None
    ) -> None:
        if (
            not bucket
            or not region
            or not kms_key_id
            or (endpoint_url is not None and not endpoint_url.startswith("https://"))
        ):
            raise ValueError("Private bucket, region, KMS key and HTTPS endpoint are required")
        self.bucket, self.kms_key_id = bucket, kms_key_id
        self.client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url,
            config=Config(connect_timeout=3, read_timeout=15, retries={"max_attempts": 2}),
        )

    async def put(self, key: str, data: bytes, media_type: str) -> None:
        try:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=data,
                ContentType=media_type,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self.kms_key_id,
            )
        except Exception:
            raise StorageUnavailable("Private object write failed") from None

    async def get(self, key: str, maximum: int) -> bytes:
        def read() -> bytes:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            with response["Body"] as body:
                data = body.read(maximum + 1)
            if len(data) > maximum:
                raise StorageUnavailable("Object exceeds configured limit")
            return bytes(data)

        try:
            return await asyncio.to_thread(read)
        except StorageUnavailable:
            raise
        except Exception:
            raise StorageUnavailable("Private object read failed") from None

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)
        except Exception:
            raise StorageUnavailable("Private object deletion failed") from None
