from __future__ import annotations

import os
import re
import uuid
from pathlib import Path


def safe_name(filename: str) -> str:
    return re.sub(r'[^\w.\- ]+', '_', Path(filename).name)[:160] or 'document'


class LocalStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def put(self, user_id: int, kb_id: int, filename: str, data: bytes) -> str:
        key = f'users/{user_id}/knowledge-bases/{kb_id}/documents/{uuid.uuid4().hex}/{safe_name(filename)}'
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


def get_storage():
    if os.getenv('STORAGE_PROVIDER', 'local').lower() == 's3':
        try:
            return S3Storage()
        except Exception:
            pass
    return LocalStorage(os.getenv('LOCAL_STORAGE_PATH', str(Path(__file__).resolve().parents[1] / 'uploads')))


class S3Storage:
    def __init__(self):
        import boto3
        self.bucket = os.getenv('S3_BUCKET', 'study-agent')
        self.client = boto3.client('s3', endpoint_url=os.getenv('S3_ENDPOINT') or None, aws_access_key_id=os.getenv('S3_ACCESS_KEY'), aws_secret_access_key=os.getenv('S3_SECRET_KEY'), region_name=os.getenv('S3_REGION', 'us-east-1'))

    def put(self, user_id: int, kb_id: int, filename: str, data: bytes) -> str:
        key = f'users/{user_id}/knowledge-bases/{kb_id}/documents/{uuid.uuid4().hex}/{safe_name(filename)}'
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ServerSideEncryption='AES256')
        return key

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)['Body'].read()
