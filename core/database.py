"""Hermes TV — aiosqlite database wrapper."""

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

    # Run migrations (creates tables not in schema.sql, e.g. characters)
    await _migrate(db)


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

    # Ensure cache_bitcoin table exists
    await db.execute("""
        CREATE TABLE IF NOT EXISTS cache_bitcoin (
            id TEXT PRIMARY KEY DEFAULT 'btc',
            payload_json TEXT NOT NULL,
            fetched_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)

    # Ensure bitcoin settings exist
    for key, default in [
        ("bitcoin_enabled", "false"),
        ("bitcoin_api_key", ""),
        ("bitcoin_cache_ttl", "300"),
    ]:
        await db.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            (key, default),
        )

    # --- Characters table ---
    await db.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            gender TEXT DEFAULT '',
            age INTEGER DEFAULT 0,
            behavior_prompt TEXT DEFAULT '',
            piper_model TEXT DEFAULT 'en_US-lessac-high',
            host_id TEXT DEFAULT '',
            position_x REAL DEFAULT 0.5,
            position_y REAL DEFAULT 0.85,
            scale REAL DEFAULT 0.9,
            positions_json TEXT DEFAULT '{}',
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed default characters if table is empty
    cursor = await db.execute("SELECT COUNT(*) FROM characters")
    count = (await cursor.fetchone())[0]
    if count == 0:
        await _seed_characters(db)

    await db.commit()


async def _seed_characters(db):
    """Pre-populate characters table from hardcoded data."""
    import json
    from core.character_prompts import CHARACTER_PROMPTS

    seeds = [
        {
            "id": "alex",
            "label": "Alex Nakamoto",
            "gender": "male",
            "behavior_prompt": CHARACTER_PROMPTS.get("alex", ""),
            "piper_model": "en_US-lessac-high",
            "host_id": "host_a",
            "position_x": 0.3,
            "position_y": 0.85,
            "scale": 0.9,
            "positions_json": json.dumps({
                "wide": [0.3, 0.85, 0.6],
                "closeup_left": [0.5, 0.85, 1.0],
                "closeup_right": [0.5, 0.85, 1.0],
                "twoshot": [0.3, 0.85, 0.8],
            }),
        },
        {
            "id": "maya",
            "label": "Maya Torres",
            "gender": "female",
            "behavior_prompt": CHARACTER_PROMPTS.get("maya", ""),
            "piper_model": "en_US-ryan-high",
            "host_id": "host_b",
            "position_x": 0.7,
            "position_y": 0.85,
            "scale": 0.9,
            "positions_json": json.dumps({
                "wide": [0.7, 0.85, 0.6],
                "closeup_left": [0.5, 0.85, 1.0],
                "closeup_right": [0.5, 0.85, 1.0],
                "twoshot": [0.7, 0.85, 0.8],
            }),
        },
        {
            "id": "rolo",
            "label": "Rolo Méndez",
            "gender": "male",
            "behavior_prompt": CHARACTER_PROMPTS.get("rolo", ""),
            "piper_model": "en_US-lessac-high",
            "host_id": "",
            "position_x": 0.5,
            "position_y": 0.85,
            "scale": 0.9,
            "positions_json": json.dumps({
                "wide": [0.5, 0.85, 0.6],
                "closeup_left": [0.5, 0.85, 1.0],
                "closeup_right": [0.5, 0.85, 1.0],
                "twoshot": [0.5, 0.85, 0.8],
            }),
        },
    ]

    for s in seeds:
        await db.execute(
            """INSERT OR IGNORE INTO characters
               (id, label, gender, behavior_prompt, piper_model, host_id,
                position_x, position_y, scale, positions_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                s["id"], s["label"], s["gender"], s["behavior_prompt"],
                s["piper_model"], s["host_id"], s["position_x"],
                s["position_y"], s["scale"], s["positions_json"],
            ),
        )
    print("[db] Seeded 3 default characters")
