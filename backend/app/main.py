from contextlib import asynccontextmanager
import logging
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.db.init_db import init_db

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

logger = logging.getLogger("app.request_timing")


@app.middleware("http")
async def log_api_request_timing(request, call_next):
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
    if request.url.path.startswith("/api/"):
        logger.info(
            "api_request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
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
