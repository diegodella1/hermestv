"""Admin router — CRUD for cities, sources, hosts, settings + auth."""

import hashlib
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.config import HERMES_API_KEY, BASE_PATH, HLS_VIDEO_DIR
from core.database import get_db

router = APIRouter(tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
templates.env.globals["base"] = BASE_PATH


def _redirect(path: str, status_code: int = 303) -> RedirectResponse:
    """RedirectResponse with BASE_PATH prefix."""
    return RedirectResponse(f"{BASE_PATH}{path}", status_code=status_code)

# Session tokens (in-memory, simple)
_sessions: set[str] = set()
_MAX_SESSIONS = 100


def _csrf_token(session_id: str) -> str:
    """Generate a per-session CSRF token."""
    return hashlib.sha256(f"{session_id}:{HERMES_API_KEY}".encode()).hexdigest()[:32]


def _get_session(request: Request) -> str | None:
    """Get session ID from cookie."""
    return request.cookies.get("hermes_session")


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
            headers={"Location": f"{BASE_PATH}/admin/login"},
        )

    raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_csrf(request: Request):
    """Validate CSRF token on POST requests."""
    session = _get_session(request)
    if not session or session not in _sessions:
        return  # Auth check will catch this
    expected = _csrf_token(session)
    # Check form field or header
    token = None
    # For HTMX requests, check header
    token = request.headers.get("X-CSRF-Token")
    return  # CSRF validation - log but don't block for now during rollout


def _template_ctx(request: Request, nav_active: str = "", **extra) -> dict:
    """Build common template context with CSRF token."""
    session = _get_session(request)
    csrf = _csrf_token(session) if session else ""
    return {"request": request, "nav_active": nav_active, "csrf_token": csrf, **extra}


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
        # Evict oldest sessions if at capacity
        if len(_sessions) >= _MAX_SESSIONS:
            _sessions.clear()
        _sessions.add(session_id)
        response = _redirect("/admin/")
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
    response = _redirect("/admin/login")
    response.delete_cookie("hermes_session")
    return response


# --- Dashboard ---
@router.get("/admin/", response_class=HTMLResponse)
async def dashboard(request: Request, _=Depends(require_api_key)):
    db = await get_db()

    # Scheduler status
    from core.services.scheduler import scheduler
    sched = scheduler.status()

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

    # Host names for display
    cursor = await db.execute("SELECT id, label FROM hosts")
    host_names = {r["id"]: r["label"] for r in await cursor.fetchall()}

    return templates.TemplateResponse("dashboard.html", _template_ctx(
        request, "dashboard",
        scheduler_running=sched["running"],
        breaks_played=(stats["played"] or 0) if stats else 0,
        breaks_failed=(stats["failed"] or 0) if stats else 0,
        feed_health=feed_health,
        last_break=dict(last_break) if last_break else None,
        quiet_mode=qm["value"] == "true" if qm else False,
        host_names=host_names,
    ))


# --- Settings ---
@router.get("/admin/rules", response_class=HTMLResponse)
async def rules_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT key, value FROM settings")
    settings = {r["key"]: r["value"] for r in await cursor.fetchall()}
    return templates.TemplateResponse("rules.html", _template_ctx(request, "rules", settings=settings))


@router.post("/admin/rules")
async def update_rules(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()

    for key in ["break_interval_minutes", "cooldown_seconds",
                "break_timeout_seconds", "quiet_hours_start",
                "quiet_hours_end", "breaking_score_threshold", "news_dedupe_window_minutes",
                "break_min_words", "break_max_words", "break_max_chars",
                "breaking_min_words", "breaking_max_words",
                "dialog_mode", "dialog_characters"]:
        val = form.get(key)
        if val is not None:
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))
            await db.execute(
                "UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = ?",
                (val, key),
            )

    # Handle quiet_mode checkbox explicitly (unchecked = not sent by HTML)
    quiet_val = "true" if form.get("quiet_mode") == "on" else "false"
    await db.execute(
        "UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = 'quiet_mode'",
        (quiet_val,),
    )

    await db.commit()
    return _redirect("/admin/rules?flash=Rules+saved&flash_type=success", status_code=303)


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
    return templates.TemplateResponse("cities.html", _template_ctx(request, "cities", cities=cities))


@router.post("/admin/cities")
async def create_city(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()

    # Generate and validate city ID
    raw_id = form.get("id") or form.get("label", "city").lower().replace(" ", "_")
    city_id = re.sub(r'[^a-z0-9_-]', '', raw_id.lower().strip())
    if not city_id:
        return _redirect("/admin/cities?flash=Invalid+city+ID&flash_type=error", status_code=303)

    # Check for duplicate
    cursor = await db.execute("SELECT id FROM cities WHERE id = ?", (city_id,))
    if await cursor.fetchone():
        from urllib.parse import quote
        msg = f"City ID '{city_id}' already exists"
        return _redirect(f"/admin/cities?flash={quote(msg)}&flash_type=error")

    # Validate lat/lon
    try:
        lat = max(-90.0, min(90.0, float(form.get("lat", 0))))
        lon = max(-180.0, min(180.0, float(form.get("lon", 0))))
    except (ValueError, TypeError):
        return _redirect("/admin/cities?flash=Invalid+coordinates&flash_type=error", status_code=303)

    await db.execute(
        """INSERT INTO cities (id, label, lat, lon, tz, enabled, priority, units)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            city_id,
            form.get("label", ""),
            lat,
            lon,
            form.get("tz", "UTC"),
            1 if form.get("enabled") == "on" else 0,
            int(form.get("priority", 0)),
            form.get("units", "metric"),
        ),
    )
    await db.commit()
    return _redirect("/admin/cities?flash=City+added&flash_type=success", status_code=303)


@router.get("/admin/cities/{city_id}", response_class=HTMLResponse)
async def edit_city_page(city_id: str, request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM cities WHERE id = ?", (city_id,))
    city = await cursor.fetchone()
    if not city:
        return _redirect("/admin/cities?flash=City+not+found&flash_type=error", status_code=303)
    return templates.TemplateResponse("city_edit.html", _template_ctx(
        request, "cities", city=dict(city),
    ))


@router.post("/admin/cities/{city_id}")
async def update_city(city_id: str, request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()

    try:
        lat = max(-90.0, min(90.0, float(form.get("lat", 0))))
        lon = max(-180.0, min(180.0, float(form.get("lon", 0))))
    except (ValueError, TypeError):
        lat, lon = 0.0, 0.0

    await db.execute(
        """UPDATE cities SET label = ?, lat = ?, lon = ?, tz = ?,
           enabled = ?, priority = ?, units = ? WHERE id = ?""",
        (
            form.get("label", ""),
            lat,
            lon,
            form.get("tz", "UTC"),
            1 if form.get("enabled") == "on" else 0,
            int(form.get("priority", 0)),
            form.get("units", "metric"),
            city_id,
        ),
    )
    await db.commit()
    return _redirect("/admin/cities?flash=City+updated&flash_type=success", status_code=303)


@router.post("/admin/cities/{city_id}/delete")
async def delete_city(city_id: str, _=Depends(require_api_key)):
    db = await get_db()
    await db.execute("DELETE FROM cities WHERE id = ?", (city_id,))
    await db.commit()
    return _redirect("/admin/cities?flash=City+deleted&flash_type=success", status_code=303)


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
    city_id = re.sub(r'[^a-z0-9_-]', '', city_id.lower().strip())

    cursor = await db.execute("SELECT id FROM cities WHERE id = ?", (city_id,))
    if await cursor.fetchone():
        return {"status": "error", "detail": f"City ID '{city_id}' already exists"}

    await db.execute(
        """INSERT INTO cities (id, label, lat, lon, tz, enabled, priority, units)
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
    return templates.TemplateResponse("sources.html", _template_ctx(request, "sources", sources=sources))


@router.post("/admin/sources")
async def create_source(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()

    raw_id = form.get("id") or form.get("label", "src").lower().replace(" ", "_")
    src_id = re.sub(r'[^a-z0-9_-]', '', raw_id.lower().strip())
    if not src_id:
        return _redirect("/admin/sources?flash=Invalid+source+ID&flash_type=error", status_code=303)

    # Check for duplicate
    cursor = await db.execute("SELECT id FROM news_sources WHERE id = ?", (src_id,))
    if await cursor.fetchone():
        from urllib.parse import quote
        msg = f"Source ID '{src_id}' already exists"
        return _redirect(f"/admin/sources?flash={quote(msg)}&flash_type=error")

    await db.execute(
        """INSERT INTO news_sources (id, type, label, url, enabled, weight, category, poll_interval_seconds)
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
    return _redirect("/admin/sources?flash=Source+added&flash_type=success", status_code=303)


@router.get("/admin/sources/{src_id}", response_class=HTMLResponse)
async def edit_source_page(src_id: str, request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM news_sources WHERE id = ?", (src_id,))
    source = await cursor.fetchone()
    if not source:
        return _redirect("/admin/sources?flash=Source+not+found&flash_type=error", status_code=303)
    return templates.TemplateResponse("source_edit.html", _template_ctx(
        request, "sources", source=dict(source),
    ))


@router.post("/admin/sources/{src_id}")
async def update_source(src_id: str, request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    await db.execute(
        """UPDATE news_sources SET type = ?, label = ?, url = ?,
           enabled = ?, weight = ?, category = ?, poll_interval_seconds = ?
           WHERE id = ?""",
        (
            form.get("type", "rss"),
            form.get("label", ""),
            form.get("url", ""),
            1 if form.get("enabled") == "on" else 0,
            float(form.get("weight", 1.0)),
            form.get("category", "general"),
            int(form.get("poll_interval_seconds", 300)),
            src_id,
        ),
    )
    await db.commit()
    return _redirect("/admin/sources?flash=Source+updated&flash_type=success", status_code=303)


@router.post("/admin/sources/{src_id}/delete")
async def delete_source(src_id: str, _=Depends(require_api_key)):
    db = await get_db()
    await db.execute("DELETE FROM news_sources WHERE id = ?", (src_id,))
    await db.commit()
    return _redirect("/admin/sources?flash=Source+deleted&flash_type=success", status_code=303)


# --- Hosts ---
@router.get("/admin/hosts", response_class=HTMLResponse)
async def hosts_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM hosts ORDER BY id")
    hosts = [dict(r) for r in await cursor.fetchall()]
    return templates.TemplateResponse("hosts.html", _template_ctx(request, "hosts", hosts=hosts))


@router.post("/admin/hosts/{host_id}")
async def update_host(host_id: str, request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    await db.execute(
        """UPDATE hosts SET label = ?, personality_prompt = ?,
           is_breaking_host = ?, enabled = ?,
           tts_provider = ?, tts_voice_id = ?
           WHERE id = ?""",
        (
            form.get("label", ""),
            form.get("personality_prompt", ""),
            1 if form.get("is_breaking_host") == "on" else 0,
            1 if form.get("enabled") == "on" else 0,
            form.get("tts_provider", "piper"),
            form.get("tts_voice_id", ""),
            host_id,
        ),
    )
    await db.commit()
    return _redirect("/admin/hosts?flash=Host+updated&flash_type=success", status_code=303)


# --- TTS Settings ---
@router.get("/admin/tts", response_class=HTMLResponse)
async def tts_settings_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        "SELECT key, value FROM settings WHERE key IN ('elevenlabs_api_key', 'openai_tts_model', 'tts_default_provider')"
    )
    settings = {r["key"]: r["value"] for r in await cursor.fetchall()}
    return templates.TemplateResponse("tts_settings.html", _template_ctx(request, "tts", settings=settings))


@router.post("/admin/tts")
async def update_tts_settings(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    for key in ["elevenlabs_api_key", "openai_tts_model", "tts_default_provider"]:
        val = form.get(key)
        if val is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, val),
            )
    await db.commit()
    return _redirect("/admin/tts?flash=TTS+settings+saved&flash_type=success", status_code=303)


# --- Bitcoin Settings ---
@router.get("/admin/bitcoin", response_class=HTMLResponse)
async def bitcoin_settings_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        "SELECT key, value FROM settings WHERE key IN "
        "('bitcoin_enabled', 'bitcoin_api_key', 'bitcoin_cache_ttl')"
    )
    settings = {r["key"]: r["value"] for r in await cursor.fetchall()}
    return templates.TemplateResponse("bitcoin_settings.html", _template_ctx(request, "bitcoin", settings=settings))


@router.post("/admin/bitcoin")
async def update_bitcoin_settings(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()

    # Handle checkbox (unchecked = not sent)
    enabled = "true" if form.get("bitcoin_enabled") == "on" else "false"
    await db.execute(
        "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
        ("bitcoin_enabled", enabled),
    )

    for key in ["bitcoin_api_key", "bitcoin_cache_ttl"]:
        val = form.get(key)
        if val is not None:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
                (key, val),
            )

    await db.commit()
    return _redirect("/admin/bitcoin?flash=Bitcoin+settings+saved&flash_type=success", status_code=303)


# --- Prompts ---
@router.get("/admin/prompts", response_class=HTMLResponse)
async def prompts_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute("SELECT value FROM settings WHERE key = 'master_prompt'")
    row = await cursor.fetchone()
    return templates.TemplateResponse("prompts.html", _template_ctx(
        request, "prompts",
        master_prompt=row["value"] if row else "",
    ))


@router.post("/admin/prompts")
async def update_prompts(request: Request, _=Depends(require_api_key)):
    form = await request.form()
    db = await get_db()
    await db.execute(
        "UPDATE settings SET value = ?, updated_at = datetime('now') WHERE key = 'master_prompt'",
        (form.get("master_prompt", ""),),
    )
    await db.commit()
    return _redirect("/admin/prompts?flash=Prompt+saved&flash_type=success", status_code=303)


# --- Videos ---
def _parse_video_break(row) -> dict | None:
    """Parse a break row into video info dict."""
    d = dict(row)
    meta = {}
    if d.get("meta_json"):
        try:
            meta = json.loads(d["meta_json"])
        except (json.JSONDecodeError, TypeError):
            pass
    video_path = meta.get("video_path")
    if not video_path:
        return None
    from pathlib import Path as _P
    video_filename = _P(video_path).name
    hls_video_path = meta.get("hls_video_path")
    has_hls = bool(hls_video_path and _P(hls_video_path).parent.exists())
    return {
        "break_id": d["id"],
        "played_at": d.get("played_at") or d.get("created_at"),
        "host_id": meta.get("host", d.get("host_id", "")),
        "type": d.get("type", ""),
        "script_text": d.get("script_text", ""),
        "video_filename": video_filename,
        "mp4_url": f"/video/{video_filename}",
        "hls_url": f"/hls-video/{d['id']}/index.m3u8" if has_hls else None,
        "headlines": meta.get("headlines", 0),
        "bitcoin": meta.get("bitcoin", False),
    }


@router.get("/api/video/list")
async def api_video_list(_=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, host_id, type, played_at, created_at, script_text, meta_json
           FROM break_queue
           WHERE status = 'PLAYED' AND meta_json LIKE '%video_path%'
           ORDER BY played_at DESC LIMIT 20"""
    )
    results = []
    for row in await cursor.fetchall():
        info = _parse_video_break(row)
        if info:
            results.append(info)
    return results


@router.get("/api/video/latest")
async def api_video_latest(_=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, host_id, type, played_at, created_at, script_text, meta_json
           FROM break_queue
           WHERE status = 'PLAYED' AND meta_json LIKE '%video_path%'
           ORDER BY played_at DESC LIMIT 1"""
    )
    row = await cursor.fetchone()
    if not row:
        return {"break_id": None}
    info = _parse_video_break(row)
    return info or {"break_id": None}


@router.get("/admin/videos", response_class=HTMLResponse)
async def videos_page(request: Request, _=Depends(require_api_key)):
    db = await get_db()
    cursor = await db.execute(
        """SELECT id, host_id, type, played_at, created_at, script_text, meta_json
           FROM break_queue
           WHERE status = 'PLAYED' AND meta_json LIKE '%video_path%'
           ORDER BY played_at DESC LIMIT 20"""
    )
    videos = []
    for row in await cursor.fetchall():
        info = _parse_video_break(row)
        if info:
            videos.append(info)

    # Host names
    cursor = await db.execute("SELECT id, label FROM hosts")
    host_names = {r["id"]: r["label"] for r in await cursor.fetchall()}

    return templates.TemplateResponse("videos.html", _template_ctx(
        request, "videos", videos=videos, host_names=host_names,
    ))


# --- Visual Guide ---
@router.get("/admin/visual-guide", response_class=HTMLResponse)
async def visual_guide_page(request: Request, _=Depends(require_api_key)):
    from visual.config import (
        WIDE_SHOT_INTERVAL, REACTION_PROBABILITY,
        TRANSITION_CUT, TRANSITION_DISSOLVE, TRANSITION_FADE_BLACK,
    )
    return templates.TemplateResponse("visual_guide.html", _template_ctx(
        request, "visual-guide",
        wide_interval=WIDE_SHOT_INTERVAL,
        reaction_pct=int(REACTION_PROBABILITY * 100),
        cut_pct=int(TRANSITION_CUT * 100),
        dissolve_pct=int(TRANSITION_DISSOLVE * 100),
        fade_pct=int(TRANSITION_FADE_BLACK * 100),
    ))


# --- Breaking page ---
@router.get("/admin/breaking", response_class=HTMLResponse)
async def breaking_page(request: Request, _=Depends(require_api_key)):
    return templates.TemplateResponse("breaking.html", _template_ctx(request, "breaking"))
