"""Photo storage adapters: Supabase Storage (private bucket + signed URLs) or local disk."""

from __future__ import annotations

import hashlib
import hmac
import time
from functools import lru_cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.core.config import Settings, StorageBackend, get_settings
from app.core.errors import DomainError, ForbiddenError, NotFoundError
from app.core.logging import get_logger

log = get_logger(__name__)


class StorageProvider(Protocol):
    name: str

    async def upload(self, path: str, data: bytes, content_type: str) -> None: ...

    async def download(self, path: str) -> bytes: ...

    async def delete(self, paths: list[str]) -> None: ...

    async def signed_url(self, path: str) -> str: ...

    async def signed_urls(self, paths: list[str]) -> dict[str, str]: ...


class StorageError(DomainError):
    status_code = 502
    code = "STORAGE_ERROR"


def _safe_relative(path: str) -> str:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ForbiddenError("Invalid storage path")
    return rel.as_posix()


class LocalStorageProvider:
    """Stores files on disk and serves them via HMAC-signed URLs on ``/files/...``."""

    name = "local"

    def __init__(self, root: Path, public_base_url: str, secret: bytes, ttl_seconds: int):
        self.root = root
        self.public_base_url = public_base_url.rstrip("/")
        self.secret = secret
        self.ttl_seconds = ttl_seconds

    def _file(self, path: str) -> Path:
        return self.root / _safe_relative(path)

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        target = self._file(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    async def download(self, path: str) -> bytes:
        target = self._file(path)
        if not target.is_file():
            raise NotFoundError("File not found")
        return target.read_bytes()

    async def delete(self, paths: list[str]) -> None:
        for path in paths:
            self._file(path).unlink(missing_ok=True)

    def sign(self, path: str, expires: int) -> str:
        message = f"{_safe_relative(path)}:{expires}".encode()
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def verify(self, path: str, expires: int, signature: str) -> Path:
        if expires < int(time.time()):
            raise ForbiddenError("Link expired")
        if not hmac.compare_digest(self.sign(path, expires), signature):
            raise ForbiddenError("Invalid signature")
        target = self._file(path)
        if not target.is_file():
            raise NotFoundError("File not found")
        return target

    async def signed_url(self, path: str) -> str:
        expires = int(time.time()) + self.ttl_seconds
        # Round expiry so URLs are stable within a window (better browser caching).
        expires -= expires % 300
        expires += 300
        return f"{self.public_base_url}/files/{quote(path)}?exp={expires}&sig={self.sign(path, expires)}"

    async def signed_urls(self, paths: list[str]) -> dict[str, str]:
        return {path: await self.signed_url(path) for path in paths}


class SupabaseStorageProvider:
    name = "supabase"

    def __init__(self, supabase_url: str, service_key: str, bucket: str, ttl_seconds: int):
        self.base = supabase_url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.ttl_seconds = ttl_seconds
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={"Authorization": f"Bearer {service_key}", "apikey": service_key},
        )

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        url = f"{self.base}/object/{self.bucket}/{quote(_safe_relative(path))}"
        resp = await self._client.post(
            url, content=data, headers={"Content-Type": content_type, "x-upsert": "true"}
        )
        if resp.status_code >= 400:
            log.error("storage_upload_failed", path=path, status=resp.status_code, body=resp.text[:300])
            raise StorageError("Failed to upload file to storage")

    async def download(self, path: str) -> bytes:
        resp = await self._client.get(f"{self.base}/object/{self.bucket}/{quote(_safe_relative(path))}")
        if resp.status_code == 404 or resp.status_code == 400:
            raise NotFoundError("File not found")
        if resp.status_code >= 400:
            raise StorageError("Failed to download file from storage")
        return resp.content

    async def delete(self, paths: list[str]) -> None:
        if not paths:
            return
        resp = await self._client.request(
            "DELETE", f"{self.base}/object/{self.bucket}", json={"prefixes": paths}
        )
        if resp.status_code >= 400:
            log.warning("storage_delete_failed", status=resp.status_code, body=resp.text[:300])

    async def signed_url(self, path: str) -> str:
        return (await self.signed_urls([path]))[path]

    async def signed_urls(self, paths: list[str]) -> dict[str, str]:
        if not paths:
            return {}
        resp = await self._client.post(
            f"{self.base}/object/sign/{self.bucket}",
            json={"expiresIn": self.ttl_seconds, "paths": paths},
        )
        if resp.status_code >= 400:
            log.error("storage_sign_failed", status=resp.status_code, body=resp.text[:300])
            raise StorageError("Failed to sign storage URLs")
        result: dict[str, str] = {}
        for item in resp.json():
            signed = item.get("signedURL") or item.get("signedUrl")
            if signed and item.get("path"):
                result[item["path"]] = self.base + signed
        return result

    async def ensure_bucket(self) -> None:
        resp = await self._client.post(
            f"{self.base}/bucket", json={"id": self.bucket, "name": self.bucket, "public": False}
        )
        if resp.status_code not in (200, 201, 400, 409):
            log.warning("storage_bucket_create_failed", status=resp.status_code, body=resp.text[:300])


def build_storage(settings: Settings) -> StorageProvider:
    if settings.storage_backend is StorageBackend.SUPABASE:
        if not settings.supabase_url or not settings.supabase_service_role_key.get_secret_value():
            raise RuntimeError("STORAGE_BACKEND=supabase requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        return SupabaseStorageProvider(
            settings.supabase_url,
            settings.supabase_service_role_key.get_secret_value(),
            settings.supabase_storage_bucket,
            settings.signed_url_ttl_seconds,
        )
    return LocalStorageProvider(
        settings.local_storage_dir,
        settings.public_api_url,
        (settings.service_api_key.get_secret_value() + ":files").encode(),
        settings.signed_url_ttl_seconds,
    )


@lru_cache
def get_storage() -> StorageProvider:
    return build_storage(get_settings())
