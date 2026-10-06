"""Private Supabase Storage for user-uploaded media.

The database stores ``supabase://<bucket>/<object-key>`` references. Service
credentials stay on the backend; every object download remains behind the
application's existing teacher/session authorization.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
import tempfile
from urllib.parse import quote, urlsplit

import httpx

from app.core.config import get_settings

URI_PREFIX = "supabase://"


class ObjectStorageError(RuntimeError):
    pass


def _settings():
    return get_settings()


def is_remote_ref(value: str | None) -> bool:
    return bool(value and value.startswith(URI_PREFIX))


def _credentials() -> tuple[str, str, str]:
    settings = _settings()
    base = settings.supabase_url.rstrip("/")
    key = settings.supabase_service_role_key
    bucket = settings.supabase_storage_bucket
    if not base or not key:
        raise ObjectStorageError(
            "线上文件存储未配置。请在后端设置 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY。"
        )
    if not bucket:
        raise ObjectStorageError("SUPABASE_STORAGE_BUCKET 不能为空。")
    return base, key, bucket


def _headers(key: str, *, content_type: str | None = None) -> dict[str, str]:
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def object_uri(bucket: str, key: str) -> str:
    return f"{URI_PREFIX}{bucket}/{key.lstrip('/')}"


def split_object_uri(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    if parsed.scheme != "supabase" or not parsed.netloc or not parsed.path.strip("/"):
        raise ObjectStorageError("Supabase 文件引用格式无效。")
    return parsed.netloc, parsed.path.lstrip("/")


def upload_local_file(path: Path, key: str, *, content_type: str | None = None) -> str:
    """Upload or replace one object in the configured private bucket."""
    base, token, bucket = _credentials()
    key = key.lstrip("/")
    mime = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    endpoint = f"{base}/storage/v1/object/{quote(bucket, safe='')}/{quote(key, safe='/')}"
    try:
        with path.open("rb") as source:
            response = httpx.put(
                endpoint,
                headers={**_headers(token, content_type=mime), "x-upsert": "true"},
                content=source,
                timeout=httpx.Timeout(180.0, connect=15.0),
            )
        response.raise_for_status()
    except (OSError, httpx.HTTPError) as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        raise ObjectStorageError(f"上传文件到 Supabase Storage 失败：{detail[:300] or str(exc)}") from exc
    return object_uri(bucket, key)


def upload_app_file(path: Path, teacher_id: int, category: str) -> str:
    """Use private per-teacher object names for new app uploads."""
    if not path.is_file():
        raise ObjectStorageError(f"待上传文件不存在：{path}")
    settings = _settings()
    if settings.database_url.startswith("sqlite"):
        return str(path)
    _credentials()
    return upload_local_file(path, f"teachers/{teacher_id}/{category}/{path.name}")


def download_object(uri: str) -> bytes:
    base, token, configured_bucket = _credentials()
    bucket, key = split_object_uri(uri)
    if bucket != configured_bucket:
        raise ObjectStorageError("文件所在存储桶与当前后端配置不一致。")
    endpoint = f"{base}/storage/v1/object/{quote(bucket, safe='')}/{quote(key, safe='/')}"
    try:
        response = httpx.get(endpoint, headers=_headers(token), timeout=httpx.Timeout(180.0, connect=15.0))
        response.raise_for_status()
        return response.content
    except httpx.HTTPError as exc:
        detail = getattr(getattr(exc, "response", None), "text", "")
        raise ObjectStorageError(f"从 Supabase Storage 读取文件失败：{detail[:300] or str(exc)}") from exc


def materialize_file(reference: str | Path) -> Path:
    """Return a local path for analysis code, downloading remote refs to a temp cache."""
    value = str(reference)
    if not is_remote_ref(value):
        path = Path(value)
        if not path.is_file():
            raise ObjectStorageError(f"文件不存在：{path}")
        return path
    _, key = split_object_uri(value)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    suffix = Path(key).suffix
    cache_path = Path(tempfile.gettempdir()) / "xiangyin-object-cache" / f"{digest}{suffix}"
    if not cache_path.is_file():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = download_object(value)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        temporary.write_bytes(data)
        os.replace(temporary, cache_path)
    return cache_path
