"""Hermes Radio — FastAPI application entry point."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Ensure core package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import HLS_DIR
from core.database import init_db, close_db
from core.routers import playout, status
from core.services import liquidsoap_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("[hermes] Database initialized")

    # Clean stale PREPARING breaks left by previous crash/restart
    try:
        from core.database import get_db
        db = await get_db()
        res = await db.execute(
            "UPDATE break_queue SET status='FAILED', meta_json=json_object('error','stale_preparing_on_startup') WHERE status='PREPARING'"
        )
        await db.commit()
        if res.rowcount:
            print(f"[hermes] Cleaned {res.rowcount} stale PREPARING break(s)")
    except Exception as e:
        print(f"[hermes] Stale break cleanup error: {e}")

    # Prune old data to keep SQLite lean
    try:
        from core.database import get_db
        db = await get_db()
        c1 = await db.execute("DELETE FROM events_log WHERE created_at < datetime('now', '-7 days')")
        c2 = await db.execute("DELETE FROM cache_news WHERE fetched_at < datetime('now', '-24 hours')")
        c3 = await db.execute("DELETE FROM break_queue WHERE status = 'FAILED' AND created_at < datetime('now', '-7 days')")
        await db.commit()
        pruned = c1.rowcount + c2.rowcount + c3.rowcount
        if pruned:
            print(f"[hermes] Pruned {pruned} old rows (events={c1.rowcount}, news_cache={c2.rowcount}, failed_breaks={c3.rowcount})")
    except Exception as e:
        print(f"[hermes] DB pruning error: {e}")

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

# CORS — needed for HLS players in browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Range"],
    expose_headers=["Content-Length", "Content-Range"],
)

# Static files (CSS/JS)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# HLS stream files — served directly by FastAPI (no Caddy needed in Docker)
hls_dir = Path(str(HLS_DIR))
os.makedirs(str(hls_dir), exist_ok=True)
app.mount("/hls", StaticFiles(directory=str(hls_dir)), name="hls")

# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Routers
app.include_router(playout.router)
app.include_router(status.router)

# Lazy-load optional routers
@app.get("/", response_class=HTMLResponse)
async def player_page(request: Request):
    return templates.TemplateResponse("player.html", {"request": request})


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
