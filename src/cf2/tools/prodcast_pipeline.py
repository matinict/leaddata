"""
cf2/tools/prodcast_pipeline.py

Simple podcast pipeline builder.
"""

from typing import List, Dict, Any
import re

_SPEAKER_RE = re.compile(r"^\[(.+?)\]")


def build(
    fmt: str,
    script_lines: List[str],
    has_intro: bool,
    has_subscribe: bool,
    clip_config: dict,
) -> List[Dict[str, Any]]:

    pipeline: List[Dict[str, Any]] = []

    fmt_clips = {
        **clip_config.get("shared", {}),
        **clip_config.get(fmt, {}),
    }

    if has_intro:
        pipeline.append({
            "type": "video",
            "key": "intro",
            "role": "intro"
        })

    host_i = 0
    guest_i = 0

    for line in script_lines:

        m = _SPEAKER_RE.match(line.strip())

        if not m:
            continue

        tag = m.group(1).strip().lower()

        if tag == "host":
            key = f"h{host_i}"
            host_i += 1

        elif tag == "guest":
            key = f"g{guest_i}"
            guest_i += 1

        else:
            continue

        if key in fmt_clips:
            pipeline.append({
                "type": "block",
                "key": key,
                "role": tag,
            })

    if "outro" in fmt_clips:
        pipeline.append({
            "type": "video",
            "key": "outro",
            "role": "outro"
        })

    if has_subscribe:
        pipeline.append({
            "type": "video",
            "key": "sbs",
            "role": "subscribe"
        })

    return pipeline


def build_subtitle_map(
    pipeline: List[Dict[str, Any]],
    line_map: Dict[str, str],
    fmt_clips: Dict[str, Any],
) -> Dict[str, str]:

    subtitle_map = {}

    host_i = 0
    guest_i = 0

    for step in pipeline:

        key = step["key"]

        if step["type"] == "video":

            cfg = fmt_clips.get(key, {})

            subtitle_map[key] = (
                cfg.get("subtext", " ")
                if isinstance(cfg, dict)
                else " "
            )

            continue

        role = step["role"]

        if role == "host":
            map_key = f"HOST-{host_i}"
            host_i += 1

        elif role == "guest":
            map_key = f"GUEST-{guest_i}"
            guest_i += 1

        else:
            map_key = ""

        subtitle_map[key] = line_map.get(map_key, " ")

    return subtitle_map
