"""
cf2/tools/debate_timeline_builder.py — Frame Timeline Construction
Responsibility: Map audio segments to frame ranges.
Pure function — takes durations, returns frame spans.
"""
from typing import List, Tuple

Segment = Tuple[str, float, str]
TimelineEntry = Tuple[int, int, str]

def build(segments: List[Segment], fps: int) -> List[TimelineEntry]:
    """
    Convert ordered audio segments into a frame-indexed timeline.
    Args:
        segments : list of (path, duration, key) — path may be None for silent
        fps      : frames per second
    Returns:
        List of (start_frame, end_frame, key) sorted by start_frame.
    """
    valid = [(p, d, k) for p, d, k in segments if d > 0]
    if not valid:
        return []

    timeline: List[TimelineEntry] = []
    current_time = 0.0

    for _, dur, key in valid:
        start_f = int(current_time * fps)
        end_f   = int((current_time + dur) * fps)
        timeline.append((start_f, end_f, key))
        current_time += dur

    # Extend last entry to cover any rounding gap
    if timeline:
        total_frames = int(current_time * fps)
        last_start, last_end, last_key = timeline[-1]
        if last_end < total_frames:
            timeline[-1] = (last_start, total_frames, last_key)

    return timeline

def total_frames(segments: List[Segment], fps: int) -> int:
    """Total frame count from segment durations."""
    return int(sum(d for _, d, _ in segments if d > 0) * fps)

def lookup_key(timeline: List[TimelineEntry], frame_idx: int) -> str:
    """Return the active segment key for a given frame index."""
    for start, end, key in timeline:
        if start <= frame_idx < end:
            return key
    return timeline[-1][2] if timeline else ""
