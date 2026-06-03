"""
smart_skip_utils.py
Shared smart-skip utilities for all video tools.
"""
import os
from typing import List, Optional

def check_final_debate_merge_exists(
    output_dir: str,
    channel: str,
    topic_slug: str,
    fmt: str,
    lang_suffix: str = ""
) -> Optional[str]:
    """
    Check if final debate merge video exists.
    Returns filepath if exists, None otherwise.
    Pattern: {channel}_Debate_{topic_slug}_{fmt}_{lang}.mp4
    """
    final_path = os.path.join(
        output_dir,
        f"{channel}_Debate_{topic_slug}_{fmt}_{lang_suffix}.mp4"
    )
    if os.path.exists(final_path):
        return final_path
    return None

def check_all_formats_merged(
    output_dir: str,
    channel: str,
    topic_slug: str,
    video_formats: List[str],
    lang_suffix: str = ""
) -> bool:
    """
    Check if ALL formats have final merged videos.
    Returns True only if ALL formats exist.
    """
    for fmt in video_formats:
        if not check_final_debate_merge_exists(
            output_dir, channel, topic_slug, fmt, lang_suffix
        ):
            return False
    return True
