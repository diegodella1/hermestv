"""Hermes Radio — FastAPI application entry point."""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

# Ensure core package is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import HLS_DIR, HLS_VIDEO_DIR, BREAKS_DIR, BASE_PATH
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

    # Ensure HLS video dir exists + clean old dirs (>24h)
    try:
        os.makedirs(str(HLS_VIDEO_DIR), exist_ok=True)
        import shutil
        from time import time as _time
        cutoff = _time() - 86400
        for d in HLS_VIDEO_DIR.iterdir():
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        print(f"[hermes] HLS video cleanup error: {e}")

    yield

    # Shutdown
    await liquidsoap_client.close()
    await close_db()
    print("[hermes] Shutdown complete")


app = FastAPI(
    title="Hermes Radio", version="0.1.0", lifespan=lifespan,
)

# Strip BASE_PATH prefix from incoming requests (Tailscale Funnel does NOT strip it)
# Templates still generate URLs with {{ base }} prefix for the browser.
if BASE_PATH:
    from starlette.types import ASGIApp, Receive, Scope, Send

    class StripBasePath:
        """ASGI middleware that strips BASE_PATH prefix from request path."""
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] in ("http", "websocket"):
                path: str = scope["path"]
                if path.startswith(BASE_PATH):
                    scope["path"] = path[len(BASE_PATH):] or "/"
            await self.app(scope, receive, send)

    app.add_middleware(StripBasePath)

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

# HLS stream files — custom route with proper cache headers for live streaming.
# .m3u8 MUST NOT be cached (playlist changes every segment), .ts CAN be cached.
hls_dir = Path(str(HLS_DIR))
os.makedirs(str(hls_dir), exist_ok=True)


@app.get("/hls/{filename}")
async def serve_hls(filename: str):
    # Prevent path traversal
    if ".." in filename or "/" in filename:
        return Response(status_code=400)
    filepath = hls_dir / filename
    if not filepath.exists() or not filepath.is_file():
        return Response(status_code=404)
    if filename.endswith(".m3u8"):
        return FileResponse(
            filepath,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    elif filename.endswith(".ts"):
        return FileResponse(
            filepath,
            media_type="video/MP2T",
            headers={"Cache-Control": "public, max-age=300"},
        )
    return Response(status_code=404)


# MP4 video files from breaks dir
breaks_dir = Path(str(BREAKS_DIR))
os.makedirs(str(breaks_dir), exist_ok=True)


@app.get("/video/{filename}")
async def serve_video(filename: str):
    if ".." in filename or "/" in filename:
        return Response(status_code=400)
    filepath = breaks_dir / filename
    if not filepath.exists() or not filepath.is_file():
        return Response(status_code=404)
    return FileResponse(
        filepath, media_type="video/mp4",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# HLS video segments per break
hls_video_dir = Path(str(HLS_VIDEO_DIR))
os.makedirs(str(hls_video_dir), exist_ok=True)


@app.get("/hls-video/{break_id}/{filename}")
async def serve_hls_video(break_id: str, filename: str):
    if ".." in break_id or "/" in break_id or ".." in filename or "/" in filename:
        return Response(status_code=400)
    filepath = hls_video_dir / break_id / filename
    if not filepath.exists() or not filepath.is_file():
        return Response(status_code=404)
    if filename.endswith(".m3u8"):
        return FileResponse(
            filepath,
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )
    elif filename.endswith(".ts"):
        return FileResponse(
            filepath,
            media_type="video/MP2T",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    return Response(status_code=404)


# Templates
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["base"] = BASE_PATH

# Routers
app.include_router(playout.router)
app.include_router(status.router)

# Lazy-load optional routers
@app.get("/", response_class=HTMLResponse)
async def player_page(request: Request):
    return templates.TemplateResponse("player.html", {"request": request})


@app.get("/tv", response_class=HTMLResponse)
async def tv_page(request: Request):
    return templates.TemplateResponse("tv.html", {"request": request})


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
