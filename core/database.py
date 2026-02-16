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
        # Run migrations for existing DBs
        await _migrate(db)
        return

    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    if not os.path.exists(schema_path):
        schema_path = "/opt/hermes/schema.sql"

    with open(schema_path) as f:
        await db.executescript(f.read())
    print("[db] Schema initialized")


async def _migrate(db: aiosqlite.Connection):
    """Idempotent migrations for existing databases."""
    # Check if hosts table has tts_provider column
    cursor = await db.execute("PRAGMA table_info(hosts)")
    columns = {row[1] for row in await cursor.fetchall()}

    if "tts_provider" not in columns:
        await db.execute("ALTER TABLE hosts ADD COLUMN tts_provider TEXT DEFAULT 'piper'")
        await db.execute("ALTER TABLE hosts ADD COLUMN tts_voice_id TEXT DEFAULT ''")
        # Copy piper_model → tts_voice_id for existing hosts
        await db.execute("UPDATE hosts SET tts_voice_id = piper_model WHERE tts_voice_id = ''")
        print("[db] Migration: added tts_provider, tts_voice_id to hosts")

    # Ensure TTS settings rows exist
    for key, default in [
        ("elevenlabs_api_key", ""),
        ("openai_tts_model", "tts-1"),
        ("tts_default_provider", "piper"),
        ("break_min_words", "15"),
        ("break_max_words", "100"),
        ("break_max_chars", "600"),
        ("breaking_min_words", "10"),
        ("breaking_max_words", "50"),
    ]:
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, default),
        )

    await db.commit()
