"""Sync character DB row → filesystem config.json for visual pipeline."""

import json
from pathlib import Path

from core.config import ASSETS_DIR


def sync_character_config(char_id: str, row: dict):
    """Write config.json from DB row so AssetPack picks it up unchanged.

    Args:
        char_id: Character slug (e.g. "alex")
        row: Dict with at least label, position_x, position_y, scale, positions_json
    """
    char_dir = Path(ASSETS_DIR) / "characters" / char_id
    char_dir.mkdir(parents=True, exist_ok=True)

    positions = {}
    raw = row.get("positions_json", "{}")
    if raw:
        try:
            positions = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            pass

    config = {
        "label": row.get("label", char_id),
        "position_x": row.get("position_x", 0.5),
        "position_y": row.get("position_y", 0.85),
        "scale": row.get("scale", 0.9),
        "positions": positions,
    }

    config_path = char_dir / "config.json"
    config_path.write_text(json.dumps(config, indent=2))
