"""Hermes Radio — FastAPI application entry point."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Ensure core package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db, close_db
from core.routers import playout, status
from core.services import liquidsoap_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("[hermes] Database initialized")

    # Wire up break builder (lazy import to avoid circular deps)
    try:
        from core.services.break_builder import prepare_break
        playout.set_prepare_break_fn(prepare_break)
        print("[hermes] Break builder wired")
    except Exception as e:
        print(f"[hermes] Break builder not available: {e}")

    yield

    # Shutdown
    await liquidsoap_client.close()
    await close_db()
    print("[hermes] Shutdown complete")


app = FastAPI(title="Hermes Radio", version="0.1.0", lifespan=lifespan)

# Static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Routers
app.include_router(playout.router)
app.include_router(status.router)

# Lazy-load optional routers
try:
    from core.routers import admin
    app.include_router(admin.router)
except ImportError:
    pass

try:
    from core.routers import breaking
    app.include_router(breaking.router)
except ImportError:
    pass

try:
    from core.routers import logs
    app.include_router(logs.router)
except ImportError:
    pass
