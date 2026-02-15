"""Degradation manager — 5 levels of graceful fallback."""

import os

from core.config import STINGS_DIR
from core.database import get_db


async def get_fallback_script(weather_data: list[dict]) -> tuple[str | None, int]:
    """
    Generate a fallback script from templates + weather data.
    Returns (script_text, degradation_level).

    Level 1: cached template + fresh weather data
    Level 2: pre-written template with weather only
    Level 3: sting audio path (no script)
    Level 4: nothing (music continues)
    """
    db = await get_db()

    # Level 2: template + weather
    if weather_data and len(weather_data) >= 2:
        cursor = await db.execute(
            "SELECT * FROM fallback_templates ORDER BY use_count ASC, RANDOM() LIMIT 1"
        )
        template = await cursor.fetchone()

        if template:
            w1 = weather_data[0]
            w2 = weather_data[1]

            script = template["template_text"].format(
                city1=w1.get("city_label", "City 1"),
                temp1=f"{w1.get('temp', '?')}",
                condition1=w1.get("condition", ""),
                city2=w2.get("city_label", "City 2"),
                temp2=f"{w2.get('temp', '?')}",
                condition2=w2.get("condition", ""),
            )

            # Update usage count
            await db.execute(
                "UPDATE fallback_templates SET use_count = use_count + 1, last_used_at = datetime('now') WHERE id = ?",
                (template["id"],),
            )
            await db.commit()

            return script, 2

    # Level 3: sting audio
    sting_path = os.path.join(str(STINGS_DIR), "station_id.mp3")
    if os.path.exists(sting_path):
        return None, 3  # Caller should use sting directly

    # Level 4: nothing
    return None, 4


def get_sting_path(sting_name: str = "station_id") -> str | None:
    """Get path to a pre-recorded sting."""
    path = os.path.join(str(STINGS_DIR), f"{sting_name}.mp3")
    return path if os.path.exists(path) else None
