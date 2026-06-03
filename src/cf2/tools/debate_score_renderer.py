"""
cf2/tools/debate_score_renderer.py — Scoreboard Video Renderer

Migrated from: cf2/core/render/scoreboard/score_renderer.py
Responsibility: Render an HD scoreboard .mp4 from ScoreData.
Pure PIL + ffmpeg; no TTS, no LLM, no config file I/O.
Rule alignment: R17, R22, R24, R31, R32
Animation plan: Forward → Hold → Reverse (applies to both full & teaser)
"""
from __future__ import annotations
import os, shutil, subprocess, tempfile, math
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

# Constants
FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
HD_SIZE = (1920, 1080)
BG_TOP, BG_BOTTOM = (8, 12, 24), (20, 28, 48)
GOLD, PRO_COLOR, CON_COLOR, DRAW_COLOR = (255, 205, 64), (86, 204, 242), (255, 99, 132), (200, 200, 210)
WHITE, GREY, PANEL = (240, 240, 245), (120, 130, 150), (18, 22, 36)

# Public API
def render(
    score_data: Dict[str, Any],  # ✅ Fixed line 24
    output_path: Path,
    fps: int,
    duration: float,
    title_primary: str = "FINAL SCOREBOARD",
    title_secondary: str = "Dynamic Intelligent",
    phase_limit: float = 1.0,
    logger=print,
) -> bool:
    if output_path.exists():
        logger(f"⏭️ Scoreboard exists: {output_path.name}")
        return True

    width, height = HD_SIZE
    total_frames = max(int(fps * duration), fps)
    tmpdir = Path(tempfile.mkdtemp(prefix="scoreboard_"))
    try:
        _render_frames(score_data, tmpdir, total_frames, width, height,
                       title_primary, title_secondary, phase_limit, logger)
        ok = _encode_frames_to_mp4(tmpdir, output_path, fps, logger)
        return ok and output_path.exists()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

def _render_frames(score, tmpdir, total_frames, w, h, p, s, phase_limit, logger):
    fonts = _load_fonts()
    rows = _build_rows(score)
    log_step = max(1, total_frames // 10)

    for fi in range(total_frames):
        raw_t = fi / max(total_frames - 1, 1)
        t = _remap_timeline(raw_t)  # Reverse logic
        draw_t = min(t, phase_limit)

        img = _draw_frame(draw_t, score, rows, fonts, w, h, p, s)
        img.save(tmpdir / f"frame_{fi:06d}.png", "PNG")
        if (fi + 1) % log_step == 0:
            logger(f"  Scoreboard rendering {(fi + 1) / total_frames * 100:.0f}%")

def _draw_frame(t, score, rows, fonts, w, h, p, s):
    img = _gradient_background(w, h)
    draw = ImageDraw.Draw(img, "RGBA")
    a_title = _ease(_phase_progress(t, 0.0, 0.25))
    # Only draw title if provided (can be disabled via config)
    if p:
        _draw_title(draw, p, s, fonts, w, a_title)
    _draw_column_headers(draw, fonts, w, h, a_title)

    # Check if rendering judge marks
    if "judge_marks" in score and score.get("judge_marks"):
        _draw_judge_marks(draw, score["judge_marks"], fonts, w, h, t)
    else:
        _draw_rows(draw, rows, fonts, w, h, t)

    a_totals = _ease(_phase_progress(t, 0.75, 0.90))
    _draw_totals(draw, score["totals"], fonts, w, h, a_totals)
    a_winner = _ease(_phase_progress(t, 0.90, 1.00))
    _draw_winner(draw, score["winner"], fonts, w, h, a_winner, t)
    return img

def _gradient_background(w, h):
    bg = Path("assets/img/debate_hd.png")
    if bg.exists():
        try:
            img = Image.open(bg).convert("RGB")
            return img.resize((w, h), Image.LANCZOS) if img.size != (w, h) else img
        except Exception: pass
    img = Image.new("RGB", (w, h), BG_TOP)
    px = img.load()
    for y in range(h):
        r = int(BG_TOP[0] + (BG_BOTTOM[0]-BG_TOP[0])*y/h)
        g = int(BG_TOP[1] + (BG_BOTTOM[1]-BG_TOP[1])*y/h)
        b = int(BG_TOP[2] + (BG_BOTTOM[2]-BG_TOP[2])*y/h)
        for x in range(w): px[x,y] = (r,g,b)
    return img

def _draw_title(draw, p, s, fonts, w, a):
    if a <= 0: return
    al = int(255 * max(0.0, min(1.0, a)))
    y = 60; max_w = int(w * 0.90); words, cur, lines = p.split(), "", []
    for wd in words:
        test = (cur + " " + wd).strip()
        if _text_width(draw, test, fonts["title"]) <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = wd
    if cur: lines.append(cur)
    for line in lines[:2]:
        _draw_centered(draw, line, fonts["title"], y=y, w=w, fill=(*GOLD, al)); y += 100
    _draw_centered(draw, s, fonts["subtitle"], y=y, w=w, fill=(*WHITE, al))

def _draw_column_headers(draw, fonts, w, h, a):
    if a <= 0: return
    al = int(255 * max(0.0, min(1.0, a)))
    y = 260
    draw.text((220, y), "PROPOSE", font=fonts["header"], fill=(*PRO_COLOR, al))
    tw = _text_width(draw, "OPPOSE", fonts["header"])
    draw.text((w - 220 - tw, y), "OPPOSE", font=fonts["header"], fill=(*CON_COLOR, al))

def _build_rows(score):
    rows = [{"label":"OPENING", "pro_title":score["opening"]["pro_title"], "con_title":score["opening"]["con_title"], "pro":score["opening"]["pro"], "con":score["opening"]["con"]}]
    for i, a in enumerate(score["args"], 1):
        rows.append({"label":f"ARG {i}", "pro_title":a["pro_title"], "con_title":a["con_title"], "pro":a["pro"], "con":a["con"]})
    return rows

def _draw_rows(draw, rows, fonts, w, h, t):
    n, row_h, y0 = len(rows), 110, 340
    pt = _phase_progress(t, 0.25, 0.75); per = 1.0 / max(n, 1)
    for i, row in enumerate(rows):
        rp = _clamp01((pt - i*per) / max(per, 0.001))
        y, alpha = y0 + i*row_h, _ease(rp)
        if alpha > 0: _draw_single_row(draw, row, fonts, w, y, rp, alpha)

def _draw_judge_marks(draw, judges, fonts, w, h, t):
    """Render individual judge marks instead of debate arguments"""
    n, row_h, y0 = len(judges), 110, 340
    pt = _phase_progress(t, 0.25, 0.75); per = 1.0 / max(n, 1)
    for i, judge in enumerate(judges):
        rp = _clamp01((pt - i*per) / max(per, 0.001))
        y, alpha = y0 + i*row_h, _ease(rp)
        if alpha > 0:
            row = {
                "label": judge.get("name", f"Judge {i+1}"),
                "pro_title": "",
                "con_title": "",
                "pro": judge.get("pro", 0),
                "con": judge.get("con", 0)
            }
            _draw_single_row(draw, row, fonts, w, y, rp, alpha)

def _draw_single_row(draw, row, fonts, w, y, prog, alpha):
    a = int(255 * max(0.0, min(1.0, alpha)))
    pro = int(row["pro"]*_ease(prog)); con = int(row["con"]*_ease(prog))
    draw._image.paste(Image.new("RGBA", (w-160,90), (*PANEL, int(180*alpha))), (80,y), Image.new("RGBA", (w-160,90), (*PANEL, int(180*alpha))))
    label, pt, ct = row["label"], row["pro_title"], row["con_title"]
    bw, ip = 140, 20
    _draw_centered_in_box(draw, f"[ {pro:>2} ]", fonts["score"], x=100, y=y+15, w=bw, fill=(*PRO_COLOR, a))
    _draw_centered_in_box(draw, f"[ {con:>2} ]", fonts["score"], x=w-100-bw, y=y+15, w=bw, fill=(*CON_COLOR, a))
    mxs, mxe = 100+bw+ip, w-100-bw-ip; mw = mxe-mxs; mc = mxs+mw//2
    sep, sw = "  —   ", _text_width(draw, "  —   ", fonts["row"]); sx = mc-sw//2; ty, hw = y+28, mw//2-sw//2-10
    lt = _truncate(draw, f"{label}: {pt}", fonts["row"], hw)
    draw.text((sx-_text_width(draw, lt, fonts["row"])-5, ty), lt, font=fonts["row"], fill=(*WHITE, a))
    draw.text((sx, ty), sep, font=fonts["row"], fill=(*GREY, a))
    rt = _truncate(draw, f"{ct} :{label}", fonts["row"], hw)
    draw.text((sx+sw+5, ty), rt, font=fonts["row"], fill=(*WHITE, a))

def _truncate(draw, text, font, mw):
    if _text_width(draw, text, font) <= mw: return text
    while text and _text_width(draw, text+"…", font) > mw: text = text[:-1]
    return text.rstrip()+"…" if text else " "

def _draw_totals(draw, totals, fonts, w, h, a):
    if a <= 0: return
    al = int(255 * max(0.0, min(1.0, a)))
    y = h-300
    draw.line([(160,y-20),(w-160,y-20)], fill=(*GREY, al), width=3)
    _draw_centered(draw, f"TOTAL   PROPOSE  {totals['pro']}   –   {totals['con']}  OPPOSE", fonts["totals"], y=y, w=w, fill=(*WHITE, al))

def _draw_winner(draw, winner, fonts, w, h, a, t):
    if a <= 0: return
    # Skip winner display if no winner is set (for running/intermediate scoreboards)
    if not winner or winner not in ("propose", "oppose", "draw"):
        return
    al = int(255 * max(0.0, min(1.0, a)))
    label = {"propose":"PROPOSE","oppose":"OPPOSE","draw":"DRAW"}.get(winner,"DRAW")
    color = {"propose":PRO_COLOR,"oppose":CON_COLOR,"draw":DRAW_COLOR}[winner]
    pulse = 1.0 + 0.08 * _pulse(t, 0.9, 1.0)
    _draw_centered(draw, f"🏆 WINNER: {label}", fonts["winner"], y=h-150, w=w, fill=(*color, al), scale=pulse)

def _load_fonts():
    sizes = {"title":92,"subtitle":46,"header":54,"row":38,"score":58,"totals":60,"winner":80}
    fonts = {}
    for n, sz in sizes.items():
        p = FONT_BOLD if n in {"title","header","score","totals","winner"} else FONT_REGULAR
        try: fonts[n] = ImageFont.truetype(p, sz)
        except OSError: fonts[n] = ImageFont.load_default()
    return fonts

def _draw_centered(draw, text, font, y, w, fill, scale=1.0):
    if not text: return
    tw = _text_width(draw, text, font); x = (w-tw)//2
    draw.text((x+2,y+2), text, font=font, fill=(0,0,0,min(180,fill[3])))
    draw.text((x,y), text, font=font, fill=fill)

def _draw_centered_in_box(draw, text, font, x, y, w, fill):
    draw.text((x+(w-_text_width(draw,text,font))//2, y), text, font=font, fill=fill)

def _text_width(draw, text, font):
    b = draw.textbbox((0,0), text, font=font); return b[2]-b[0]

def _phase_progress(t, a, b):
    if t <= a: return 0.0
    if t >= b: return 1.0
    return (t-a)/(b-a)

def _ease(x):
    x = _clamp01(x); return 4*x*x*x if x < 0.5 else 1 - pow(-2*x+2, 3)/2

def _pulse(t, a, b):
    if t < a or t > b: return 0.0
    return math.sin(((t-a)/max(b-a,0.001))*math.pi)

def _clamp01(x): return max(0.0, min(1.0, x))

def _remap_timeline(t: float) -> float:
    if t < 0.25: return t / 0.25
    elif t < 0.75: return 1.0
    else: return 1.0 - (t - 0.75) / 0.25

def _encode_frames_to_mp4(fd, out, fps, logger):
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg","-y","-framerate",str(fps),"-i",str(fd/"frame_%06d.png"),
           "-c:v","libx264","-preset","medium","-crf","18","-pix_fmt","yuv420p",str(out)]
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 and logger: logger(f"❌ ffmpeg encode failed: {r.stderr.decode()[:300]}")
    return r.returncode == 0
