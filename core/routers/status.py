"""Status router — health check, now-playing info, playout control, HTMX partials."""

import asyncio
import os
import time
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import HLS_DIR, HERMES_API_KEY
from core.routers.admin import require_api_key
from core.database import get_db
from core.services import liquidsoap_client

router = APIRouter(tags=["status"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

_start_time = time.time()


@router.get("/api/health")
async def health():
    """Public health endpoint."""
    db = await get_db()
    uptime = int(time.time() - _start_time)

    # Liquidsoap status
    liq_ok = await liquidsoap_client.heartbeat()
    track_count = await liquidsoap_client.get_track_count() if liq_ok else None

    # HLS freshness
    hls_path = os.path.join(str(HLS_DIR), "radio.m3u8")
    hls_age = None
    if os.path.exists(hls_path):
        hls_age = int(time.time() - os.path.getmtime(hls_path))

    # Feed health
    cursor = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM feed_health GROUP BY status"
    )
    feed_stats = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

    # Last break
    cursor = await db.execute(
        """SELECT id, type, host_id, played_at, degradation_level
           FROM break_queue WHERE status = 'PLAYED'
           ORDER BY played_at DESC LIMIT 1"""
    )
    last_break = None
    row = await cursor.fetchone()
    if row:
        last_break = {
            "id": row["id"],
            "type": row["type"],
            "host": row["host_id"],
            "played_at": row["played_at"],
            "degradation_level": row["degradation_level"],
        }

    # Stats today
    cursor = await db.execute(
        """SELECT
            SUM(CASE WHEN status = 'PLAYED' THEN 1 ELSE 0 END) as played,
            SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed
           FROM break_queue
           WHERE created_at > date('now')"""
    )
    stats_row = await cursor.fetchone()

    # Settings for next break estimate
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'every_n_tracks'"
    )
    every_n_row = await cursor.fetchone()
    every_n = int(every_n_row["value"]) if every_n_row else 4

    tracks_left = (every_n - (track_count or 0) % every_n) if track_count else None

    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "components": {
            "liquidsoap": {
                "status": "ok" if liq_ok else "down",
                "socket_connected": liq_ok,
                "track_count": track_count,
            },
            "ffmpeg": {
                "status": "ok" if hls_age is not None and hls_age < 30 else "warning",
                "hls_last_modified_seconds_ago": hls_age,
            },
            "news": {
                "feeds_healthy": feed_stats.get("healthy", 0),
                "feeds_unhealthy": feed_stats.get("unhealthy", 0),
                "feeds_dead": feed_stats.get("dead", 0),
            },
        },
        "now_playing": {
            "tracks_since_last_break": track_count,
            "next_break_estimated": f"~{tracks_left} track(s)" if tracks_left else "unknown",
        },
        "last_break": last_break,
        "stats_today": {
            "breaks_played": (stats_row["played"] or 0) if stats_row else 0,
            "breaks_failed": (stats_row["failed"] or 0) if stats_row else 0,
        },
    }


async def _supervisorctl(action: str) -> tuple[bool, str]:
    """Run supervisorctl command and return (success, output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "supervisorctl", action, "playout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode().strip()
        return proc.returncode == 0, output
    except Exception as e:
        return False, str(e)


@router.get("/api/playout/status")
async def playout_status():
    """Check if playout is running."""
    ok, output = await _supervisorctl("status")
    running = "RUNNING" in output
    return {"running": running, "detail": output}


@router.post("/api/playout/start")
async def playout_start(_=Depends(require_api_key)):
    """Start the playout pipeline."""
    ok, output = await _supervisorctl("start")
    return {"ok": ok or "ALREADY" in output.upper(), "detail": output}


@router.post("/api/playout/stop")
async def playout_stop(_=Depends(require_api_key)):
    """Stop the playout pipeline."""
    ok, output = await _supervisorctl("stop")
    return {"ok": ok or "NOT RUNNING" in output.upper(), "detail": output}


@router.get("/api/status/now-playing")
async def now_playing():
    """Now playing info for admin."""
    db = await get_db()
    track_count = await liquidsoap_client.get_track_count()

    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'quiet_mode'"
    )
    row = await cursor.fetchone()
    quiet = row["value"] == "true" if row else False

    cursor = await db.execute(
        "SELECT id, status FROM break_queue WHERE status IN ('PREPARING', 'READY') ORDER BY created_at DESC LIMIT 1"
    )
    bq = await cursor.fetchone()

    return {
        "tracks_since_last_break": track_count,
        "break_preparing": bq["status"] == "PREPARING" if bq else False,
        "break_ready": bq["id"] if bq and bq["status"] == "READY" else None,
        "quiet_mode": quiet,
    }


# --- HTMX Partials for Dashboard ---

@router.get("/api/partials/dashboard-stats", response_class=HTMLResponse)
async def partial_dashboard_stats(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    track_count = await liquidsoap_client.get_track_count()

    cursor = await db.execute(
        """SELECT
            SUM(CASE WHEN status='PLAYED' THEN 1 ELSE 0 END) as played,
            SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) as failed
           FROM break_queue WHERE created_at > date('now')"""
    )
    stats = await cursor.fetchone()

    cursor = await db.execute("SELECT key, value FROM settings WHERE key = 'quiet_mode'")
    qm = await cursor.fetchone()

    return templates.TemplateResponse("partials/dashboard_stats.html", {
        "request": request,
        "track_count": track_count,
        "breaks_played": (stats["played"] or 0) if stats else 0,
        "breaks_failed": (stats["failed"] or 0) if stats else 0,
        "quiet_mode": qm["value"] == "true" if qm else False,
    })


@router.get("/api/partials/feed-health", response_class=HTMLResponse)
async def partial_feed_health(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM feed_health GROUP BY status"
    )
    feed_health = {r["status"]: r["cnt"] for r in await cursor.fetchall()}
    return templates.TemplateResponse("partials/health_badges.html", {
        "request": request,
        "feed_health": feed_health,
    })


@router.get("/api/partials/last-break", response_class=HTMLResponse)
async def partial_last_break(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM break_queue WHERE status='PLAYED' ORDER BY played_at DESC LIMIT 1"
    )
    last_break = await cursor.fetchone()

    cursor = await db.execute("SELECT id, label FROM hosts")
    host_names = {r["id"]: r["label"] for r in await cursor.fetchall()}

    return templates.TemplateResponse("partials/last_break.html", {
        "request": request,
        "last_break": dict(last_break) if last_break else None,
        "host_names": host_names,
    })
