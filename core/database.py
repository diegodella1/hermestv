"""Hermes Radio — aiosqlite database wrapper."""

import aiosqlite
from core.config import DB_PATH

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA busy_timeout=5000")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db():
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db():
    """Initialize database from schema.sql if tables don't exist."""
    import os
    db = await get_db()

    # Check if already initialized
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
    )
    if await cursor.fetchone():
        return

    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if not os.path.exists(schema_path):
        schema_path = "/opt/hermes/schema.sql"

    with open(schema_path) as f:
        await db.executescript(f.read())
    print("[db] Schema initialized")
