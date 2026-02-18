"""Status router — health check, scheduler info, HTMX partials."""

import time
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.config import HERMES_API_KEY, BASE_PATH
from core.routers.admin import require_api_key
from core.database import get_db
from core.services.scheduler import scheduler

router = APIRouter(tags=["status"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
templates.env.globals["base"] = BASE_PATH

_start_time = time.time()


@router.get("/api/health")
async def health():
    """Public health endpoint."""
    db = await get_db()
    uptime = int(time.time() - _start_time)

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

    # Scheduler info
    sched_status = scheduler.status()

    # Break interval
    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'break_interval_minutes'"
    )
    interval_row = await cursor.fetchone()
    interval = int(interval_row["value"]) if interval_row else 15

    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "components": {
            "scheduler": sched_status,
            "news": {
                "feeds_healthy": feed_stats.get("healthy", 0),
                "feeds_unhealthy": feed_stats.get("unhealthy", 0),
                "feeds_dead": feed_stats.get("dead", 0),
            },
        },
        "schedule": {
            "interval_minutes": interval,
            "last_trigger": sched_status.get("last_trigger"),
        },
        "last_break": last_break,
        "stats_today": {
            "breaks_played": (stats_row["played"] or 0) if stats_row else 0,
            "breaks_failed": (stats_row["failed"] or 0) if stats_row else 0,
        },
    }


@router.get("/api/status/current")
async def current_status():
    """Current scheduler status for admin."""
    db = await get_db()

    cursor = await db.execute(
        "SELECT value FROM settings WHERE key = 'quiet_mode'"
    )
    row = await cursor.fetchone()
    quiet = row["value"] == "true" if row else False

    cursor = await db.execute(
        "SELECT id, status FROM break_queue WHERE status IN ('PREPARING', 'READY') ORDER BY created_at DESC LIMIT 1"
    )
    bq = await cursor.fetchone()

    sched = scheduler.status()

    return {
        "scheduler_running": sched["running"],
        "last_trigger": sched.get("last_trigger"),
        "break_preparing": bq["status"] == "PREPARING" if bq else False,
        "break_ready": bq["id"] if bq and bq["status"] == "READY" else None,
        "quiet_mode": quiet,
    }


# --- HTMX Partials for Dashboard ---

@router.get("/api/partials/dashboard-stats", response_class=HTMLResponse)
async def partial_dashboard_stats(request: Request, _=Depends(require_api_key)):
    db = await get_db()

    cursor = await db.execute(
        """SELECT
            SUM(CASE WHEN status='PLAYED' THEN 1 ELSE 0 END) as played,
            SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) as failed
           FROM break_queue WHERE created_at > date('now')"""
    )
    stats = await cursor.fetchone()

    cursor = await db.execute("SELECT key, value FROM settings WHERE key = 'quiet_mode'")
    qm = await cursor.fetchone()

    sched = scheduler.status()

    return templates.TemplateResponse("partials/dashboard_stats.html", {
        "request": request,
        "scheduler_running": sched["running"],
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
