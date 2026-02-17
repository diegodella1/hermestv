"""Asset loader — loads and validates character PNGs and backgrounds."""

import json
from pathlib import Path

from visual.config import DEFAULT_ASSETS_DIR
from visual.models import CharacterConfig


class AssetPack:
    """Loaded and validated asset bundle."""

    def __init__(self, assets_dir: Path | None = None):
        self.assets_dir = Path(assets_dir or DEFAULT_ASSETS_DIR)
        self.characters: dict[str, CharacterConfig] = {}
        self.backgrounds: dict[str, Path] = {}

    def load(self, character_ids: list[str]) -> None:
        """Load characters and discover backgrounds."""
        self._load_characters(character_ids)
        self._load_backgrounds()

    def _load_characters(self, character_ids: list[str]) -> None:
        chars_dir = self.assets_dir / "characters"
        for cid in character_ids:
            char_dir = chars_dir / cid
            if not char_dir.is_dir():
                raise FileNotFoundError(f"Character directory not found: {char_dir}")

            idle = char_dir / "idle.png"
            talking = char_dir / "talking.png"
            config_file = char_dir / "config.json"

            if not idle.exists():
                raise FileNotFoundError(f"Missing idle.png for {cid}")
            if not talking.exists():
                raise FileNotFoundError(f"Missing talking.png for {cid}")

            # Load config (optional — defaults are fine)
            cfg = {}
            if config_file.exists():
                cfg = json.loads(config_file.read_text())

            # Build per-shot positions dict
            positions = cfg.get("positions", {})

            # Build emotion states by scanning PNGs
            states = self._scan_emotion_states(char_dir, idle, talking)

            self.characters[cid] = CharacterConfig(
                char_id=cid,
                label=cfg.get("label", cid.capitalize()),
                idle_path=idle,
                talking_path=talking,
                position_x=cfg.get("position_x", 0.5),
                position_y=cfg.get("position_y", 0.7),
                scale=cfg.get("scale", 1.0),
                positions=positions,
                states=states,
            )
            print(f"[assets] Loaded character: {cid} "
                  f"({len(positions)} positions, {len(states)} emotions)")

    def _scan_emotion_states(
        self, char_dir: Path, default_idle: Path, default_talking: Path
    ) -> dict:
        """Scan for emotion-specific PNGs (e.g. excited_idle.png, excited_talking.png).

        Returns: {"neutral": {"idle": Path, "talking": Path}, "excited": {...}, ...}
        Always includes "neutral" pointing to default idle/talking.
        """
        states = {"neutral": {"idle": default_idle, "talking": default_talking}}

        for png in char_dir.glob("*_idle.png"):
            emotion = png.stem.replace("_idle", "")
            if emotion == "idle":
                continue
            talking_png = char_dir / f"{emotion}_talking.png"
            states[emotion] = {
                "idle": png,
                "talking": talking_png if talking_png.exists() else default_talking,
            }

        return states

    def _load_backgrounds(self) -> None:
        bg_dir = self.assets_dir / "backgrounds"
        if not bg_dir.is_dir():
            raise FileNotFoundError(f"Backgrounds directory not found: {bg_dir}")

        for png in sorted(bg_dir.glob("*.png")):
            key = png.stem  # e.g. "studio_wide"
            self.backgrounds[key] = png
            print(f"[assets] Loaded background: {key}")

        if not self.backgrounds:
            raise FileNotFoundError(f"No background PNGs found in {bg_dir}")

    def get_background(self, shot_type: str, base: str = "studio") -> Path:
        """Get background path for a shot type.

        Tries: {base}_{shot_type}, then {base}_wide as fallback.
        """
        key = f"{base}_{shot_type}"
        if key in self.backgrounds:
            return self.backgrounds[key]
        # Fallback to wide
        fallback = f"{base}_wide"
        if fallback in self.backgrounds:
            return self.backgrounds[fallback]
        # Last resort: first available
        return next(iter(self.backgrounds.values()))

    def get_character_png(
        self, char_id: str, emotion: str = "neutral", is_talking: bool = False
    ) -> Path:
        """Get the right PNG for a character given emotion and talking state."""
        cfg = self.characters[char_id]
        state_key = "talking" if is_talking else "idle"

        # Try emotion-specific first
        if emotion in cfg.states:
            return cfg.states[emotion][state_key]

        # Fallback to neutral
        if "neutral" in cfg.states:
            return cfg.states["neutral"][state_key]

        # Last resort: default paths
        return cfg.talking_path if is_talking else cfg.idle_path

    def get_character_position(
        self, char_id: str, shot_type: str
    ) -> tuple[float, float, float]:
        """Get (x, y, scale) for a character in a given shot type.

        Falls back to default position_x/position_y/scale if no per-shot config.
        """
        cfg = self.characters[char_id]

        if shot_type in cfg.positions:
            pos = cfg.positions[shot_type]
            return (pos[0], pos[1], pos[2])

        # Fallback to default
        return (cfg.position_x, cfg.position_y, cfg.scale)
