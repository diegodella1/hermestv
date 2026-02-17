"""Lower thirds / chyrons — text overlays for speaker names and headlines."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from visual.config import WIDTH, HEIGHT

# Layout constants
LT_MARGIN_LEFT = 80
LT_MARGIN_BOTTOM = 100
LT_BAR_HEIGHT = 70
LT_NAME_BAR_WIDTH = 350
LT_HEADLINE_BAR_WIDTH = 900
LT_BAR_RADIUS = 8
LT_BAR_COLOR = (20, 20, 40, 200)  # dark semi-transparent
LT_ACCENT_COLOR = (220, 50, 50, 255)  # red accent stripe
LT_ACCENT_WIDTH = 6
LT_NAME_COLOR = (255, 255, 255, 255)
LT_HEADLINE_COLOR = (200, 200, 200, 255)
LT_FONT_SIZE_NAME = 30
LT_FONT_SIZE_HEADLINE = 22


def _get_font(size: int = 30, bold: bool = False):
    """Try to load a TTF font."""
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_lower_third(
    base_img: Image.Image,
    speaker_name: str | None = None,
    headline: str | None = None,
) -> Image.Image:
    """Overlay a lower third on an existing frame.

    Args:
        base_img: The composed frame (RGB, 1920x1080)
        speaker_name: Speaker name to show (e.g. "Alex")
        headline: Headline text (e.g. "Bitcoin Surpasses $200K")

    Returns:
        New image with lower third overlay.
    """
    if not speaker_name and not headline:
        return base_img

    # Work on RGBA for alpha compositing
    result = base_img.convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    y_base = HEIGHT - LT_MARGIN_BOTTOM - LT_BAR_HEIGHT

    if speaker_name:
        _draw_name_bar(draw, speaker_name, y_base)

    if headline:
        y_headline = y_base + LT_BAR_HEIGHT + 8
        _draw_headline_bar(draw, headline, y_headline)

    result = Image.alpha_composite(result, overlay)
    return result.convert("RGB")


def _draw_name_bar(draw: ImageDraw.ImageDraw, name: str, y: int) -> None:
    """Draw the speaker name bar."""
    x = LT_MARGIN_LEFT
    # Accent stripe
    draw.rectangle(
        [x, y, x + LT_ACCENT_WIDTH, y + LT_BAR_HEIGHT],
        fill=LT_ACCENT_COLOR,
    )
    # Background bar
    draw.rounded_rectangle(
        [x + LT_ACCENT_WIDTH, y, x + LT_NAME_BAR_WIDTH, y + LT_BAR_HEIGHT],
        radius=LT_BAR_RADIUS,
        fill=LT_BAR_COLOR,
    )
    # Text
    font = _get_font(LT_FONT_SIZE_NAME, bold=True)
    text_y = y + (LT_BAR_HEIGHT - LT_FONT_SIZE_NAME) // 2
    draw.text(
        (x + LT_ACCENT_WIDTH + 20, text_y),
        name.upper(),
        fill=LT_NAME_COLOR,
        font=font,
    )


def _draw_headline_bar(draw: ImageDraw.ImageDraw, text: str, y: int) -> None:
    """Draw the headline bar below the name."""
    x = LT_MARGIN_LEFT
    bar_h = 45
    # Background bar
    draw.rounded_rectangle(
        [x, y, x + LT_HEADLINE_BAR_WIDTH, y + bar_h],
        radius=LT_BAR_RADIUS,
        fill=LT_BAR_COLOR,
    )
    # Text
    font = _get_font(LT_FONT_SIZE_HEADLINE, bold=False)
    # Truncate if too long
    max_chars = 60
    display_text = text[:max_chars] + "..." if len(text) > max_chars else text
    text_y = y + (bar_h - LT_FONT_SIZE_HEADLINE) // 2
    draw.text(
        (x + 20, text_y),
        display_text,
        fill=LT_HEADLINE_COLOR,
        font=font,
    )
