"""Admin router — CRUD for cities, sources, hosts, settings + auth."""

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import HERMES_API_KEY
from core.database import get_db

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

# Session tokens (in-memory, simple)
_sessions: set[str] = set()


async def require_api_key(request: Request):
    """Check API key from header or session cookie. Redirects browsers to login."""
    # Check header
    api_key = request.headers.get("X-API-Key")
    if api_key == HERMES_API_KEY:
        return True

    # Check session cookie
    session = request.cookies.get("hermes_session")
    if session in _sessions:
        return True

    # Browser requests: redirect to login instead of JSON 401
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        raise HTTPException(
            status_code=307,
            headers={"Location": "/admin/login"},
        )

    raise HTTPException(status_code=401, detail="Unauthorized")


# --- Auth ---
@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/admin/login")
async def login(request: Request):
    form = await request.form()
    password = form.get("password", "")
    if password == HERMES_API_KEY:
        session_id = uuid.uuid4().hex
        _sessions.add(session_id)
        response = RedirectResponse("/admin/", status_code=303)
        response.set_cookie("hermes_session", session_id, httponly=True, max_age=86400)
        return response
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid password"}
    )


@router.get("/admin/logout")
async def logout(request: Request):
    session = request.cookies.get("hermes_session")
    if session in _sessions:
        _sessions.discard(session)
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie("hermes_session")
    return response


# --- Dashboard ---
@router.get("/admin/", response_class=HTMLResponse)
async def dashboard(request: Request, _=Depends(require_api_key)):
    db = await get_db()

    # Now playing
    from core.services import liquidsoap_client
    track_count = await liquidsoap_client.get_track_count()

    # Stats today
    cursor = await db.execute(
        """SELECT
            SUM(CASE WHEN status='PLAYED' THEN 1 ELSE 0 END) as played,
            SUM(CASE WHEN status='FAILED' THEN 1 ELSE 0 END) as failed
           FROM break_queue WHERE created_at > date('now')"""
    )
    stats = await cursor.fetchone()

    # Feed health
    cursor = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM feed_health GROUP BY status"
    )
    feed_health = {r["status"]: r["cnt"] for r in await cursor.fetchall()}

    # Last break
    cursor = await db.execute(
        "SELECT * FROM break_queue WHERE status='PLAYED' ORDER BY played_at DESC LIMIT 1"
    )
    last_break = await cursor.fetchone()

    # Settings
    cursor = await db.execute("SELECT key, value FROM settings WHERE key = 'quiet_mode'")
    qm = await cursor.fetchone()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "track_count": track_count,
        "breaks_played": (stats["played"] or 0) if stats else 0,
        "breaks_failed": (stats["failed"] or 0) if stats else 0,
        "feed_health": feed_health,
        "last_break": dict(last_break) if last_break else None,
        "quiet_mode": qm["value"] == "true" if qm else False,
    })


# --- Settings ---
@router.get("/admin/rules", response_class=HTMLResponse)
async def rules_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT key, value FROM settings")
    settings = {r["key"]: r["value"] for r in await cursor.fetchall()}
    return templates.TemplateResponse("rules.html", {"request": request, "settings": settings})


@router.post("/admin/rules")
async def update_rules(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    for key in ["every_n_tracks", "prepare_at_track", "cooldown_seconds",
                "break_timeout_seconds", "quiet_mode", "quiet_hours_start",
                "quiet_hours_end", "breaking_score_threshold", "news_dedupe_window_minutes"]:
        val = form.get(key)
        if val is not None:
            if key == "quiet_mode":
                val = "true" if val == "on" else "false"
            await db.execute(
                "UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (val, key),
            )
    await db.commit()
    return RedirectResponse("/admin/rules", status_code=303)


# --- API Settings ---
@router.get("/api/admin/settings")
async def get_settings(_=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT key, value FROM settings")
    return {r["key"]: r["value"] for r in await cursor.fetchall()}


@router.put("/api/admin/settings")
async def update_settings(body: dict, _=Depends(require_api_key)):
    db = await get_db()
    for key, val in body.items():
        await db.execute(
            "UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
            (str(val), key),
        )
    await db.commit()
    return {"status": "ok"}


# --- Cities ---
@router.get("/admin/cities", response_class=HTMLResponse)
async def cities_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM cities ORDER BY priority")
    cities = [dict(r) for r in await cursor.fetchall()]
    return templates.TemplateResponse("cities.html", {"request": request, "cities": cities})


@router.post("/admin/cities")
async def create_city(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    city_id = form.get("id") or form.get("label", "city").lower().replace(" ", "_")
    await db.execute(
        """INSERT OR REPLACE INTO cities (id, label, lat, lon, tz, enabled, priority, units)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            city_id,
            form.get("label", ""),
            float(form.get("lat", 0)),
            float(form.get("lon", 0)),
            form.get("tz", "UTC"),
            1 if form.get("enabled") == "on" else 0,
            int(form.get("priority", 0)),
            form.get("units", "metric"),
        ),
    )
    await db.commit()
    return RedirectResponse("/admin/cities", status_code=303)


@router.post("/admin/cities/{city_id}/delete")
async def delete_city(city_id: str, _=Depends(require_api_key)):
    db = await get_db()
    await db.execute("DELETE FROM cities WHERE id = ?", (city_id,))
    await db.commit()
    return RedirectResponse("/admin/cities", status_code=303)


# --- API Cities ---
@router.get("/api/admin/cities")
async def api_list_cities(_=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM cities ORDER BY priority")
    return [dict(r) for r in await cursor.fetchall()]


@router.post("/api/admin/cities")
async def api_create_city(body: dict, _=Depends(require_api_key)):
    db = await get_db()
    city_id = body.get("id") or body.get("label", "city").lower().replace(" ", "_")
    await db.execute(
        """INSERT OR REPLACE INTO cities (id, label, lat, lon, tz, enabled, priority, units)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            city_id, body.get("label"), body.get("lat"), body.get("lon"),
            body.get("tz", "UTC"), body.get("enabled", True),
            body.get("priority", 0), body.get("units", "metric"),
        ),
    )
    await db.commit()
    return {"status": "ok", "id": city_id}


@router.delete("/api/admin/cities/{city_id}")
async def api_delete_city(city_id: str, _=Depends(require_api_key)):
    db = await get_db()
    await db.execute("DELETE FROM cities WHERE id = ?", (city_id,))
    await db.commit()
    return {"status": "ok"}


# --- Sources ---
@router.get("/admin/sources", response_class=HTMLResponse)
async def sources_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        """SELECT ns.*, fh.status as health_status, fh.consecutive_failures, fh.last_success
           FROM news_sources ns
           LEFT JOIN feed_health fh ON fh.source_id = ns.id
           ORDER BY ns.label"""
    )
    sources = [dict(r) for r in await cursor.fetchall()]
    return templates.TemplateResponse("sources.html", {"request": request, "sources": sources})


@router.post("/admin/sources")
async def create_source(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    src_id = form.get("id") or form.get("label", "src").lower().replace(" ", "_")
    await db.execute(
        """INSERT OR REPLACE INTO news_sources (id, type, label, url, enabled, weight, category, poll_interval_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            src_id, form.get("type", "rss"), form.get("label", ""),
            form.get("url", ""), 1 if form.get("enabled") == "on" else 0,
            float(form.get("weight", 1.0)), form.get("category", "general"),
            int(form.get("poll_interval_seconds", 300)),
        ),
    )
    await db.execute("INSERT OR IGNORE INTO feed_health (source_id) VALUES (?)", (src_id,))
    await db.commit()
    return RedirectResponse("/admin/sources", status_code=303)


@router.post("/admin/sources/{src_id}/delete")
async def delete_source(src_id: str, _=Depends(require_api_key)):
    db = await get_db()
    await db.execute("DELETE FROM news_sources WHERE id = ?", (src_id,))
    await db.commit()
    return RedirectResponse("/admin/sources", status_code=303)


# --- Hosts ---
@router.get("/admin/hosts", response_class=HTMLResponse)
async def hosts_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM hosts ORDER BY id")
    hosts = [dict(r) for r in await cursor.fetchall()]
    return templates.TemplateResponse("hosts.html", {"request": request, "hosts": hosts})


@router.post("/admin/hosts/{host_id}")
async def update_host(host_id: str, request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    await db.execute(
        """UPDATE hosts SET label = ?, personality_prompt = ?,
           is_breaking_host = ?, enabled = ?
           WHERE id = ?""",
        (
            form.get("label", ""),
            form.get("personality_prompt", ""),
            1 if form.get("is_breaking_host") == "on" else 0,
            1 if form.get("enabled") == "on" else 0,
            host_id,
        ),
    )
    await db.commit()
    return RedirectResponse("/admin/hosts", status_code=303)


# --- Prompts ---
@router.get("/admin/prompts", response_class=HTMLResponse)
async def prompts_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT value FROM settings WHERE key = 'master_prompt'")
    row = await cursor.fetchone()
    return templates.TemplateResponse("prompts.html", {
        "request": request,
        "master_prompt": row["value"] if row else "",
    })


@router.post("/admin/prompts")
async def update_prompts(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    await db.execute(
        "UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = 'master_prompt'",
        (form.get("master_prompt", ""),),
    )
    await db.commit()
    return RedirectResponse("/admin/prompts", status_code=303)


# --- Breaking page ---
@router.get("/admin/breaking", response_class=HTMLResponse)
async def breaking_page(request: Request, _=Depends(require_api_key)):
    return templates.TemplateResponse("breaking.html", {"request": request})
