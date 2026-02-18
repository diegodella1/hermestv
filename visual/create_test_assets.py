"""Generate stickman placeholder assets with Pillow.

Run: python visual/create_test_assets.py
Creates PNG placeholders in assets/ for testing the full pipeline without real art.
Characters are drawn as stickmen with distinct colors and features.
"""

import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

CHAR_W, CHAR_H = 400, 700
BG_W, BG_H = 1920, 1080

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
        "skin": "#F4C27F",
        "shirt": "#2980b9",
        "tie": "#e74c3c",
        "hair": "#4a3728",
        "hair_style": "short",
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
        "skin": "#D4A574",
        "shirt": "#8e44ad",
        "tie": None,
        "hair": "#1a1a2e",
        "hair_style": "long",
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
        "skin": "#E8B88A",
        "shirt": "#27ae60",
        "tie": "#f39c12",
        "hair": "#c0c0c0",
        "hair_style": "bald",
    },
}


def _get_font(size: int = 36):
    for path in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_stickman(draw: ImageDraw.ImageDraw, cfg: dict, talking: bool):
    """Draw a stickman news anchor."""
    cx = CHAR_W // 2  # center x
    skin = cfg["skin"]
    shirt = cfg["shirt"]
    hair_color = cfg["hair"]
    line_w = 4

    # --- Head (circle) ---
    head_r = 55
    head_cy = 120
    draw.ellipse(
        [cx - head_r, head_cy - head_r, cx + head_r, head_cy + head_r],
        fill=skin, outline="#333", width=line_w
    )

    # --- Hair ---
    hs = cfg["hair_style"]
    if hs == "short":
        # Flat top hair
        draw.arc(
            [cx - head_r - 2, head_cy - head_r - 12, cx + head_r + 2, head_cy + 10],
            start=180, end=0, fill=hair_color, width=14
        )
    elif hs == "long":
        # Flowing hair on sides
        draw.arc(
            [cx - head_r - 2, head_cy - head_r - 8, cx + head_r + 2, head_cy + 10],
            start=180, end=0, fill=hair_color, width=12
        )
        # Side hair strands
        draw.line(
            [cx - head_r, head_cy, cx - head_r - 10, head_cy + 70],
            fill=hair_color, width=10
        )
        draw.line(
            [cx + head_r, head_cy, cx + head_r + 10, head_cy + 70],
            fill=hair_color, width=10
        )
    # bald: no hair drawn

    # --- Eyes ---
    eye_y = head_cy - 8
    eye_sep = 22
    for ex in [cx - eye_sep, cx + eye_sep]:
        draw.ellipse([ex - 6, eye_y - 6, ex + 6, eye_y + 6], fill="white", outline="#333", width=2)
        draw.ellipse([ex - 3, eye_y - 3, ex + 3, eye_y + 3], fill="#333")

    # --- Mouth ---
    mouth_y = head_cy + 25
    if talking:
        # Open mouth (ellipse)
        draw.ellipse(
            [cx - 18, mouth_y - 10, cx + 18, mouth_y + 14],
            fill="#222", outline="#333", width=2
        )
    else:
        # Closed smile
        draw.arc(
            [cx - 16, mouth_y - 8, cx + 16, mouth_y + 8],
            start=0, end=180, fill="#333", width=3
        )

    # --- Neck ---
    neck_top = head_cy + head_r
    neck_bot = neck_top + 25
    draw.line([cx, neck_top, cx, neck_bot], fill=skin, width=14)

    # --- Body/torso (trapezoid for suit jacket) ---
    shoulder_w = 90
    waist_w = 60
    torso_top = neck_bot
    torso_bot = torso_top + 160
    draw.polygon(
        [
            (cx - shoulder_w, torso_top),
            (cx + shoulder_w, torso_top),
            (cx + waist_w, torso_bot),
            (cx - waist_w, torso_bot),
        ],
        fill=shirt, outline="#333", width=line_w
    )

    # --- Tie ---
    if cfg["tie"]:
        tie_color = cfg["tie"]
        # Knot
        draw.polygon(
            [(cx - 8, torso_top), (cx + 8, torso_top), (cx + 12, torso_top + 20), (cx - 12, torso_top + 20)],
            fill=tie_color
        )
        # Tie body
        draw.polygon(
            [(cx - 12, torso_top + 20), (cx + 12, torso_top + 20), (cx + 6, torso_top + 100), (cx - 6, torso_top + 100)],
            fill=tie_color, outline="#333", width=2
        )

    # --- Arms ---
    arm_top = torso_top + 10

    # Left arm: resting on desk
    draw.line(
        [cx - shoulder_w, arm_top, cx - shoulder_w - 50, torso_bot - 20],
        fill=shirt, width=16
    )
    # Left hand
    draw.ellipse(
        [cx - shoulder_w - 60, torso_bot - 32, cx - shoulder_w - 36, torso_bot - 8],
        fill=skin, outline="#333", width=2
    )

    # Right arm
    if talking:
        # Gesturing up
        draw.line(
            [cx + shoulder_w, arm_top, cx + shoulder_w + 40, arm_top - 40],
            fill=shirt, width=16
        )
        draw.ellipse(
            [cx + shoulder_w + 30, arm_top - 54, cx + shoulder_w + 54, arm_top - 30],
            fill=skin, outline="#333", width=2
        )
    else:
        # Resting
        draw.line(
            [cx + shoulder_w, arm_top, cx + shoulder_w + 50, torso_bot - 20],
            fill=shirt, width=16
        )
        draw.ellipse(
            [cx + shoulder_w + 36, torso_bot - 32, cx + shoulder_w + 60, torso_bot - 8],
            fill=skin, outline="#333", width=2
        )

    # --- News desk (bottom bar) ---
    desk_y = torso_bot + 10
    draw.rounded_rectangle(
        [20, desk_y, CHAR_W - 20, CHAR_H - 30],
        radius=8, fill="#2c3e50", outline="#1a252f", width=3
    )
    # Desk highlight strip
    draw.rectangle([30, desk_y + 4, CHAR_W - 30, desk_y + 12], fill="#34495e")


def _draw_name_tag(draw: ImageDraw.ImageDraw, name: str):
    """Draw a name tag at the bottom of the desk."""
    font = _get_font(22)
    bbox = draw.textbbox((0, 0), name, font=font)
    tw = bbox[2] - bbox[0]
    x = (CHAR_W - tw) // 2
    y = CHAR_H - 70
    # Tag background
    draw.rounded_rectangle(
        [x - 12, y - 4, x + tw + 12, y + 28],
        radius=4, fill="#e74c3c"
    )
    draw.text((x, y), name, fill="white", font=font)


def create_character(name: str, cfg: dict):
    """Create idle.png, talking.png, and config.json for a character."""
    char_dir = ASSETS_DIR / "characters" / name
    char_dir.mkdir(parents=True, exist_ok=True)

    for state in ("idle", "talking"):
        img = Image.new("RGBA", (CHAR_W, CHAR_H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        _draw_stickman(draw, cfg, talking=(state == "talking"))
        _draw_name_tag(draw, cfg["label"].upper())
        img.save(char_dir / f"{state}.png")
        print(f"  Created {char_dir / f'{state}.png'}")

    config = {
        "label": cfg["label"],
        "position_x": cfg["position_x"],
        "position_y": cfg["position_y"],
        "scale": cfg["scale"],
        "positions": cfg["positions"],
    }
    (char_dir / "config.json").write_text(json.dumps(config, indent=2))
    print(f"  Created {char_dir / 'config.json'}")


def _draw_studio_bg(draw: ImageDraw.ImageDraw, label: str, accent: str):
    """Draw a TV studio background."""
    # Dark gradient base
    for y in range(BG_H):
        r = int(20 + (y / BG_H) * 15)
        g = int(22 + (y / BG_H) * 12)
        b = int(40 + (y / BG_H) * 20)
        draw.line([(0, y), (BG_W, y)], fill=(r, g, b))

    # Back wall panels
    panel_w = BG_W // 5
    for i in range(5):
        x0 = i * panel_w + 10
        draw.rounded_rectangle(
            [x0, 30, x0 + panel_w - 20, BG_H // 2 - 40],
            radius=12, fill="#1a1a30", outline="#2a2a4a", width=2
        )

    # Accent strip (channel color bar)
    strip_y = BG_H // 2 - 30
    draw.rectangle([0, strip_y, BG_W, strip_y + 6], fill=accent)

    # Floor with subtle reflection
    floor_top = BG_H * 2 // 3
    for y in range(floor_top, BG_H):
        progress = (y - floor_top) / (BG_H - floor_top)
        c = int(30 - progress * 10)
        draw.line([(0, y), (BG_W, y)], fill=(c, c, c + 5))

    # "HERMES TV" bug in corner
    font = _get_font(28)
    draw.text((BG_W - 200, 20), "HERMES TV", fill="#ffffff40", font=font)

    # Shot label (subtle)
    font_sm = _get_font(18)
    draw.text((20, BG_H - 40), label, fill="#555555", font=font_sm)


def create_background(name: str, accent: str, label: str):
    """Create a studio background PNG."""
    bg_dir = ASSETS_DIR / "backgrounds"
    bg_dir.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGB", (BG_W, BG_H), "#141428")
    draw = ImageDraw.Draw(img)
    _draw_studio_bg(draw, label, accent)

    path = bg_dir / f"{name}.png"
    img.save(path)
    print(f"  Created {path}")


def main():
    print("[test_assets] Generating stickman placeholder assets...")

    for name, cfg in CHARACTER_CONFIGS.items():
        create_character(name, cfg)

    create_background("studio_wide", "#e74c3c", "WIDE")
    create_background("studio_closeup_left", "#3498db", "CLOSEUP LEFT")
    create_background("studio_closeup_right", "#e67e22", "CLOSEUP RIGHT")
    create_background("studio_twoshot", "#2ecc71", "TWO SHOT")

    print(f"[test_assets] Done! Assets in: {ASSETS_DIR}")


if __name__ == "__main__":
    main()
