"""StorageProvider + local filesystem implementation (S3/MinIO-compatible in production)."""
import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO, Protocol

from app.core.config import settings

SAFE_KEY = re.compile(r"[^a-zA-Z0-9/_.-]")


class StorageProvider(Protocol):
    def put(self, key: str, data: BinaryIO, content_type: str | None = None) -> str: ...
    def get_path(self, key: str) -> str: ...
    def delete(self, key: str) -> None: ...
    def random_key(self, prefix: str, ext: str) -> str: ...


class LocalStorageProvider:
    """Stores objects under data/uploads. `key` is server-generated; user filenames
    are only ever stored as display_name (see security review)."""

    def __init__(self) -> None:
        self.root = Path(settings.STORAGE_LOCAL_DIR)
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        clean = SAFE_KEY.sub("_", key).lstrip("/")
        path = (self.root / clean).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("path traversal blocked")
        return path

    def put(self, key: str, data: BinaryIO, content_type: str | None = None) -> str:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data.read())
        return key

    def get_path(self, key: str) -> str:
        return str(self._resolve(key))

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.exists():
            os.remove(path)

    def random_key(self, prefix: str, ext: str) -> str:
        return f"{prefix}/{uuid.uuid4().hex}.{ext.lstrip('.')}"


_storage: StorageProvider | None = None


def get_storage() -> StorageProvider:
    global _storage
    if _storage is None:
        # s3-compatible provider can be added here; local keeps dev self-contained
        _storage = LocalStorageProvider()
    return _storage
