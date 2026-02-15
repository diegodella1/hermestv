"""Break queue — CRUD operations on break_queue table."""

import json
from datetime import datetime, timezone

from core.database import get_db


async def create_break(
    break_id: str,
    break_type: str = "scheduled",
    priority: int = 0,
    host_id: str | None = None,
) -> str:
    """Create a new break entry with PREPARING status."""
    db = await get_db()
    await db.execute(
        """INSERT INTO break_queue (id, type, priority, host_id, status)
           VALUES (?, ?, ?, ?, 'PREPARING')""",
        (break_id, break_type, priority, host_id),
    )
    await db.commit()
    return break_id


async def mark_ready(
    break_id: str,
    script_text: str,
    audio_path: str,
    degradation_level: int = 0,
    duration_ms: int | None = None,
    meta: dict | None = None,
):
    """Mark break as ready for playout."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """UPDATE break_queue
           SET status = 'READY', script_text = ?, audio_path = ?,
               degradation_level = ?, ready_at = ?, duration_ms = ?,
               meta_json = ?
           WHERE id = ?""",
        (
            script_text,
            audio_path,
            degradation_level,
            now,
            duration_ms,
            json.dumps(meta) if meta else None,
            break_id,
        ),
    )
    await db.commit()


async def mark_played(break_id: str):
    """Mark break as played."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE break_queue SET status = 'PLAYED', played_at = ? WHERE id = ?",
        (now, break_id),
    )
    await db.commit()


async def mark_failed(break_id: str, reason: str = ""):
    """Mark break as failed."""
    db = await get_db()
    await db.execute(
        "UPDATE break_queue SET status = 'FAILED', meta_json = ? WHERE id = ?",
        (json.dumps({"error": reason}), break_id),
    )
    await db.commit()


async def get_ready_break() -> dict | None:
    """Get the next READY break (highest priority first)."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT * FROM break_queue
           WHERE status = 'READY'
           ORDER BY priority DESC, created_at ASC
           LIMIT 1"""
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_recent_headline_ids(lookback: int = 2) -> list[str]:
    """Get headline IDs used in the last N played/ready breaks."""
    db = await get_db()
    cursor = await db.execute(
        """SELECT meta_json FROM break_queue
           WHERE status IN ('PLAYED', 'READY')
             AND meta_json IS NOT NULL
           ORDER BY created_at DESC LIMIT ?""",
        (lookback,),
    )
    ids = []
    for row in await cursor.fetchall():
        try:
            meta = json.loads(row["meta_json"])
            ids.extend(meta.get("headline_ids", []))
        except (json.JSONDecodeError, TypeError):
            pass
    return ids


async def get_preparing_break() -> dict | None:
    """Check if there's a break currently being prepared."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM break_queue WHERE status = 'PREPARING' LIMIT 1"
    )
    row = await cursor.fetchone()
    return dict(row) if row else None
