"""
cf2/tools/debate_subtitle_overlay.py

Migrated from: core/render/overlay/subtitle_overlay.py — Subtitle Bar Overlay

Responsibility: Draw subtitle text at the BOTTOM of a PIL frame.
Pure rendering — no config loading, no file I/O.
"""
from typing import List
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"


def _wrap_text(
    text: str,
    font: ImageFont.FreeTypeFont,
    draw: ImageDraw.ImageDraw,
    max_width: int,
) -> List[str]:
    """Word-wrap text to fit inside max_width pixels."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip() if current else word
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw(
    pil_img: Image.Image,
    text: str,
    fmt: str,
    width: int,
    height: int,
) -> Image.Image:
    """
    Draw subtitle bar at the bottom of pil_img.

    - Up to 2 wrapped lines
    - Semi-transparent dark pill background
    - White text with black drop-shadow

    Returns modified pil_img (mutated in-place, also returned for chaining).
    """
    if not text.strip():
        return pil_img

    is_shorts     = "Shorts" in fmt
    sub_fs        = max(22, int(width * 0.033)) if is_shorts else max(26, int(width * 0.025))
    padding_x     = int(width * 0.04)
    bottom_margin = int(height * 0.04)
    max_w         = width - padding_x * 2

    try:
        font = ImageFont.truetype(FONT_BOLD, sub_fs)
    except Exception:
        font = ImageFont.load_default()

    draw_ctx      = ImageDraw.Draw(pil_img)
    lines         = _wrap_text(text, font, draw_ctx, max_w)
    display_lines = lines[:2]                      # max 2 lines

    line_h  = int(sub_fs * 1.35)
    block_h = len(display_lines) * line_h
    y_start = height - bottom_margin - block_h

    max_line_w = max(
        (draw_ctx.textbbox((0, 0), ln, font=font)[2] for ln in display_lines),
        default=0,
    )

    # Semi-transparent pill
    overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    pad = 10
    od.rounded_rectangle(
        [padding_x - pad, y_start - pad,
         padding_x + max_line_w + pad, y_start + block_h + pad],
        radius=12, fill=(0, 0, 0, 170),
    )
    merged = Image.alpha_composite(pil_img.convert("RGBA"), overlay).convert("RGB")
    pil_img.paste(merged)
    draw_ctx = ImageDraw.Draw(pil_img)

    for i, line in enumerate(display_lines):
        y = y_start + i * line_h
        draw_ctx.text((padding_x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw_ctx.text((padding_x,     y),     line, font=font, fill=(255, 255, 255))

    return pil_img
