"""Generate placeholder test assets with Pillow.

Run: python visual/create_test_assets.py
Creates PNG placeholders in assets/ for testing the full pipeline without real art.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# Character dimensions
CHAR_W, CHAR_H = 400, 700
BG_W, BG_H = 1920, 1080

# Per-character configs with shot-type positions
CHARACTER_CONFIGS = {
    "alex": {
        "label": "Alex",
        "position_x": 0.3,
        "position_y": 0.85,
        "scale": 0.9,
        "positions": {
            "wide": [0.3, 0.85, 0.6],
            "closeup_left": [0.5, 0.85, 1.0],
            "closeup_right": [0.5, 0.85, 1.0],
            "twoshot": [0.3, 0.85, 0.8],
        },
        "idle_color": "#1a5276",
        "talking_color": "#2e86c1",
    },
    "maya": {
        "label": "Maya",
        "position_x": 0.7,
        "position_y": 0.85,
        "scale": 0.9,
        "positions": {
            "wide": [0.7, 0.85, 0.6],
            "closeup_left": [0.5, 0.85, 1.0],
            "closeup_right": [0.5, 0.85, 1.0],
            "twoshot": [0.7, 0.85, 0.8],
        },
        "idle_color": "#7b241c",
        "talking_color": "#e74c3c",
    },
    "rolo": {
        "label": "Rolo",
        "position_x": 0.5,
        "position_y": 0.85,
        "scale": 0.9,
        "positions": {
            "wide": [0.5, 0.85, 0.6],
            "closeup_left": [0.5, 0.85, 1.0],
            "closeup_right": [0.5, 0.85, 1.0],
            "twoshot": [0.5, 0.85, 0.8],
        },
        "idle_color": "#1e8449",
        "talking_color": "#27ae60",
    },
}


def _get_font(size: int = 36):
    """Try to load a TTF font, fall back to default."""
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_label(draw: ImageDraw.ImageDraw, text: str, w: int, h: int):
    """Draw centered label text."""
    font = _get_font(32)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) // 2, (h - th) // 2), text, fill="white", font=font)


def create_character(name: str, cfg: dict):
    """Create idle.png, talking.png, and config.json for a character."""
    char_dir = ASSETS_DIR / "characters" / name
    char_dir.mkdir(parents=True, exist_ok=True)

    idle_color = cfg["idle_color"]
    talking_color = cfg["talking_color"]

    for state, color in [("idle", idle_color), ("talking", talking_color)]:
        img = Image.new("RGBA", (CHAR_W, CHAR_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [40, 40, CHAR_W - 40, CHAR_H - 40],
            radius=30,
            fill=color,
            outline="white",
            width=3,
        )
        _draw_label(draw, f"{name}\n{state}", CHAR_W, CHAR_H)
        img.save(char_dir / f"{state}.png")
        print(f"  Created {char_dir / f'{state}.png'}")

    # config.json with positions
    config = {
        "label": cfg["label"],
        "position_x": cfg["position_x"],
        "position_y": cfg["position_y"],
        "scale": cfg["scale"],
        "positions": cfg["positions"],
    }
    (char_dir / "config.json").write_text(json.dumps(config, indent=2))
    print(f"  Created {char_dir / 'config.json'}")


def create_background(name: str, color: str, label: str):
    """Create a background PNG."""
    bg_dir = ASSETS_DIR / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (BG_W, BG_H), color)
    draw = ImageDraw.Draw(img)
    # Grid lines for visual reference
    for x in range(0, BG_W, 200):
        draw.line([(x, 0), (x, BG_H)], fill="#333333", width=1)
    for y in range(0, BG_H, 200):
        draw.line([(0, y), (BG_W, y)], fill="#333333", width=1)
    _draw_label(draw, label, BG_W, BG_H)
    path = bg_dir / f"{name}.png"
    img.save(path)
    print(f"  Created {path}")


def main():
    print("[test_assets] Generating placeholder assets...")

    # Characters
    for name, cfg in CHARACTER_CONFIGS.items():
        create_character(name, cfg)

    # Backgrounds
    create_background("studio_wide", "#1c1c2e", "STUDIO — WIDE")
    create_background("studio_closeup_left", "#1c2e1c", "STUDIO — CLOSEUP LEFT")
    create_background("studio_closeup_right", "#2e1c1c", "STUDIO — CLOSEUP RIGHT")
    create_background("studio_twoshot", "#2e2e1c", "STUDIO — TWO SHOT")

    print("[test_assets] Done! Assets in:", ASSETS_DIR)


if __name__ == "__main__":
    main()
