"""
cf2/tools/debate_pipeline.py — Debate Pipeline Structure Builder
Responsibility: Build the ordered execution plan (pipeline) for a debate video.
Pure function — no I/O, no side effects.
Rule Alignment: R28 (No Hardcoded Values), R30 (Config = Control)
"""
from typing import List, Dict, Any

def build(
    fmt: str,
    has_intro: bool,
    has_subscribe: bool,
    clip_config: dict,
    has_scoreboard: bool = False,
    debate_config: dict = None,
) -> List[Dict[str, Any]]:
    """
    Build debate pipeline with proper clip config inheritance.
    Dynamically determines round count from config['max_args'] or clip keys.
    """
    pipeline: List[Dict[str, Any]] = []

    # 1. Resolve _extend inheritance (R28: No hardcoded keys)
    raw_fmt_cfg = clip_config.get(fmt, {})
    if "_extend" in raw_fmt_cfg:
        parent_key = raw_fmt_cfg["_extend"]
        parent_cfg = clip_config.get(parent_key, {})
        # Merge: Parent keys first, then overwrite with format-specific keys
        fmt_clips = {**parent_cfg, **raw_fmt_cfg}
    else:
        fmt_clips = raw_fmt_cfg.copy()

    if has_intro:
        pipeline.append({"type": "video", "key": "intro", "role": "intro"})

    # ✅ FIX: Only add teaser if BOTH intro and scoreboard exist
    if has_scoreboard and has_intro:
        pipeline.append({"type": "video", "key": "score_teaser", "role": "teaser"})

    _add_video_key(pipeline, fmt_clips, ["ads1", "ad1"], "ad")

    # 🔥 CONFIG-DRIVEN ROUND CALCULATION (Rule 28)
    # Reads max_args from debate_3d_score config. Supports int or {"Shorts": N, "HD": M}
    sb_cfg = (debate_config or {}).get("debate_3d_score", {})
    max_args_cfg = sb_cfg.get("max_args")

    if isinstance(max_args_cfg, dict):
        max_round = max_args_cfg.get(fmt, 3)  # Fallback to 3 if format not specified
    elif isinstance(max_args_cfg, (int, float)):
        max_round = int(max_args_cfg)
    else:
        # Fallback: scan fmt_clips for 'p{index}' keys to determine max argument count
        max_round = 0
        for key in fmt_clips:
            if key.startswith("p") and len(key) > 1 and key[1:].isdigit():
                try:
                    idx = int(key[1:])
                    if idx > max_round:
                        max_round = idx
                except ValueError:
                    pass

    for i in range(max_round + 1):
        pipeline.append({"type": "block", "key": f"p{i}", "role": "propose"})
        pipeline.append({"type": "block", "key": f"c{i}", "role": "oppose"})

    # Judge panel — only included if the format actually has the clips configured.
    if "sum" in fmt_clips:
        pipeline.append({"type": "block", "key": "sum", "role": "decide"})

    aly_key = "aly" if "aly" in fmt_clips else ("anly" if "anly" in fmt_clips else None)
    if aly_key:
        pipeline.append({"type": "block", "key": aly_key, "role": "decide"})

    _add_video_key(pipeline, fmt_clips, ["ad2", "ads2"], "ad")

    # win is block type to generate audio, clip handles video
    pipeline.append({"type": "block", "key": "win", "role": "decide"})

    if has_scoreboard:
        pipeline.append({"type": "video", "key": "score", "role": "score"})

    if has_subscribe:
        sbs_key = "sbs" if "sbs" in fmt_clips else "subscribe"
        pipeline.append({"type": "video", "key": sbs_key, "role": "outro"})

    return pipeline

def _add_video_key(pipeline: List[Dict], fmt_clips: dict, candidates: List[str], role: str):
    """Add first available video key from candidates list."""
    for key in candidates:
        if fmt_clips.get(key):
            pipeline.append({"type": "video", "key": key, "role": role})
            return

def build_subtitle_map(pipeline: List[Dict], block_map: Dict, fmt_clips: dict) -> Dict[str, str]:
    """Build subtitle map from pipeline and block map."""
    subtitle_map = {}
    for step in pipeline:
        key = step["key"]
        role = step.get("role", "unknown")
        if step["type"] == "video":
            cfg_entry = fmt_clips.get(key)
            subtitle_map[key] = (
                cfg_entry.get("subtext", "  ") if isinstance(cfg_entry, dict) else "  "
            )
        else:
            subtitle_map[key] = block_map.get((role, key), "  ")
    return subtitle_map
