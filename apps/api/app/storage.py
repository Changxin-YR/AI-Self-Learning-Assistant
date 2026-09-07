from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from .providers import dev_mode


def safe_name(filename: str) -> str:
    return re.sub(r"[^\w.\- ]+", "_", Path(filename).name)[:160] or "document"


def storage_key(user_id: int, kb_id: int, filename: str) -> str:
    return f"users/{user_id}/knowledge-bases/{kb_id}/documents/{uuid.uuid4().hex}/{safe_name(filename)}"


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _target(self, key: str) -> Path:
        if not key:
            raise ValueError("STORAGE_KEY_REQUIRED")
        target = (self.root / key).resolve()
        if target != self.root and self.root not in target.parents:
            raise ValueError("STORAGE_KEY_INVALID")
        return target

    def put(self, user_id: int, kb_id: int, filename: str, data: bytes) -> str:
        key = storage_key(user_id, kb_id, filename)
        target = self._target(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return self._target(key).read_bytes()

    def delete(self, key: str) -> None:
        if not key:
            return
        target = self._target(key)
        if target.exists():
            target.unlink()

    def health(self) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        return "ok"


class S3Storage:
    def __init__(self):
        import boto3
        self.bucket = os.getenv("S3_BUCKET", "").strip()
        endpoint = os.getenv("S3_ENDPOINT", "").strip()
        access_key = os.getenv("S3_ACCESS_KEY", "").strip()
        secret_key = os.getenv("S3_SECRET_KEY", "").strip()
        if not self.bucket or not access_key or not secret_key:
            raise RuntimeError("S3_CONFIGURATION_REQUIRED")
        self.client = boto3.client("s3", endpoint_url=endpoint or None, aws_access_key_id=access_key, aws_secret_access_key=secret_key, region_name=os.getenv("S3_REGION", "us-east-1"))

    def put(self, user_id: int, kb_id: int, filename: str, data: bytes) -> str:
        key = storage_key(user_id, kb_id, filename)
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption="AES256")
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        if not key:
            return
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def health(self) -> str:
        self.client.head_bucket(Bucket=self.bucket)
        return "ok"


def get_storage():
    provider = os.getenv("STORAGE_PROVIDER", "local").lower()
    if provider == "local":
        if not dev_mode():
            raise RuntimeError("LOCAL_STORAGE_FORBIDDEN")
        return LocalStorage(os.getenv("LOCAL_STORAGE_PATH", str(Path(__file__).resolve().parents[1] / "uploads")))
    if provider == "s3":
        return S3Storage()
    raise RuntimeError("STORAGE_PROVIDER_UNSUPPORTED")
