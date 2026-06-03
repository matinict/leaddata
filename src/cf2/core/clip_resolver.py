"""
cf2/core/clip_resolver.py — Global Common clip resolution for CF2 units.
Responsibility: Resolve clip paths, suffixes, and sequences.
Includes Classroom-style fallback: tries suffixed path first, then unsuffixed.
Pure logic — no LLM, no side effects, no Single unit,no hardcoded
Rule alignment: R4, R19, R28, R32
"""
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import os
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# Global Clip Merge + Suffix (shared by prodcast, classroom, debate)
# ============================================================================

def apply_suffix(entry: Any, suffix: str) -> Any:
    """
    Replace {suffix} placeholder in clip names.
    Works recursively on strings, dicts, and lists.
    Used by all units: prodcast, classroom, debate.

    Example:
        apply_suffix("H0{suffix}.mkv", "_s") -> "H0_s.mkv"
        apply_suffix({"init": ["T1{suffix}.mkv"]}, "_s") -> {"init": ["T1_s.mkv"]}
    """
    if isinstance(entry, str):
        return entry.replace("{suffix}", suffix)
    if isinstance(entry, dict):
        return {k: apply_suffix(v, suffix) for k, v in entry.items()}
    if isinstance(entry, list):
        return [apply_suffix(i, suffix) for i in entry]
    return entry


def merge_clips(clip_config: dict, fmt: str, suffix: str) -> dict:
    """
    Merge shared and format-specific clips, apply suffix, remove meta keys.
    Shared by all units: prodcast, classroom, debate.

    Steps:
      1. Start with shared clips
      2. Merge format-specific clips (handles _extend)
      3. Remove meta keys (_*)
      4. Remove null entries
      5. Apply {suffix} replacement to all clip values

    Args:
        clip_config: Full clip config dict (with _clips_base, shared, HD, Shorts, etc.)
        fmt: Format string ("HD", "Shorts", etc.)
        suffix: Suffix string ("", "_s", etc.) from _format_suffix

    Returns:
        Merged dict of clip entries with suffix applied.

    Example:
        merge_clips(config, "Shorts", "_s")
        -> {"T1": {"init": ["T1_s.mkv"], "loop": ["T1_s.mkv"], ...}, ...}
    """
    shared = clip_config.get("shared", {})
    fmt_specific = clip_config.get(fmt, {})

    # Handle _extend inheritance
    if isinstance(fmt_specific, dict) and fmt_specific.get("_extend") == "shared":
        merged = {**shared}
        for k, v in fmt_specific.items():
            if k != "_extend":
                merged[k] = v
    else:
        merged = {**shared, **fmt_specific}

    # Remove meta keys and null entries, apply suffix
    result = {}
    for key, val in merged.items():
        if key.startswith("_"):
            continue
        if val is None:
            continue
        # Apply {suffix} replacement to all values
        result[key] = apply_suffix(val, suffix)

    return result


# ============================================================================
# Intro / Subscribe Resolution
# ============================================================================

def resolve_intro(fmt: str, enabled: bool, workspace: Path,
                  clip_config: dict, fmt_suffix: str = "", logger=print) -> Tuple[str, bool]:
    """
    Resolve intro clip path from config.
    Returns (path, has_intro).
    Includes fallback to non-suffixed clip if suffixed one is missing.
    """
    if not enabled:
        return "", False

    # Check if format-specific or shared intro exists
    raw_cfg = clip_config.get(fmt, {})
    if "_extend" in raw_cfg:
        parent_cfg = clip_config.get(raw_cfg["_extend"], {})
        merged = {**parent_cfg, **raw_cfg}
    else:
        merged = raw_cfg

    intro_entry = merged.get("intro")
    if not intro_entry:
        return "", False

    # Extract path
    path = None
    if isinstance(intro_entry, dict):
        paths = intro_entry.get("paths", [])
        if paths:
            first = paths[0]
            if isinstance(first, str):
                path = first
            elif isinstance(first, dict):
                path = first.get("src")
    elif isinstance(intro_entry, str):
        path = intro_entry

    if path:
        # Apply suffix
        path = path.replace("{suffix}", fmt_suffix or "")

        # Resolve base path
        base = clip_config.get("_clips_base", "assets/clips")
        use_prefix = bool(clip_config.get("_folder_prefix", False))

        resolved_path = _resolve_clip_path_with_fallback(path, "intro", base, use_prefix, fmt_suffix)

        if resolved_path and Path(resolved_path).exists():
            if logger:
                logger(f"🎬 Resolved intro: {Path(resolved_path).name}")
            return resolved_path, True

    return "", False


def resolve_subscribe(fmt: str, clip_config: dict, fmt_suffix: str = "") -> bool:
    """Check if subscribe clip exists."""
    raw_cfg = clip_config.get(fmt, {})
    if "_extend" in raw_cfg:
        parent_cfg = clip_config.get(raw_cfg["_extend"], {})
        merged = {**parent_cfg, **raw_cfg}
    else:
        merged = raw_cfg
    return bool(merged.get("sbs") or merged.get("subscribe"))


# ============================================================================
# Clip Map Resolution
# ============================================================================

def resolve_clip_map(pipeline: List[Dict], fmt: str, fmt_clips: dict,
                     intro_path: str, clips_base: str, use_prefix: bool,
                     fmt_suffix: str = "") -> Dict[str, str]:
    """
    Resolve primary video path for each step in the pipeline.
    Includes fallback to non-suffixed clip if suffixed one is missing.
    """
    clip_map = {}
    for step in pipeline:
        key = step["key"]
        if key == "intro":
            clip_map[key] = intro_path
            continue
        entry = fmt_clips.get(key)
        if entry:
            path = _get_path_from_entry(entry, fmt_suffix)
            if path:
                resolved = _resolve_clip_path_with_fallback(path, key, clips_base, use_prefix, fmt_suffix)
                clip_map[key] = resolved or ""
    return clip_map


# ============================================================================
# Clip Sequence Resolution (init/loop/trails)
# ============================================================================

def resolve_clip_sequences(pipeline: List[Dict], fmt_clips: dict,
                           intro_path: str, clips_base: str,
                           use_prefix: bool, fmt_suffix: str = "") -> Dict[str, Dict]:
    """
    Resolve full sequence (paths, loops, tails) for the renderer.
    Returns a DICTIONARY keyed by clip key, matching what debate_video_renderer expects.
    Includes fallback to non-suffixed clip if suffixed one is missing.
    """
    sequences = {}
    for step in pipeline:
        key = step["key"]
        if key == "intro":
            if intro_path:
                sequences[key] = {"paths": [(intro_path, None)], "loops": [(intro_path, None)], "tail": []}
            continue
        entry = fmt_clips.get(key)
        if entry:
            seq = _build_sequence_with_fallback(entry, key, clips_base, use_prefix, fmt_suffix)
            if seq:
                sequences[key] = seq
    return sequences


# ============================================================================
# Entry Path Extraction
# ============================================================================

def _get_path_from_entry(entry: Any, fmt_suffix: str) -> Optional[str]:
    """Extract first string path from entry dict or string."""
    if isinstance(entry, str):
        return entry.replace("{suffix}", fmt_suffix or "")
    if isinstance(entry, dict):
        paths = entry.get("paths")
        if paths:
            first = paths[0]
            if isinstance(first, str):
                return first.replace("{suffix}", fmt_suffix or "")
            elif isinstance(first, dict):
                src = first.get("src", "")
                return src.replace("{suffix}", fmt_suffix or "")
    return None


# ============================================================================
# Path Resolution with Fallback
# ============================================================================

def _resolve_clip_path_with_fallback(path: str, key: str, clips_base: str,
                                     use_prefix: bool, fmt_suffix: str) -> Optional[str]:
    """
    Resolve clip path with Classroom-style fallback.
    1. Try suffixed path (e.g., h01_s.mkv)
    2. If missing and suffix exists, try unsuffixed path (e.g., h01.mkv)
    """
    if not path:
        return None

    # Try primary (suffixed) path
    resolved = _resolve_clip_path(path, key, clips_base, use_prefix)
    if resolved and Path(resolved).exists():
        return resolved

    # Fallback: strip suffix and retry
    if fmt_suffix and fmt_suffix in path:
        fallback_path = path.replace(fmt_suffix, "")
        resolved_fb = _resolve_clip_path(fallback_path, key, clips_base, use_prefix)
        if resolved_fb and Path(resolved_fb).exists():
            logger.info(f"[ClipResolver] Fallback: using {Path(resolved_fb).name} for key={key}")
            return resolved_fb

    return None


def _resolve_clip_path(path: str, key: str, clips_base: str, use_prefix: bool) -> Optional[str]:
    """Resolve relative path to absolute."""
    if not path:
        return None
    if os.path.isabs(path):
        return path
    if "/" in path:
        p = Path(path)
        return str(p.resolve())

    base = Path(clips_base).resolve()

    if use_prefix:
        # Look for folder ending with key
        for d in base.iterdir() if base.exists() else []:
            if d.is_dir() and d.name.endswith(key):
                candidate = d / path
                if candidate.exists():
                    return str(candidate)
        # If prefix used but no folder found, try flat
        candidate = base / path
        if candidate.exists():
            return str(candidate)
    else:
        candidate = base / path
        if candidate.exists():
            return str(candidate)

    return None


# ============================================================================
# Sequence Builder with Fallback
# ============================================================================

def _build_sequence_with_fallback(entry: Any, key: str, clips_base: str,
                                  use_prefix: bool, fmt_suffix: str) -> Optional[Dict]:
    """Build full sequence dict with fallback support."""
    paths = []
    loops = []
    tail = []

    def process_list(lst, target_list):
        if not isinstance(lst, list):
            return
        for item in lst:
            if isinstance(item, str):
                p = item.replace("{suffix}", fmt_suffix or "")
                resolved = _resolve_clip_path_with_fallback(p, key, clips_base, use_prefix, fmt_suffix)
                if resolved:
                    target_list.append((resolved, None))
            elif isinstance(item, dict):
                p = item.get("src", "").replace("{suffix}", fmt_suffix or "")
                frames = item.get("frames")
                resolved = _resolve_clip_path_with_fallback(p, key, clips_base, use_prefix, fmt_suffix)
                if resolved:
                    target_list.append((resolved, frames))

    if isinstance(entry, dict):
        process_list(entry.get("init", []) or entry.get("paths", []), paths)
        process_list(entry.get("loop", []) or entry.get("loops", []), loops)
        process_list(entry.get("trails", []) or entry.get("tail", []), tail)
    elif isinstance(entry, str):
        p = entry.replace("{suffix}", fmt_suffix or "")
        resolved = _resolve_clip_path_with_fallback(p, key, clips_base, use_prefix, fmt_suffix)
        if resolved:
            paths.append((resolved, None))

    if paths or loops or tail:
        return {"key": key, "paths": paths, "loops": loops, "tail": tail}
    return None


# ============================================================================
# Winner Clip Resolution (Debate)
# ============================================================================

def resolve_win_clip(verdict_path: Path, win_cfg: dict, fmt: str) -> Optional[str]:
    """
    Select winner clip based on verdict and resolve to absolute path.
    Args:
        verdict_path: Path to decide.md
        win_cfg: Config dict for 'win' key
        fmt: Video format string (e.g. "Shorts")
    Returns:
        Absolute path string to the clip
    """
    if not verdict_path.exists():
        return None

    # 1. Parse Verdict
    try:
        text = verdict_path.read_text(encoding="utf-8").upper()
        if "OPPOSITION WINS" in text:
            idx = 1  # cwin
        elif "DRAW" in text:
            idx = 2  # nwin
        else:
            idx = 0  # pwin (default)
    except Exception:
        idx = 0

    # 2. Get raw path
    paths = win_cfg.get("paths", [])
    if not paths or idx >= len(paths):
        return None
    raw_path = paths[idx]

    # 3. Handle Suffix
    suffix = "_s" if "Shorts" in fmt else ""
    if "{suffix}" in raw_path:
        raw_path = raw_path.replace("{suffix}", suffix)
    elif suffix and not raw_path.endswith(suffix + ".mkv"):
        raw_path = raw_path.replace(".mkv", suffix + ".mkv")

    # 4. Resolve Path (Defaults to assets/debate + 17_win search)
    clips_base = win_cfg.get("_clips_base", "assets/debate")
    use_prefix = win_cfg.get("_folder_prefix", True)

    if os.path.isabs(raw_path):
        return raw_path

    # Try to find in specific folder (e.g., 17_win)
    if use_prefix:
        base = Path(clips_base).resolve()
        if base.exists():
            for d in base.iterdir():
                if d.is_dir() and "win" in d.name:
                    candidate = d / raw_path
                    if candidate.exists():
                        return str(candidate)

    # Fallback to flat base
    candidate = Path(clips_base) / raw_path
    if candidate.exists():
        return str(candidate.resolve())

    return str(candidate)
