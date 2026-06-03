"""
cf2/tools/classroom_pipeline.py — Classroom Pipeline Structure Builder
Responsibility: Build the ordered execution plan for a classroom video.
Pure function — no I/O, no side effects.
Mirrors: debate_pipeline.py
"""
from typing import List, Dict, Any
import re

_SPEAKER_RE = re.compile(r"^\[(\S+?)\]")
_HOLO_RE = re.compile(r"^\[HOLO:(\w+)\]", re.IGNORECASE)


def build(
    fmt: str,
    script_lines: List[str],
    has_intro: bool,
    has_subscribe: bool,
    clip_config: dict,
) -> List[Dict[str, Any]]:
    """
    Build classroom pipeline from script lines.
    Each dialogue line → one video step keyed by speaker tag (T1, T2, S1…S8).
    Hologram lines [HOLO:clip_id] → insert visual hologram clip.
    Structural steps (intro, sum, end, sbs) added around them.
    """
    pipeline: List[Dict[str, Any]] = []
    fmt_clips = {**clip_config.get("shared", {}), **clip_config.get(fmt, {})}

    if has_intro:
        pipeline.append({"type": "video", "key": "intro", "role": "intro"})

    for line in script_lines:
        stripped = line.strip()
        if not stripped:
            continue

        # --- Hologram insert ---
        holo_match = _HOLO_RE.match(stripped)
        if holo_match:
            clip_id = holo_match.group(1)
            pipeline.append({
                "type": "hologram",
                "key": clip_id,
                "role": "visual",
                "tag": "HOLO"
            })
            continue

        # --- Speaker dialogue ---
        m = _SPEAKER_RE.match(stripped)
        if not m:
            continue
        tag = m.group(1)
        tag_base = tag.split("-")[0].upper()
        if tag_base in fmt_clips:
            pipeline.append({"type": "block", "key": tag_base, "role": "speaker", "tag": tag})

    pipeline.append({"type": "block", "key": "sum", "role": "recap"})
    pipeline.append({"type": "video", "key": "end", "role": "end"})

    if has_subscribe:
        pipeline.append({"type": "video", "key": "sbs", "role": "outro"})

    return pipeline


def build_subtitle_map(
    pipeline: List[Dict[str, Any]],
    line_map: Dict[str, str],
    fmt_clips: Dict[str, Any],
) -> Dict[str, str]:
    """
    Map each pipeline step key → subtitle text.
    video steps use fmt_clips subtext.
    block steps use the actual dialogue line text.
    hologram steps get empty subtitle (visual only).
    """
    subtitle_map = {}
    for step in pipeline:
        key = step["key"]
        step_type = step["type"]
        if step_type == "video":
            cfg = fmt_clips.get(key, {})
            subtitle_map[key] = cfg.get("subtext", " ") if isinstance(cfg, dict) else " "
        elif step_type == "hologram":
            # No subtitles for hologram visuals (or use clip_id as placeholder)
            subtitle_map[key] = " "
        else:
            subtitle_map[key] = line_map.get(step.get("tag", key), " ")
    return subtitle_map
