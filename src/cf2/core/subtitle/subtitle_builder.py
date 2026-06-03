"""
core/subtitle/subtitle_builder.py — SRT & TXT Subtitle Generator

Responsibility: Generate .srt and .txt subtitle files from timed segments.
Pure file writing — no rendering, no audio ops.
"""
from pathlib import Path
from typing import List, Tuple, Dict, Optional


# Segment = (path_or_None, duration_seconds, key)
Segment = Tuple[Optional[str], float, str]


def _format_srt_time(seconds: float) -> str:
    """Convert float seconds → SRT timestamp HH:MM:SS,mmm."""
    ms  = int((seconds % 1) * 1000)
    s   = int(seconds) % 60
    m   = (int(seconds) // 60) % 60
    h   = int(seconds) // 3600
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(
    segments: List[Segment],
    subtitle_map: Dict[str, str],
    output_path: str,
) -> bool:
    """
    Write an .srt file from audio segments + subtitle text map.

    Args:
        segments     : ordered list of (path, duration, key) — same order as timeline
        subtitle_map : key → subtitle text
        output_path  : where to save .srt

    Returns True on success.
    """
    lines  = []
    idx    = 1
    cursor = 0.0

    for _, dur, key in segments:
        if dur <= 0:
            continue
        text = subtitle_map.get(key, "").strip()
        if text:
            start = _format_srt_time(cursor)
            end   = _format_srt_time(cursor + dur)
            lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
            idx += 1
        cursor += dur

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return True


def build_txt(
    segments: List[Segment],
    subtitle_map: Dict[str, str],
    output_path: str,
    include_timestamps: bool = False,
) -> bool:
    """
    Write a plain .txt transcript from audio segments + subtitle text map.

    Args:
        segments          : ordered list of (path, duration, key)
        subtitle_map      : key → subtitle text
        output_path       : where to save .txt
        include_timestamps: prepend HH:MM:SS timestamps to each line

    Returns True on success.
    """
    lines  = []
    cursor = 0.0

    for _, dur, key in segments:
        if dur <= 0:
            continue
        text = subtitle_map.get(key, "").strip()
        if text:
            if include_timestamps:
                ts = _format_srt_time(cursor).split(",")[0]   # HH:MM:SS only
                lines.append(f"[{ts}] {text}")
            else:
                lines.append(text)
        cursor += dur

    Path(output_path).write_text("\n\n".join(lines), encoding="utf-8")
    return True
