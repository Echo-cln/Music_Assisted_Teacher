"""EdgeOne Cloud Function adapter for the existing FastAPI application.

EdgeOne maps cloud-functions/api/[[default]].py to /api/* and passes the
matched path to FastAPI without the /api prefix. The existing application
keeps that prefix in its router, so this middleware restores it before routing.
"""
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402


class RestoreApiPrefixMiddleware:
    """Restore the file-routing prefix removed by EdgeOne before FastAPI runs."""

    def __init__(self, inner_app):
        self.inner_app = inner_app

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            path = scope.get("path", "/")
            if not path.startswith("/api/") and path != "/api":
                scope = dict(scope)
                suffix = "" if path == "/" else path
                scope["path"] = f"/api{suffix}"
                raw_path = scope.get("raw_path", path.encode("utf-8"))
                raw_suffix = b"" if raw_path == b"/" else raw_path
                scope["raw_path"] = b"/api" + raw_suffix
        await self.inner_app(scope, receive, send)


app.add_middleware(RestoreApiPrefixMiddleware)
