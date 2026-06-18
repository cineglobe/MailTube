from __future__ import annotations

import logging
import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config

from mailtube.config import Settings

logger = logging.getLogger(__name__)


class Storage(Protocol):
    def upload(
        self, path: Path, *, job_id: str, filename: str, content_type: str
    ) -> str | None: ...

    def presign(self, object_key: str, filename: str, expires_seconds: int) -> str: ...

    def delete(self, object_key: str | None) -> None: ...

    def test(self) -> dict[str, bool | str]: ...


class LocalStorage:
    def upload(self, path: Path, *, job_id: str, filename: str, content_type: str) -> None:
        return None

    def presign(self, object_key: str, filename: str, expires_seconds: int) -> str:
        raise RuntimeError("Local storage cannot create email-accessible links")

    def delete(self, object_key: str | None) -> None:
        return None

    def test(self) -> dict[str, bool | str]:
        return {"ok": True, "detail": "Local artifact storage is writable"}


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_bucket:
            raise ValueError("MAILTUBE_S3_BUCKET is required for S3 storage")
        addressing = "path" if settings.s3_force_path_style else "auto"
        self.bucket = settings.s3_bucket
        self.instance_id = settings.instance_id
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key.get_secret_value(),
            config=Config(signature_version="s3v4", s3={"addressing_style": addressing}),
        )
        self.transfer = TransferConfig(
            multipart_threshold=16 * 1024 * 1024,
            multipart_chunksize=16 * 1024 * 1024,
            max_concurrency=2,
            use_threads=True,
        )

    def upload(self, path: Path, *, job_id: str, filename: str, content_type: str) -> str:
        month = datetime.now(UTC).strftime("%Y-%m")
        key = f"mailtube/{self.instance_id}/{month}/{job_id}/{uuid.uuid4().hex[:12]}-{filename}"
        self.client.upload_file(
            str(path),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": content_type,
                "ContentDisposition": f'attachment; filename="{filename}"',
            },
            Config=self.transfer,
        )
        return key

    def presign(self, object_key: str, filename: str, expires_seconds: int) -> str:
        return str(
            self.client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self.bucket,
                    "Key": object_key,
                    "ResponseContentDisposition": f'attachment; filename="{filename}"',
                    "ResponseContentType": mimetypes.guess_type(filename)[0]
                    or "application/octet-stream",
                },
                ExpiresIn=max(1, min(expires_seconds, 604800)),
            )
        )

    def delete(self, object_key: str | None) -> None:
        if object_key:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def test(self) -> dict[str, bool | str]:
        key = f"mailtube/connection-tests/{uuid.uuid4().hex}.txt"
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=b"mailtube storage test")
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            valid = response["Body"].read() == b"mailtube storage test"
            self.client.generate_presigned_url(
                "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=60
            )
            return {"ok": valid, "detail": "Write, read, sign, and delete succeeded"}
        except Exception as exc:
            return {"ok": False, "detail": f"Storage test failed: {type(exc).__name__}"}
        finally:
            try:
                self.client.delete_object(Bucket=self.bucket, Key=key)
            except Exception as exc:
                logger.debug("Temporary S3 test object cleanup failed: %s", type(exc).__name__)
