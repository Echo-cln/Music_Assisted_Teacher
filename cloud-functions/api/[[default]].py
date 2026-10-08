"""EdgeOne Cloud Function entry for the existing FastAPI application.

EdgeOne discovers Python route modules by finding an explicit framework
instance assignment (for example, app = FastAPI(...)). The backend application
is mounted here so its router, middleware, and configuration stay the single
source of truth.
"""
from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app as backend_app  # noqa: E402


@asynccontextmanager
async def lifespan(_app):
    # Mounted ASGI apps do not own the outer application lifespan. Forward it
    # explicitly so database initialization and startup cleanup still run.
    async with backend_app.router.lifespan_context(backend_app):
        yield


# Keep an explicit FastAPI instance in this file: EdgeOne uses it to recognize
# and register the catch-all /api/* function route.
app = FastAPI(lifespan=lifespan)
app.mount("/", backend_app)
