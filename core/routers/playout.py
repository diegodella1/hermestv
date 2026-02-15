"""Playout router — receives webhooks from Liquidsoap."""

import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Request

from core.database import get_db

router = APIRouter(prefix="/api/playout", tags=["playout"])

# Will be set by main.py after break_builder is imported
_prepare_break_fn = None

# Recent tracks (in-memory ring buffer for LLM context)
_recent_tracks: list[dict] = []
MAX_RECENT = 10


def get_recent_tracks(n: int = 4) -> list[dict]:
    """Return last N played tracks (newest first)."""
    return list(reversed(_recent_tracks[-n:]))


def set_prepare_break_fn(fn):
    global _prepare_break_fn
    _prepare_break_fn = fn


@router.post("/event")
async def playout_event(request: Request, body: dict):
    """Receive track events from Liquidsoap."""
    # Only accept from localhost
    client = request.client
    if client and client.host not in ("127.0.0.1", "::1", "localhost"):
        return {"status": "forbidden"}

    event = body.get("event")
    track_count = body.get("tracks_since_last_break", 0)
    track_info = body.get("track", {})

    # Store in recent tracks buffer
    if track_info.get("artist") or track_info.get("title"):
        _recent_tracks.append({
            "artist": track_info.get("artist", "Unknown"),
            "title": track_info.get("title", "Unknown"),
            "filename": track_info.get("filename", ""),
        })
        if len(_recent_tracks) > MAX_RECENT:
            _recent_tracks.pop(0)

    db = await get_db()

    # Log event
    await db.execute(
        "INSERT INTO events_log (event_type, payload_json) VALUES (?, ?)",
        ("track_change", json.dumps(body)),
    )
    await db.commit()

    # Check if we should prepare a break
    action = "none"

    settings = {}
    cursor = await db.execute("SELECT key, value FROM settings")
    for row in await cursor.fetchall():
        settings[row["key"]] = row["value"]

    prepare_at = int(settings.get("prepare_at_track", "3"))
    every_n = int(settings.get("every_n_tracks", "4"))
    quiet_mode = settings.get("quiet_mode", "false") == "true"

    if not quiet_mode and track_count == prepare_at and _prepare_break_fn:
        action = "prepare_break"
        # Fire-and-forget break preparation with recent tracks context
        recent = get_recent_tracks(4)
        asyncio.create_task(_prepare_break_fn(recent_tracks=recent))

    return {"status": "ok", "action": action, "track_count": track_count}
