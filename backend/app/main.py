from contextlib import asynccontextmanager
import logging
from pathlib import Path
from time import perf_counter
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.db.init_db import init_db
from app.services.object_storage import cleanup_materialized_cache

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    removed = cleanup_materialized_cache()
    if removed:
        logging.getLogger("app.privacy").info("removed_expired_audio_cache_files count=%s", removed)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

logger = logging.getLogger("app.request_timing")


def _normalized_origin(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            return None
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return None
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    except ValueError:
        return None


@app.middleware("http")
async def log_api_request_timing(request, call_next):
    is_api = request.url.path.startswith("/api/")
    origin = request.headers.get("origin")
    if is_api and request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip()
        scheme = forwarded_proto if forwarded_proto in {"http", "https"} else request.url.scheme
        same_origin = _normalized_origin(f"{scheme}://{request.headers.get('host', request.url.netloc)}")
        allowed_origins = {_normalized_origin(value) for value in settings.cors_origins}
        candidate = _normalized_origin(origin)
        if not candidate or (candidate not in allowed_origins and candidate != same_origin):
            return JSONResponse(status_code=403, content={"detail": "跨站写请求已拒绝，请从本应用页面重新操作"}, headers={"Cache-Control": "private, no-store"})

    if is_api and request.url.path in {"/api/audio/analyze", "/api/audio/jobs"}:
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            content_length = 0
        request_limit = max(1, int(settings.audio_max_upload_bytes)) * 2 + 2 * 1024 * 1024
        if content_length > request_limit:
            return JSONResponse(status_code=413, content={"detail": "录音与参考音频的总上传大小超出限制"}, headers={"Cache-Control": "private, no-store"})

    started = perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (perf_counter() - started) * 1000
        logger.exception(
            "api_request_failed method=%s path=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise

    elapsed_ms = (perf_counter() - started) * 1000
    if is_api:
        logger.info(
            "api_request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Pragma"] = "no-cache"
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)

frontend_dir = Path(settings.frontend_dir)
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
