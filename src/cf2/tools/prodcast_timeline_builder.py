"""
cf2/tools/prodcast_timeline_builder.py — Prodcast Timeline Builder
Pure function — no I/O, no debate dependencies.
"""
from typing import List, Tuple

TimelineEntry = Tuple[int, int, str] # (start_frame, end_frame, key)

def build(segments: List[Tuple], fps: int) -> List[TimelineEntry]:
    """
    Build timeline from segments.
    segments: [(speaker, duration, key),...]
    Returns: [(start_frame, end_frame, key),...]
    """
    timeline = []
    current_frame = 0

    for seg in segments:
        # Handle both 3-tuple and 4-tuple (ignore extra values)
        if len(seg) >= 3:
            speaker, duration, key = seg[0], seg[1], seg[2]
        else:
            continue

        if duration <= 0:
            continue

        frames = int(duration * fps)
        end_frame = current_frame + frames

        timeline.append((current_frame, end_frame, key))
        current_frame = end_frame

    return timeline
