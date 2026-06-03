"""
cf2/tools/debate_topic_overlay.py

Migrated from: core/render/overlay/topic_overlay.py — Topic Banner Overlay

Responsibility: Draw the topic label + value at the TOP of a PIL frame.
Pure rendering — no config loading, no file I/O.
"""
from typing import List
from PIL import Image, ImageDraw, ImageFont

FONT_BOLD    = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


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
        w = draw.textbbox((0, 0), test, font=font)[2]
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _apply_pill(
    pil_img: Image.Image,
    x1: int, y1: int, x2: int, y2: int,
    alpha: int = 155,
) -> Image.Image:
    """Overlay a semi-transparent rounded rectangle on pil_img (in-place paste)."""
    overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    pad = 8
    od.rounded_rectangle([x1 - pad, y1 - pad, x2 + pad, y2 + pad],
                         radius=10, fill=(0, 0, 0, alpha))
    merged = Image.alpha_composite(pil_img.convert("RGBA"), overlay).convert("RGB")
    pil_img.paste(merged)
    return pil_img


def draw(
    pil_img: Image.Image,
    topic: str,
    fmt: str,
    width: int,
    height: int,
) -> Image.Image:
    """
    Draw topic banner at the top of pil_img.

    Shorts → 2 lines: "Topic:" then "<value>"
    HD     → single row if topic fits, else 2 rows (label then value)

    Returns modified pil_img (mutated in-place, also returned for chaining).
    """
    is_shorts  = "Shorts" in fmt
    padding_x  = int(width * 0.04)
    max_w      = width - padding_x * 2
    label_fs   = max(20, int(width * 0.030))
    value_fs   = max(22, int(width * 0.036))
    top_margin = int(height * 0.018)
    line_gap   = int(value_fs * 0.3)

    try:
        font_label = ImageFont.truetype(FONT_REGULAR, label_fs)
        font_value = ImageFont.truetype(FONT_BOLD,    value_fs)
    except Exception:
        font_label = font_value = ImageFont.load_default()

    draw_ctx = ImageDraw.Draw(pil_img)
    label_text, value_text = "Topic:", topic

    if is_shorts:
        # ── Shorts: 2-line layout ─────────────────────────────────────────
        label_h  = draw_ctx.textbbox((0, 0), label_text, font=font_label)[3]
        val_line = (_wrap_text(value_text, font_value, draw_ctx, max_w) or [value_text])[0]
        val_bbox = draw_ctx.textbbox((0, 0), val_line, font=font_value)
        val_h    = val_bbox[3] - val_bbox[1]
        block_h  = label_h + line_gap + val_h
        pill_w   = max(draw_ctx.textbbox((0, 0), label_text, font=font_label)[2], val_bbox[2])
        pil_img  = _apply_pill(pil_img, padding_x, top_margin,
                               padding_x + pill_w, top_margin + block_h)
        draw_ctx = ImageDraw.Draw(pil_img)
        draw_ctx.text((padding_x + 2, top_margin + 2), label_text, font=font_label, fill=(0, 0, 0))
        draw_ctx.text((padding_x,     top_margin),     label_text, font=font_label, fill=(220, 220, 220))
        y_val = top_margin + label_h + line_gap
        draw_ctx.text((padding_x + 2, y_val + 2), val_line, font=font_value, fill=(0, 0, 0))
        draw_ctx.text((padding_x,     y_val),     val_line, font=font_value, fill=(255, 255, 255))

    else:
        # ── HD: single row if topic fits, else 2-row layout ───────────────
        sep     = "  "
        label_w = draw_ctx.textbbox((0, 0), label_text + sep, font=font_label)[2]
        label_h = draw_ctx.textbbox((0, 0), label_text + sep, font=font_label)[3]

        # Check if FULL topic fits on one row alongside label
        # (must measure untruncated text — not wrapped line, which always fits)
        full_topic_w    = draw_ctx.textbbox((0, 0), value_text, font=font_value)[2]
        fits_single_row = full_topic_w <= (max_w - label_w)
        val_line_single = value_text  # used in single-row branch below

        if fits_single_row:
            # ── Single row: "Topic:  <full value>" ───────────────────────
            val_bbox = draw_ctx.textbbox((0, 0), val_line_single, font=font_value)
            val_w    = val_bbox[2]
            val_h    = val_bbox[3]
            line_h   = max(label_h, val_h)
            pil_img  = _apply_pill(pil_img, padding_x, top_margin,
                                   padding_x + label_w + val_w, top_margin + line_h)
            draw_ctx = ImageDraw.Draw(pil_img)
            draw_ctx.text((padding_x + 2, top_margin + 2), label_text + sep,
                          font=font_label, fill=(0, 0, 0))
            draw_ctx.text((padding_x,     top_margin),     label_text + sep,
                          font=font_label, fill=(200, 200, 200))
            x_val = padding_x + label_w
            draw_ctx.text((x_val + 2, top_margin + 2), val_line_single,
                          font=font_value, fill=(0, 0, 0))
            draw_ctx.text((x_val,     top_margin),     val_line_single,
                          font=font_value, fill=(255, 255, 255))

        else:
            # ── Two rows: "Topic:" on row 1, full value on row 2 ─────────
            val_lines = (
                _wrap_text(value_text, font_value, draw_ctx, max_w)
                or [value_text]
            )
            val_line  = val_lines[0]   # first (longest fitting) line
            val_bbox  = draw_ctx.textbbox((0, 0), val_line, font=font_value)
            val_h     = val_bbox[3] - val_bbox[1]
            block_h   = label_h + line_gap + val_h
            pill_w    = max(
                draw_ctx.textbbox((0, 0), label_text + sep, font=font_label)[2],
                val_bbox[2],
            )
            pil_img   = _apply_pill(pil_img, padding_x, top_margin,
                                    padding_x + pill_w, top_margin + block_h)
            draw_ctx  = ImageDraw.Draw(pil_img)
            draw_ctx.text((padding_x + 2, top_margin + 2), label_text + sep,
                          font=font_label, fill=(0, 0, 0))
            draw_ctx.text((padding_x,     top_margin),     label_text + sep,
                          font=font_label, fill=(200, 200, 200))
            y_val = top_margin + label_h + line_gap
            draw_ctx.text((padding_x + 2, y_val + 2), val_line,
                          font=font_value, fill=(0, 0, 0))
            draw_ctx.text((padding_x,     y_val),     val_line,
                          font=font_value, fill=(255, 255, 255))

    return pil_img
