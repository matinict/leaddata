"""
classroom_video_renderer.py — Per-segment renderer with random animal/shape bubbles
                               + Hologram overlay support
Destination: src/cf2/tools/classroom_video_renderer.py

Kids 6-10 attraction features:
  - 14 random shapes per segment:
      Geometric: rounded-rect, circle, cloud, starburst, ribbon, hexagon
      Animals:   cat, dog, bunny, bird, fish, fox, panda, owl
  - Random screen position (8 zones + jitter)
  - Each speaker keeps unique color + emoji
  - 3-phase clips: init/loop/trails (same format as prodcast)
  - Clip resolution via cf2.core.clip_resolver (global, shared with prodcast/debate)

Hologram features:
  - [HOLO:source_id:segment_id] tags in script trigger hologram overlays
  - Hologram overlays are large (35-60% of frame), positioned per config
  - HD: bottom_left, center_right, bottom_right, etc.
  - Shorts: center_bottom like a phone landscape screen
  - Zoom parameter controls source magnification (2x = show center 50%)
  - clip_speed controls playback speed (1.5x = faster tutorial)
  - animation controls entry/exit effects (fade_in, slide_up, none)
  - Character animation plays in background behind the hologram panel
"""
from __future__ import annotations
import json
import logging
import re
import subprocess
import textwrap
import random
import math
from typing import Any, Optional
from pathlib import Path
from cf2.core import clip_resolver as common_resolver
from cf2.core.paths import OUTPUT_ROOT


_QUIZ_KP_RE = re.compile(r"^\[(QUIZ|KEY POINTS)\]\s*(.+)$", re.IGNORECASE)

def _expand_sections(s):
    import re
    sec = {"LESSON GOAL":"T1","LEARNING OBJECTIVES":"T2","PRE-THINK":"T1",
           "QUIZ":"T1","KEY POINTS":"T2","EMOTIONAL CLOSURE":"T2"}
    out, cur = [], None
    for line in s.splitlines():
        _qkm = _QUIZ_KP_RE.match(line.strip())
        if _qkm:
            _spk = "T1" if _qkm.group(1).upper() == "QUIZ" else "T2"
            _tn = "Teacher1" if _spk == "T1" else "Teacher2"
            out.append(f"[{_spk}] {_tn}: {_qkm.group(2).strip()}")
            continue
        t = line.strip()
        m = re.match(r"^\[([A-Z][A-Z\s\-_]+)\]\s*(.*)$", t)
        if m and m.group(1) in sec:
            cur = sec[m.group(1)]
            inline = m.group(2).strip()
            if inline:
                out.append(f"[{cur}] Teacher{1 if cur=='T1' else 2}: {inline}")
            continue
        if t.startswith("[PHASE:") or t.startswith("[T") or t.startswith("[S"):
            cur = None
            out.append(line); continue
        if cur and t and not t.startswith("["):
            tn = "Teacher1" if cur == "T1" else "Teacher2"
            cleaned = re.sub(r"^[-*\d.)\s]+", "", t).strip()
            if cleaned: out.append(f"[{cur}] {tn}: " + ("\u2705 " + cleaned if cur=="T2" else cleaned))
            continue
        out.append(line)
    return "\n".join(out)


_SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+([\w][\w\s\-]*?):\s+(.+)$")
_HOLO_RE    = re.compile(r"^\[HOLO:([^\]]+)\]$", re.IGNORECASE)

_STYLES = {
    "T1": ((59, 130, 246),  (37, 99, 235),  "\U0001F393"),
    "T2": ((139, 92, 246),  (124, 58, 237), "\U0001F4DA"),
    "S1": ((16, 185, 129),  (5, 150, 105),  "\U0001F31F"),
    "S2": ((6, 182, 212),   (14, 116, 144), "\U000026A1"),
    "S3": ((245, 158, 11),  (217, 119, 6),  "\U0001F914"),
    "S4": ((239, 68, 68),   (220, 38, 38),  "\U0001F3A8"),
    "S5": ((236, 72, 153),  (219, 39, 119), "\U0001F602"),
    "S6": ((99, 102, 241),  (79, 70, 229),  "\U0001F9D0"),
    "S7": ((20, 184, 166),  (13, 148, 136), "\U0001F33C"),
    "S8": ((249, 115, 22),  (234, 88, 12),  "\U0001F680"),
}
_DEFAULT = ((107, 114, 128), (75, 85, 99), "\U0001F4AC")

_SHAPES = [
    "rounded", "circle", "cloud", "starburst", "ribbon", "hexagon",
    "cat", "dog", "bunny", "bird", "fish", "fox", "panda", "owl",
]

_POSITIONS = [
    "top_left", "top_center", "top_right",
    "mid_left", "mid_right",
    "bottom_left", "bottom_center", "bottom_right",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ffprobe_duration(path: str) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=5
        )
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


# ── Clip Resolution (uses global clip_resolver) ──────────────────────────────

def _resolve_clip_sequence(key, fmt_clips, clips_base, use_prefix, fmt_suffix=""):
    pipeline = [{"key": key}]

    sequences = common_resolver.resolve_clip_sequences(
        pipeline=pipeline,
        fmt_clips=fmt_clips,
        intro_path=None,
        clips_base=clips_base,
        use_prefix=use_prefix,
        fmt_suffix=fmt_suffix,
    )

    seq = sequences.get(key, {})
    result = {"init": "", "loop": "", "trails": ""}

    paths = seq.get("paths", [])
    if paths and len(paths) > 0:
        result["init"] = paths[0][0]

    loops = seq.get("loops", [])
    if loops and len(loops) > 0:
        result["loop"] = loops[0][0]

    tails = seq.get("tail", [])
    if tails and len(tails) > 0:
        result["trails"] = tails[0][0]

    if not result["loop"]:
        result["loop"] = result["init"]
    if not result["trails"]:
        result["trails"] = result["loop"]

    return result


# ── Geometric shape drawers ───────────────────────────────────────────────────

def _draw_rounded(d, box, fill, outline, w=4):
    d.rounded_rectangle(box, radius=28, fill=fill, outline=outline, width=w)

def _draw_circle(d, box, fill, outline, w=4):
    d.ellipse(box, fill=fill, outline=outline, width=w)

def _draw_cloud(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw, bh = x2 - x1, y2 - y1
    d.rounded_rectangle([x1, y1 + bh * 0.25, x2, y2 - bh * 0.05],
                          radius=int(bh * 0.4), fill=fill, outline=outline, width=w)
    r = int(bh * 0.32)
    for px, py in [(x1 + bw * 0.22, y1 + bh * 0.10),
                    (x1 + bw * 0.50, y1),
                    (x1 + bw * 0.78, y1 + bh * 0.12)]:
        d.ellipse([px - r, py, px + r, py + 2 * r],
                   fill=fill, outline=outline, width=w)

def _draw_starburst(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    rxo, ryo = (x2 - x1) // 2, (y2 - y1) // 2
    rxi, ryi = int(rxo * 0.65), int(ryo * 0.65)
    pts = []
    for i in range(24):
        a = math.pi * i / 12
        rx = rxo if i % 2 == 0 else rxi
        ry = ryo if i % 2 == 0 else ryi
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline)

def _draw_ribbon(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    cut = 30
    pts = [(x1 + cut, y1), (x2 - cut, y1), (x2, (y1 + y2) // 2),
           (x2 - cut, y2), (x1 + cut, y2), (x1, (y1 + y2) // 2)]
    d.polygon(pts, fill=fill, outline=outline)

def _draw_hexagon(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    rx, ry = (x2 - x1) // 2, (y2 - y1) // 2
    pts = []
    for i in range(6):
        a = math.pi / 3 * i + math.pi / 6
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    d.polygon(pts, fill=fill, outline=outline)


# ── Animal shape drawers ──────────────────────────────────────────────────────

def _draw_cat(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    ear_h = (y2 - y1) * 0.18
    ear_w = (x2 - x1) * 0.18
    d.polygon([(x1 + ear_w, y1 + ear_h), (x1 + ear_w * 0.3, y1),
               (x1 + ear_w * 2, y1 + ear_h * 0.5)],
              fill=fill, outline=outline)
    d.polygon([(x2 - ear_w, y1 + ear_h), (x2 - ear_w * 0.3, y1),
               (x2 - ear_w * 2, y1 + ear_h * 0.5)],
              fill=fill, outline=outline)
    d.ellipse([x1, y1 + ear_h * 0.7, x2, y2], fill=fill, outline=outline, width=w)

def _draw_dog(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    d.ellipse([x1, y1 + bh * 0.05, x1 + bw * 0.25, y1 + bh * 0.55],
              fill=fill, outline=outline, width=w)
    d.ellipse([x2 - bw * 0.25, y1 + bh * 0.05, x2, y1 + bh * 0.55],
              fill=fill, outline=outline, width=w)
    d.ellipse([x1 + bw * 0.10, y1 + bh * 0.10, x2 - bw * 0.10, y2],
              fill=fill, outline=outline, width=w)

def _draw_bunny(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    ear_w = bw * 0.14
    ear_h = bh * 0.40
    cx = (x1 + x2) // 2
    d.ellipse([cx - ear_w * 1.6, y1, cx - ear_w * 0.4, y1 + ear_h],
              fill=fill, outline=outline, width=w)
    d.ellipse([cx + ear_w * 0.4, y1, cx + ear_w * 1.6, y1 + ear_h],
              fill=fill, outline=outline, width=w)
    d.ellipse([x1, y1 + ear_h * 0.85, x2, y2],
              fill=fill, outline=outline, width=w)

def _draw_bird(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    d.ellipse([x1 + bw * 0.05, y1 + bh * 0.15, x2 - bw * 0.05, y2 - bh * 0.10],
              fill=fill, outline=outline, width=w)
    d.polygon([(x2 - bw * 0.05, y1 + bh * 0.40),
               (x2 + bw * 0.06, y1 + bh * 0.50),
               (x2 - bw * 0.05, y1 + bh * 0.55)],
              fill=outline, outline=outline)
    d.ellipse([x1 + bw * 0.30, y1 + bh * 0.40, x1 + bw * 0.65, y1 + bh * 0.75],
              fill=outline, outline=outline, width=2)

def _draw_fish(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    d.polygon([(x1, y1 + bh * 0.25), (x1 + bw * 0.25, y1 + bh * 0.50),
               (x1, y1 + bh * 0.75)],
              fill=fill, outline=outline)
    d.ellipse([x1 + bw * 0.20, y1 + bh * 0.10, x2, y2 - bh * 0.10],
              fill=fill, outline=outline, width=w)

def _draw_fox(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    d.polygon([(x1, y1 + bh * 0.05), (x1 + bw * 0.20, y1),
               (x1 + bw * 0.30, y1 + bh * 0.30)],
              fill=fill, outline=outline)
    d.polygon([(x2, y1 + bh * 0.05), (x2 - bw * 0.20, y1),
               (x2 - bw * 0.30, y1 + bh * 0.30)],
              fill=fill, outline=outline)
    d.polygon([(x1 + bw * 0.10, y1 + bh * 0.20),
               (x2 - bw * 0.10, y1 + bh * 0.20),
               ((x1 + x2) // 2, y2)],
              fill=fill, outline=outline)

def _draw_panda(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    ear_r = bw * 0.14
    d.ellipse([x1 + bw * 0.05, y1, x1 + bw * 0.05 + ear_r * 2, y1 + ear_r * 2],
              fill=outline, outline=outline)
    d.ellipse([x2 - bw * 0.05 - ear_r * 2, y1, x2 - bw * 0.05, y1 + ear_r * 2],
              fill=outline, outline=outline)
    d.ellipse([x1, y1 + ear_r, x2, y2], fill=fill, outline=outline, width=w)

def _draw_owl(d, box, fill, outline, w=4):
    x1, y1, x2, y2 = box
    bw = x2 - x1
    bh = y2 - y1
    d.polygon([(x1 + bw * 0.15, y1 + bh * 0.15),
               (x1 + bw * 0.25, y1),
               (x1 + bw * 0.35, y1 + bh * 0.15)],
              fill=fill, outline=outline)
    d.polygon([(x2 - bw * 0.15, y1 + bh * 0.15),
               (x2 - bw * 0.25, y1),
               (x2 - bw * 0.35, y1 + bh * 0.15)],
              fill=fill, outline=outline)
    d.ellipse([x1, y1 + bh * 0.10, x2, y2], fill=fill, outline=outline, width=w)


_SHAPE_FNS = {
    "rounded":   _draw_rounded,
    "circle":    _draw_circle,
    "cloud":     _draw_cloud,
    "starburst": _draw_starburst,
    "ribbon":    _draw_ribbon,
    "hexagon":   _draw_hexagon,
    "cat":       _draw_cat,
    "dog":       _draw_dog,
    "bunny":     _draw_bunny,
    "bird":      _draw_bird,
    "fish":      _draw_fish,
    "fox":       _draw_fox,
    "panda":     _draw_panda,
    "owl":       _draw_owl,
}

_INSET = {
    "rounded": 18, "circle": 60, "cloud": 30, "starburst": 70,
    "ribbon": 40, "hexagon": 50,
    "cat": 40, "dog": 40, "bunny": 50, "bird": 35,
    "fish": 50, "fox": 45, "panda": 40, "owl": 45,
}


def _pick_position(cw, ch, bw, bh, key):
    mx = int(cw * 0.04)
    my = int(ch * 0.05)
    if key.startswith("top"):
        y = my
    elif key.startswith("mid"):
        y = (ch - bh) // 2
    else:
        y = ch - bh - my
    if key.endswith("left"):
        x = mx
    elif key.endswith("right"):
        x = cw - bw - mx
    else:
        x = (cw - bw) // 2
    x += random.randint(-20, 20)
    y += random.randint(-15, 15)
    return max(10, min(cw - bw - 10, x)), max(10, min(ch - bh - 10, y))


# ── Bubble PNG generator ──────────────────────────────────────────────────────

def _make_bubble_png(path, tag, name, text, cw, ch, seed, bubble_cfg=None):
    bubble_cfg = bubble_cfg or {}
    from PIL import Image, ImageDraw, ImageFont

    rng = random.Random(seed)
    bg, border, emoji = _STYLES.get(tag, _DEFAULT)

    is_short = ch > cw
    shape = rng.choice(_SHAPES)
    position = rng.choice(_POSITIONS)

    FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    try:
        name_font  = ImageFont.truetype(FONT_BOLD, 32 if not is_short else 26)
        text_font  = ImageFont.truetype(FONT_REG,  26 if not is_short else 22)
        tag_font   = ImageFont.truetype(FONT_BOLD, 20)
        emoji_font = ImageFont.truetype(FONT_BOLD, 34 if not is_short else 28)
    except Exception:
        name_font = text_font = tag_font = emoji_font = ImageFont.load_default()

    char_limit = 30 if is_short else 38
    wrapped = textwrap.wrap(text, width=char_limit) or [text]

    pad = 22
    line_h = 34 if not is_short else 28
    text_block_h = len(wrapped) * line_h
    header_h = 50

    is_animal = shape in ("cat", "dog", "bunny", "bird", "fish", "fox", "panda", "owl")
    extra = 80 if is_animal else 30

    bubble_w = min(int(cw * 0.55),
                   max(420, max(len(l) for l in wrapped) * 17) + pad * 2 + extra)
    bubble_h = pad + header_h + 8 + text_block_h + pad + extra

    bx, by = _pick_position(cw, ch, bubble_w, bubble_h, position)

    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    so = 5
    sbox = [bx + so, by + so, bx + bubble_w + so, by + bubble_h + so]
    _SHAPE_FNS[shape](draw, sbox, (0, 0, 0, 70), (0, 0, 0, 70), 1)

    box = [bx, by, bx + bubble_w, by + bubble_h]
    _op = int(bubble_cfg.get("opacity", 130))
    _SHAPE_FNS[shape](draw, box, (*bg, _op), (*border, min(255, _op + 70)), 4)

    if is_animal:
        eye_y = by + int(bubble_h * 0.30)
        eye_r = 12
        draw.ellipse([bx + bubble_w * 0.30 - eye_r, eye_y - eye_r,
                       bx + bubble_w * 0.30 + eye_r, eye_y + eye_r],
                      fill=(255, 255, 255, 240))
        draw.ellipse([bx + bubble_w * 0.70 - eye_r, eye_y - eye_r,
                       bx + bubble_w * 0.70 + eye_r, eye_y + eye_r],
                      fill=(255, 255, 255, 240))
        pr = 5
        draw.ellipse([bx + bubble_w * 0.30 - pr, eye_y - pr,
                       bx + bubble_w * 0.30 + pr, eye_y + pr], fill=(0, 0, 0, 255))
        draw.ellipse([bx + bubble_w * 0.70 - pr, eye_y - pr,
                       bx + bubble_w * 0.70 + pr, eye_y + pr], fill=(0, 0, 0, 255))

    inset = _INSET.get(shape, 20)
    cx = bx + inset
    cy = by + inset + (40 if is_animal else 0)

    bubble_cx = bx + bubble_w // 2
    name_w = draw.textbbox((0, 0), name, font=name_font)[2]
    header_w = 48 + name_w
    hx = bubble_cx - header_w // 2
    draw.text((hx, cy), emoji, font=emoji_font, fill=(255, 255, 255, 255))
    draw.text((hx + 48, cy + 4), name, font=name_font, fill=(255, 255, 255, 255))

    tag_text = f"[{tag}]"
    tw_ = draw.textbbox((0, 0), tag_text, font=tag_font)[2]
    tx = bx + bubble_w - tw_ - inset - 8
    ty = by + inset
    draw.rounded_rectangle([tx - 8, ty - 4, tx + tw_ + 8, ty + 26],
                            radius=10, fill=(255, 255, 255, 60))
    draw.text((tx, ty), tag_text, font=tag_font, fill=(255, 255, 0, 240))

    div_y = cy + header_h - 4
    draw.line([(cx, div_y), (bx + bubble_w - inset, div_y)],
               fill=(255, 255, 255, 90), width=2)

    ty = div_y + 12
    for line in wrapped:
        lw = draw.textbbox((0, 0), line, font=text_font)[2]
        lx = bubble_cx - lw // 2
        draw.text((lx + 2, ty + 2), line, font=text_font, fill=(0, 0, 0, 90))
        draw.text((lx, ty), line, font=text_font, fill=(255, 255, 255, 250))
        ty += line_h

    img.save(path, "PNG")


# ── Hologram overlay compositing ──────────────────────────────────────────────

def _build_hologram_frame(
    bg_clip_path,
    holo_clip_path,
    audio_path: str,
    audio_dur: float,
    output_path: str,
    w: int, h: int, fps: int,
    topic: str = "",
    position: str = "bottom_left",
    scale_pct: float = 0.55,
    zoom: float = 1.0,
    clip_speed: float = 1.0,
    animation: dict = None,
) -> bool:
    """
    Composite hologram overlay onto a character background clip.

    Parameters
    ----------
    bg_clip_path   : character animation clip (looped), or None for solid bg
    holo_clip_path : pre-rendered hologram overlay clip
    position       : "bottom_left", "center_right", "bottom_right",
                     "center_bottom", "center_left", "center"
    scale_pct      : panel width as fraction of canvas width
    zoom           : source magnification from config
                     1.0 = fit whole source
                     2.0 = center 50% (zoomed in on code output)
    clip_speed     : playback speed of hologram clip
                     1.0 = normal, 1.5 = 50% faster, 2.0 = double speed
    animation      : dict with entry/exit effects
                     {"entry": "fade_in", "entry_duration": 0.5,
                      "exit": "none", "exit_duration": 0.0,
                      "slide_direction": "up"}
    """
    animation = animation or {}

    if not holo_clip_path or not Path(holo_clip_path).exists():
        return False
    holo_dur = _ffprobe_duration(holo_clip_path)
    if holo_dur < 0.3:
        return False

    is_shorts = h > w

    # ── Background ──────────────────────────────────────────────────
    has_bg = bg_clip_path and Path(bg_clip_path).exists() and _ffprobe_duration(bg_clip_path) > 0.3
    if has_bg:
        cd = _ffprobe_duration(bg_clip_path)
        loop = ["-stream_loop", "-1"] if cd < audio_dur else []
        inputs = [*loop, "-i", bg_clip_path]
        base_vf = (
            f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},fps={fps}[base]"
        )
    else:
        inputs = ["-f", "lavfi", "-i",
                  f"color=c=0x1a1a2e:s={w}x{h}:r={fps}:d={audio_dur:.3f}"]
        base_vf = "[0:v]copy[base]"

    # ── Hologram sizing ──────────────────────────────────────────────
    border = 3

    if is_shorts:
        holo_w = int(w * 0.92)
        holo_h = int(holo_w * 9 / 16)
    else:
        holo_w = int(w * scale_pct)
        holo_h = int(holo_w * 9 / 16)

    inner_w = holo_w - 2 * border
    inner_h = holo_h - 2 * border

    # ── Position ────────────────────────────────────────────────────
    margin_x = int(w * 0.02)
    margin_y = int(h * 0.02)

    if is_shorts or position == "center_bottom":
        holo_x = (w - holo_w) // 2
        holo_y = h - holo_h - margin_y
    elif position == "bottom_right":
        holo_x = w - holo_w - margin_x
        holo_y = h - holo_h - margin_y
    elif position == "bottom_left":
        holo_x = margin_x
        holo_y = h - holo_h - margin_y
    elif position == "center_right":
        holo_x = w - holo_w - margin_x
        holo_y = (h - holo_h) // 2
    elif position == "center_left":
        holo_x = margin_x
        holo_y = (h - holo_h) // 2
    elif position == "center":
        holo_x = (w - holo_w) // 2
        holo_y = (h - holo_h) // 2
    else:
        holo_x = margin_x
        holo_y = h - holo_h - margin_y

    topic_f = ""
    if topic:
        t_esc = topic.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
        topic_f = (f",drawtext=text='Topic\\: {t_esc}':"
                   f"fontcolor=white:fontsize=44:"
                   f"box=1:boxcolor=black@0.55:boxborderw=12:"
                   f"x=40:y=35:enable='gte(t,0)'")

    # ── Hologram filter chain ────────────────────────────────────────
    #
    # Step 1: Speed adjustment  (setpts=PTS/speed)
    # Step 2: Zoom/scale/crop   (fit or zoom into source)
    # Step 3: Border padding    (cyan border around panel)
    # Step 4: Entry/exit animation (fade_in, slide_up, etc.)
    #
    holo_filter_parts = []

    # Step 1: Speed
    if clip_speed != 1.0:
        holo_filter_parts.append(f"setpts=PTS/{clip_speed:.2f}")

    # Step 2: Zoom + scale + crop
    if zoom <= 1.0:
        # Fit whole source inside panel
        holo_filter_parts.append(
            f"scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease"
        )
        holo_filter_parts.append(
            f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2:color=0x0d1117"
        )
    else:
        # Zoom: scale source larger, crop center
        zoom_w = int(inner_w * zoom)
        zoom_h = int(inner_h * zoom)
        holo_filter_parts.append(
            f"scale={zoom_w}:{zoom_h}:force_original_aspect_ratio=increase"
        )
        holo_filter_parts.append(
            f"crop={inner_w}:{inner_h}"
        )

    # Step 3: Cyan border
    holo_filter_parts.append(
        f"pad={holo_w}:{holo_h}:{border}:{border}:color=0x00e5ff"
    )

    # Step 4: Animation
    entry_type = animation.get("entry", "none")
    entry_dur = float(animation.get("entry_duration", 0.5))
    exit_type = animation.get("exit", "none")
    exit_dur = float(animation.get("exit_duration", 0.0))

    if entry_type == "fade_in" and entry_dur > 0:
        holo_filter_parts.append(
            f"fade=t=in:st=0:d={entry_dur:.2f}"
        )
    elif entry_type == "slide_up" and entry_dur > 0:
        # Slide up: start off-screen at bottom, move to final position
        # We handle this via animated overlay position instead of filter
        pass  # handled below in overlay

    if exit_type == "fade_out" and exit_dur > 0:
        exit_start = max(0, audio_dur - exit_dur)
        holo_filter_parts.append(
            f"fade=t=out:st={exit_start:.2f}:d={exit_dur:.2f}"
        )

    holo_vf = f"[1:v]{','.join(holo_filter_parts)}[holo]"

    # ── Build overlay with optional slide animation ──────────────────
    slide_dir = animation.get("slide_direction", "up")

    if entry_type == "slide_up" and entry_dur > 0:
        # Animate overlay Y position: slide from bottom of canvas to final Y
        ed = entry_dur
        if slide_dir == "up":
            overlay_expr = (
                f"overlay='{holo_x}':"
                f"if(lt(t\\,{ed:.2f})\\,"
                f"{h}-({h}-{holo_y})*t/{ed:.2f}\\,"
                f"{holo_y})"
            )
        elif slide_dir == "left":
            overlay_expr = (
                f"overlay='"
                f"if(lt(t\\,{ed:.2f})\\,"
                f"{w}-({w}-{holo_x})*t/{ed:.2f}\\,"
                f"{holo_x})':'{holo_y}'"
            )
        elif slide_dir == "right":
            overlay_expr = (
                f"overlay='"
                f"if(lt(t\\,{ed:.2f})\\,"
                f"-{holo_w}+({holo_x}+{holo_w})*t/{ed:.2f}\\,"
                f"{holo_x}'):'{holo_y}'"
            )
        else:
            overlay_expr = f"overlay={holo_x}:{holo_y}"
    elif entry_type == "fade_in" and entry_dur > 0:
        # fade_in is handled in filter, overlay position is static
        overlay_expr = f"overlay={holo_x}:{holo_y}"
    else:
        overlay_expr = f"overlay={holo_x}:{holo_y}"

    vf = (
        f"{base_vf};"
        f"{holo_vf};"
        f"[base][holo]{overlay_expr}{topic_f}[out]"
    )

    # Hologram clip loop flag
    holo_loop = ["-stream_loop", "-1"] if holo_dur < audio_dur else []

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        *holo_loop, "-i", holo_clip_path,
        "-i", audio_path,
        "-filter_complex", vf,
        "-map", "[out]", "-map", "2:a",
        "-t", f"{audio_dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        output_path,
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[CLS-Vid] ⚠️  Hologram composite failed: {r.stderr[-300:]}")
        return False
    return Path(output_path).exists() and Path(output_path).stat().st_size > 1000


# ── Segment builder ───────────────────────────────────────────────────────────

def _build_segment(clip_path, audio_path, audio_dur, bubble_png, output_path,
                    w, h, fps, topic="", bubble_cfg=None):
    bubble_cfg = bubble_cfg or {}
    has_clip = clip_path and Path(clip_path).exists() and _ffprobe_duration(clip_path) > 0.3
    if has_clip:
        cd = _ffprobe_duration(clip_path)
        loop = ["-stream_loop", "-1"] if cd < audio_dur else []
        inputs = [*loop, "-i", clip_path]
        scale = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                 f"crop={w}:{h},fps={fps}[base]")
    else:
        inputs = ["-f", "lavfi", "-i",
                   f"color=c=0x1a1a2e:s={w}x{h}:r={fps}:d={audio_dur:.3f}"]
        scale = "[0:v]copy[base]"

    topic_f = ""
    if topic:
        t_esc = topic.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
        topic_f = (f",drawtext=text='Topic\\: {t_esc}':"
                   f"fontcolor=white:fontsize=44:"
                   f"box=1:boxcolor=black@0.55:boxborderw=12:"
                   f"x=40:y=35:enable='gte(t,0)'")

    ox, oy = "0", "0"
    vf = f"{scale};[base][1:v]overlay={ox}:{oy}:format=auto{topic_f}[out]"

    if bubble_png is None:
        cmd = [
            "ffmpeg", "-y", *inputs,
            "-i", audio_path,
            "-filter_complex", scale.replace("[base]", "[out]"),
            "-map", "[out]", "-map", "1:a",
            "-t", f"{audio_dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            output_path
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.returncode == 0 and Path(output_path).exists()

    cmd = [
        "ffmpeg", "-y", *inputs,
        "-loop", "1", "-i", bubble_png,
        "-i", audio_path,
        "-filter_complex", vf,
        "-map", "[out]", "-map", "2:a",
        "-t", f"{audio_dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        output_path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"[CLS-Vid] ⚠️  ffmpeg: {r.stderr[-300:]}")
        return False
    return Path(output_path).exists() and Path(output_path).stat().st_size > 1000


# ── Entry ─────────────────────────────────────────────────────────────────────

def run(audio_path, script_path, output_path, topic, fmt, workspace,
         clip_config=None, clips_base="assets/classroom/clips", video_fps=30,
         watermark_enabled=True, watermark_text="@KidsThinkAI", watermark_opacity=60,
         bubble_cfg=None, hologram_cfg=None):
    """
    Render classroom video with bubble overlays and optional hologram panels.

    hologram_cfg : dict from profile "hologram" section
                   {
                     "enabled": true,
                     "mode": "floating_screen",
                     "position": "bottom_left",
                     "position_shorts": "center_bottom",
                     "scale_pct": 0.55,
                     "zoom": 1.0,
                     "clip_speed": 1.0,
                     "animation": {
                       "entry": "fade_in",
                       "entry_duration": 0.5,
                       "slide_direction": "up",
                       "exit": "none",
                       "exit_duration": 0.0
                     },
                     "sources": [...]
                   }
    """
    bubble_cfg   = bubble_cfg or {}
    hologram_cfg = hologram_cfg or {}
    ws = Path(workspace)
    out_path = Path(output_path)
    script = Path(script_path).read_text("utf-8")
    script = _expand_sections(script)

    if clip_config is None:
        cfg_path = Path("input/clips/croom.json")
        clip_config = json.loads(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}

    # ── Merge clips via global resolver ──────────────────────────────
    suffix = clip_config.get("_format_suffix", {}).get(fmt, "")
    clips_base_cfg = clip_config.get("_clips_base", clips_base)
    use_prefix = bool(clip_config.get("_folder_prefix", True))
    fmt_clips = common_resolver.merge_clips(clip_config, fmt, suffix)

    # ── Determine format early ───────────────────────────────────────
    is_shorts = "Short" in fmt
    width, height = (1080, 1920) if is_shorts else (1920, 1080)

    # ── Hologram service setup ───────────────────────────────────────
    holo_enabled = hologram_cfg.get("enabled", False)
    holo_clips_map: dict[str, str] = {}

    if holo_enabled:
        try:
            from cf2.core.services.hologram import HologramService
            holo_svc = HologramService(runtime_root=OUTPUT_ROOT)
            holo_svc.prepare(ws.parent.name, hologram_cfg)

            for src_cfg in hologram_cfg.get("sources", []):
                src_id = src_cfg.get("id", "")
                for seg_cfg in src_cfg.get("clips", src_cfg.get("segments", [])):
                    seg_id = seg_cfg.get("id", "")
                    resolved = holo_svc.resolve(ws.parent.name, src_id, seg_id)
                    if resolved and resolved.exists():
                        holo_clips_map[seg_id] = str(resolved)
                        print(f"[CLS-Vid] 👁️  Hologram clip ready: {seg_id} → {resolved.name}")

            if holo_clips_map:
                print(f"[CLS-Vid] 👁️  {len(holo_clips_map)} hologram clips available")
            else:
                print(f"[CLS-Vid] ⚠️  Hologram enabled but no clips resolved")
        except Exception as e:
            print(f"[CLS-Vid] ⚠️  Hologram service error: {e}")
            holo_enabled = False

    # ── Parse script lines (speakers + hologram tags) ───────────────
    lines = []

    for i, raw in enumerate(script.splitlines()):
        stripped = raw.strip()
        holo_match = _HOLO_RE.match(stripped)
        if holo_match:
            continue
        m = _SPEAKER_RE.match(stripped)
        if m:
            tag, name, text = m.group(1), m.group(2).strip(), m.group(3).strip()
            lines.append((tag.split("-")[0].upper(), name, text))

    if not lines:
        print("[CLS-Vid] ❌ No dialogue lines parsed")
        return

    # ── Determine which speaker lines get hologram overlay ──────────
    holo_line_map: dict[int, str] = {}
    active_holo = None
    line_idx = 0
    for raw_line in script.splitlines():
        stripped = raw_line.strip()
        holo_match = _HOLO_RE.match(stripped)
        if holo_match:
            holo_id = holo_match.group(1)
            if ":" in holo_id:
                parts = holo_id.split(":", 1)
                resolved_key = parts[1] if parts[1] in holo_clips_map else holo_id
            else:
                resolved_key = holo_id
            active_holo = resolved_key if resolved_key in holo_clips_map else None
            continue

        m = _SPEAKER_RE.match(stripped)
        if m:
            if active_holo:
                holo_line_map[line_idx] = active_holo
            line_idx += 1

    seg_audio_dir = ws / f"_cls_segs_{fmt}"
    seg_video_dir = ws / f"_cls_clips_{fmt}"
    bubble_dir    = ws / f"_cls_bubbles_{fmt}"
    seg_video_dir.mkdir(parents=True, exist_ok=True)
    bubble_dir.mkdir(parents=True, exist_ok=True)

    # ── Resolve clip sequences for each speaker tag ─────────────────
    resolved = {}
    for tag_base, _, _ in lines:
        if tag_base not in resolved:
            clip_seq = _resolve_clip_sequence(tag_base, fmt_clips, clips_base_cfg, use_prefix, fmt_suffix=suffix)
            resolved[tag_base] = clip_seq
            init_name = Path(clip_seq["init"]).name if clip_seq["init"] else "(solid)"
            loop_name = Path(clip_seq["loop"]).name if clip_seq["loop"] else "(solid)"
            trail_name = Path(clip_seq["trails"]).name if clip_seq["trails"] else "(solid)"
            if init_name == loop_name == trail_name:
                print(f"[CLS-Vid] 🎬 {tag_base:6s} → {init_name}")
            else:
                print(f"[CLS-Vid] 🎬 {tag_base:6s} → init={init_name} loop={loop_name} trail={trail_name}")

    # ── Read hologram config — all from config, zero hardcodes ──────
    if is_shorts:
        holo_position = hologram_cfg.get("position_shorts", "center_bottom")
    else:
        holo_position = hologram_cfg.get("position", "bottom_left")
    holo_scale_pct = float(hologram_cfg.get("scale_pct", 0.55))
    holo_zoom = float(hologram_cfg.get("zoom", 1.0))
    holo_clip_speed = float(hologram_cfg.get("clip_speed", 1.0))
    holo_animation = hologram_cfg.get("animation", {})

    print(f"[CLS-Vid] 🎬 Building {len(lines)} segments (hologram={'ON' if holo_enabled else 'OFF'})...")
    seg_videos = []

    for i, (tag, name, text) in enumerate(lines):
        audio_seg  = seg_audio_dir / f"seg_{i:04d}.mp3"
        video_seg  = seg_video_dir / f"clip_{i:04d}.mp4"
        bubble_png = bubble_dir / f"bubble_{i:04d}.png"

        if not audio_seg.exists():
            continue
        ad = _ffprobe_duration(str(audio_seg))
        if ad < 0.3:
            continue

        if video_seg.exists() and _ffprobe_duration(str(video_seg)) > 0.3:
            seg_videos.append(str(video_seg))
            continue

        # ── Decide: hologram overlay or bubble? ─────────────────────
        holo_seg_id = holo_line_map.get(i)
        holo_clip_path = holo_clips_map.get(holo_seg_id) if holo_seg_id else None

        if holo_clip_path and Path(holo_clip_path).exists():
            # ── Hologram segment: character bg + large hologram overlay ──
            clip_seq = resolved.get(tag, {"init": "", "loop": "", "trails": ""})
            bg_clip = clip_seq.get("loop") or clip_seq.get("init") or ""

            ok = _build_hologram_frame(
                bg_clip_path=bg_clip,
                holo_clip_path=holo_clip_path,
                audio_path=str(audio_seg),
                audio_dur=ad,
                output_path=str(video_seg),
                w=width, h=height, fps=video_fps,
                topic=topic if i == 0 else "",
                position=holo_position,
                scale_pct=holo_scale_pct,
                zoom=holo_zoom,
                clip_speed=holo_clip_speed,
                animation=holo_animation,
            )
            if ok:
                seg_videos.append(str(video_seg))
                pct = (i + 1) / len(lines) * 100
                print(f"[CLS-Vid] ✅ clip_{i:04d} [{tag}] 🖥️HOLO:{holo_seg_id} \"{text[:25]}\" ({ad:.1f}s) [{pct:.0f}%]")
            else:
                print(f"[CLS-Vid] ⚠️  Hologram failed, falling back to bubble for clip_{i:04d}")
                holo_clip_path = None

        if not holo_clip_path or not (Path(video_seg).exists() and Path(video_seg).stat().st_size > 1000):
            # ── Normal bubble segment ───────────────────────────────
            engine = (bubble_cfg or {}).get("engine", "pillow")
            if engine == "pillow":
                _make_bubble_png(str(bubble_png), tag, name, text, width, height,
                                  seed=i * 31 + hash(tag) % 1000, bubble_cfg=bubble_cfg)
            elif engine == "none":
                bubble_png = None

            clip_seq = resolved.get(tag, {"init": "", "loop": "", "trails": ""})
            clip = clip_seq.get("loop") or clip_seq.get("init") or ""

            ok = _build_segment(clip, str(audio_seg), ad, str(bubble_png),
                                 str(video_seg), width, height, video_fps,
                                 topic if i == 0 else "", bubble_cfg)
            if ok:
                seg_videos.append(str(video_seg))
                pct = (i + 1) / len(lines) * 100
                print(f"[CLS-Vid] ✅ clip_{i:04d} [{tag}] {name}: \"{text[:25]}\" ({ad:.1f}s) [{pct:.0f}%]")
            else:
                print(f"[CLS-Vid] ❌ clip_{i:04d} ({tag})")

    if not seg_videos:
        print("[CLS-Vid] ❌ No segments built")
        return

    # ── Bookend clips ───────────────────────────────────────────────
    def _build_bookend(key, dur=4.0, is_intro=False):
        clip_seq = _resolve_clip_sequence(key, fmt_clips, clips_base_cfg, use_prefix, fmt_suffix=suffix)
        clip = clip_seq.get("init") or clip_seq.get("loop") or ""
        if not clip or not Path(clip).exists():
            return None
        out = seg_video_dir / f"_bookend_{key}.mp4"
        if out.exists() and _ffprobe_duration(str(out)) > 0.3:
            return str(out)
        cd = _ffprobe_duration(clip)
        loop = ["-stream_loop", "-1"] if cd < dur else []
        cfg_block = fmt_clips.get(key, {})
        if isinstance(cfg_block, dict):
            subtext = cfg_block.get("subtext", "")
        else:
            subtext = ""
        text_filter = ""
        if subtext:
            t_esc = subtext.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
            text_filter = (f",drawtext=text='{t_esc}':"
                           f"fontcolor=white:fontsize=42:"
                           f"box=1:boxcolor=black@0.7:boxborderw=15:"
                           f"x=(w-text_w)/2:y=h*0.78:line_spacing=10")
        narration_path = None
        if subtext:
            try:
                from cf2.core.tts import synthesize, resolve_tier_for_unit
                narration_path = str(seg_video_dir / f"_bookend_{key}_audio.mp3")
                tier = resolve_tier_for_unit("Unit-Classroom")
                ok, _ = synthesize(text=subtext, output_path=narration_path,
                                    tier=tier, speaker_tag="T2",
                                    logger_fn=lambda m: None)
                if ok and Path(narration_path).exists():
                    nd = _ffprobe_duration(narration_path)
                    if nd > dur:
                        dur = nd + 0.5
                else:
                    narration_path = None
            except Exception:
                narration_path = None

        if narration_path:
            audio_input = ["-i", narration_path]
        else:
            audio_input = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

        cmd = [
            "ffmpeg", "-y", *loop, "-i", clip,
            *audio_input,
            "-filter_complex",
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={video_fps}{text_filter}[v]",
            "-map", "[v]", "-map", "1:a",
            "-t", f"{dur:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            str(out)
        ]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[CLS-Vid] ⚠️  bookend {key}: {r.stderr[-200:]}")
            return None
        return str(out)

    intro = _build_bookend("intro", dur=4.0, is_intro=True)
    sbs   = _build_bookend("sbs",   dur=4.0)
    end   = _build_bookend("end",   dur=3.0)

    final_seq = []
    if intro: final_seq.append(intro); print(f"[CLS-Vid] 🎬 +intro (4s)")
    final_seq.extend(seg_videos)
    if sbs:   final_seq.append(sbs); print(f"[CLS-Vid] 🎬 +sbs (4s)")
    if end:   final_seq.append(end); print(f"[CLS-Vid] 🎬 +end (3s)")
    seg_videos = final_seq

    concat_txt = ws / f"_cls_concat_{fmt}.txt"
    with open(concat_txt, "w") as f:
        for v in seg_videos:
            f.write(f"file '{v}'\n")

    print(f"[CLS-Vid] 🔗 Concat {len(seg_videos)} → {out_path.name}")
    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_txt), "-c", "copy", str(out_path)
    ], capture_output=True, text=True)

    if r.returncode != 0:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", str(out_path)
        ], capture_output=True)

    final_dur = _ffprobe_duration(str(out_path))
    holo_info = f" + {len(holo_clips_map)} hologram" if holo_clips_map else ""
    print(f"[CLS-Vid] ✅ {out_path.name} ({final_dur:.1f}s, {len(seg_videos)} segs{holo_info})")
