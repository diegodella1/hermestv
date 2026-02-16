"""Logs router — event log viewer."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from core.database import get_db
from core.routers.admin import require_api_key, _template_ctx

router = APIRouter(tags=["logs"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))


@router.get("/admin/logs", response_class=HTMLResponse)
async def logs_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    event_type = request.query_params.get("type", "")
    limit = min(int(request.query_params.get("limit", "50")), 200)
    offset = int(request.query_params.get("offset", "0"))

    if event_type:
        cursor = await db.execute(
            """SELECT * FROM events_log WHERE event_type LIKE ?
               ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
            (f"%{event_type}%", limit, offset),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM events_log ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    logs = [dict(r) for r in await cursor.fetchall()]

    if event_type:
        cursor = await db.execute(
            "SELECT COUNT(*) as total FROM events_log WHERE event_type LIKE ?",
            (f"%{event_type}%",),
        )
    else:
        cursor = await db.execute("SELECT COUNT(*) as total FROM events_log")
    total_row = await cursor.fetchone()
    total = total_row["total"] if total_row else 0

    return templates.TemplateResponse("logs.html", _template_ctx(
        request, "logs",
        logs=logs,
        total=total,
        limit=limit,
        offset=offset,
        event_type=event_type,
    ))


@router.get("/api/admin/logs")
async def api_logs(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    event_type = request.query_params.get("type", "")
    limit = min(int(request.query_params.get("limit", "50")), 200)
    offset = int(request.query_params.get("offset", "0"))

    if event_type:
        cursor = await db.execute(
            """SELECT * FROM events_log WHERE event_type LIKE ?
               ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
            (f"%{event_type}%", limit, offset),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM events_log ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
    logs = [dict(r) for r in await cursor.fetchall()]

    return {"logs": logs, "total": len(logs), "offset": offset, "limit": limit}
