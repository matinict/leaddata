"""
cf2/tools/debate_scoreboard_enhancer.py — Unified Scoreboard Pipeline Enhancer

Migrated from: cf2/core/render/scoreboard/scoreboard_enhancer.py

Target pipeline (7 scoreboards):
  intro → teaser → ad1 → p0+c0 → opening → p1+c1 → arg1 →
  p2+c2 → arg2 → p3+c3 → arg3 → sum → aly → ad2 → win →
  judges (all 3 on one board) → final → sbs
"""
from pathlib import Path
from typing import Dict, Any, List, Tuple
from cf2.tools.debate_score_extractor import resolve as extract_scores
from cf2.tools.debate_score_renderer import render as render_scoreboard


def enhance_pipeline(
    pipeline: List[Dict[str, Any]],
    debate_dir: Path,
    md_suffix: str,
    fmt: str,
    fps: int,
    topic: str,
    sb_cfg: Dict[str, Any],
    debate_config: Dict[str, Any],
    logger
) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, str]]:
    """Main orchestrator: generates scoreboards, injects into pipeline, returns clips & subtitles."""
    is_hd = "Shorts" not in fmt
    # Logic: skip if disabled, OR if hd_only=true and this is NOT HD (i.e., Shorts)
    if not sb_cfg.get("enabled") or (sb_cfg.get("hd_only", False) and not is_hd):
        logger(f"⚠️ Scoreboards skipped: enabled={sb_cfg.get('enabled')}, hd_only={sb_cfg.get('hd_only', False)}, fmt={fmt}")
        return pipeline, {}, {}

    fmt_clips = {}

    # Respect show_title config (default: True)
    show_title = sb_cfg.get("show_title", True)
    render_topic = topic if show_title else ""
    if not show_title:
        logger(f"🔕 Scoreboard title hidden (show_title=false)")

    # Load full score data once (source of truth)
    full_data = extract_scores(debate_dir, md_suffix, {"debate_scoreboard_max_args": sb_cfg.get("max_args", 3)})
    if not full_data:
        logger(f"⚠️ No score data available — skipping scoreboards")
        return pipeline, {}, {}

    # 1. Generate Final & Teaser
    fmt_clips.update(_render_main_boards(debate_dir, fmt, fps, render_topic, sb_cfg, full_data, logger))

    # 2. Generate progressive/judge boards (if enabled)
    if _is_dynamic_enabled_for_fmt(debate_config, fmt):
        fmt_clips.update(_render_progressive_boards(debate_dir, fmt, fps, render_topic, sb_cfg, full_data, logger))
        # Judges board is separately toggleable (default: true)
        if sb_cfg.get("judges_enabled", True):
            fmt_clips.update(_render_judge_boards(debate_dir, fmt, fps, render_topic, sb_cfg, full_data, logger))
        else:
            logger(f"🔕 Judges scoreboard disabled (judges_enabled=false)")
    else:
        logger(f"🔕 Dynamic scoreboards disabled for fmt={fmt}")

    # 3. Inject into Pipeline & Build Subtitles
    pipeline = _inject_into_pipeline(pipeline, fmt_clips, sb_cfg.get("teaser_after_intro", True), logger)
    subtitle_map = _build_subtitle_map(fmt_clips)

    return pipeline, fmt_clips, subtitle_map


def _is_dynamic_enabled_for_fmt(debate_config, fmt):
    """Check if dynamic_scoreboards_enabled is truthy for this format.

    Supports three config shapes:
      - Bool (global):     "dynamic_scoreboards_enabled": true
      - Dict (per-format): "dynamic_scoreboards_enabled": {"HD": true, "Shorts": false}
      - List (whitelist):  "dynamic_scoreboards_enabled": ["HD", "Shorts"]
    """
    val = debate_config.get("dynamic_scoreboards_enabled")
    if isinstance(val, dict):
        return bool(val.get(fmt, False))
    if isinstance(val, list):
        return fmt in val
    return bool(val)


# ── Main boards (final + teaser) ──────────────────────────────────────────

def _render_main_boards(debate_dir, fmt, fps, topic, sb_cfg, full_data, logger):
    boards = {}
    duration = float(sb_cfg.get("duration", 8.0))
    teaser_duration = float(sb_cfg.get("teaser_duration", duration * 0.5))
    sub_style = sb_cfg.get("subtitle", "Final Verdict")

    # Final Board — with winner
    _render_single("score", debate_dir / f"scoreboard_{fmt}.mp4",
                   full_data, fps, duration, topic, sub_style, 1.0, boards, logger)

    # Teaser — no winner
    teaser_data = {**full_data, "winner": ""}
    _render_single("score_teaser", debate_dir / f"scoreboard_teaser_{fmt}.mp4",
                   teaser_data, fps, teaser_duration, topic, "Preview", 0.75, boards, logger)
    return boards


# ── Progressive boards (opening + arg1..arg3) ────────────────────────────

def _render_progressive_boards(debate_dir, fmt, fps, topic, sb_cfg, full_data, logger):
    """
    Generate N+1 progressive scoreboards (opening + one per argument pair).
    N is dynamic, based on len(full_data["args"]).

    Example with 3 args:
      score_opening → after first P+C (just opening)
      score_arg1    → after arg1 pair (opening + arg1)
      score_arg2    → after arg2 pair (opening + arg1 + arg2)
      score_arg3    → after arg3 pair (opening + arg1 + arg2 + arg3)
    """
    boards = {}
    opening = full_data.get("opening", {})
    all_args = full_data.get("args", [])
    n = len(all_args)
    if n == 0:
        logger(f"⚠️ No args in score data — skipping progressive boards")
        return boards

    duration = float(sb_cfg.get("progressive_duration", sb_cfg.get("duration", 8.0) * 0.5))

    # Build stage list dynamically: opening, arg1, arg2, ..., argN
    stages = [("opening", 0)] + [(f"arg{i}", i) for i in range(1, n + 1)]

    for stage, n_args in stages:
        path = debate_dir / f"scoreboard_{stage}_{fmt}.mp4"
        sliced_args = all_args[:n_args]

        pro_total = opening.get("pro", 0) + sum(a.get("pro", 0) for a in sliced_args)
        con_total = opening.get("con", 0) + sum(a.get("con", 0) for a in sliced_args)

        stage_data = {
            "opening": opening,
            "args": sliced_args,
            "totals": {"pro": pro_total, "con": con_total},
            "winner": "",
            "source": full_data.get("source", "heuristic"),
        }

        subtitle = "Opening Scores" if stage == "opening" else f"After Argument {n_args}"
        _render_single(f"score_{stage}", path, stage_data, fps, duration, topic, subtitle, 1.0, boards, logger)

    return boards

    return boards


# ── Judge board (single combined board showing all 3 judges) ─────────────

def _render_judge_boards(debate_dir, fmt, fps, topic, sb_cfg, full_data, logger):
    """Generate ONE combined scoreboard showing all 3 judge marks together."""
    boards = {}
    judges = full_data.get("judges", [])
    if not judges:
        logger(f"⚠️ No judges data — skipping judges scoreboard")
        return boards

    path = debate_dir / f"scoreboard_judges_{fmt}.mp4"
    duration = float(sb_cfg.get("judges_duration", sb_cfg.get("duration", 8.0) * 0.75))

    # Sum of all judges' pro/con for the totals line
    pro_sum = sum(j.get("pro", 0) for j in judges)
    con_sum = sum(j.get("con", 0) for j in judges)

    judges_data = {
        "opening": full_data.get("opening", {}),
        "args": full_data.get("args", []),
        "totals": {"pro": pro_sum, "con": con_sum},
        "winner": "",
        "judge_marks": judges,  # renderer shows them as rows
        "source": full_data.get("source", "heuristic"),
    }

    _render_single("score_judges", path, judges_data, fps, duration, topic, "Individual Judge Marks", 1.0, boards, logger)
    return boards


# ── Render helper ─────────────────────────────────────────────────────────

def _render_single(key, path, data, fps, duration, topic, subtitle, phase_limit, boards, logger):
    if not data:
        return
    if path.exists():
        boards[key] = {"paths": [str(path)], "loops": [str(path)]}
        return
    if render_scoreboard(data, path, fps, duration, topic, subtitle, phase_limit, logger):
        boards[key] = {"paths": [str(path)], "loops": [str(path)]}
        logger(f"🎬 Rendered {key} → {path.name}")


# ── Pipeline injection ────────────────────────────────────────────────────

def _inject_into_pipeline(pipeline, fmt_clips, teaser_after_intro, logger):
    """
    Dynamically inject scoreboards based on what's in fmt_clips and what
    anchors exist in the pipeline.

    Target order:
      intro → [teaser] → ... → p0+c0 → [opening] → p1+c1 → [arg1] →
      p2+c2 → [arg2] → ... pN+cN → [argN] → ... → win → [judges] → [score] → sbs

    Works for any number of args (auto-detects c0..cN from pipeline).
    """
    # Remove any pre-existing final score step so we can reposition correctly
    pipeline = [s for s in pipeline if s.get("key") != "score"]

    # Auto-detect CON anchor keys from the pipeline (c0, c1, c2, ...)
    con_keys = sorted(
        [s["key"] for s in pipeline if s.get("key", "").startswith("c") and s["key"][1:].isdigit()],
        key=lambda k: int(k[1:])
    )

    # (clip_key, anchor_key) — insert clip_key right after anchor_key
    insertions = []

    if teaser_after_intro and "score_teaser" in fmt_clips:
        insertions.append(("score_teaser", "intro"))

    # 🔧 Opening → after SECOND CON (c1, which is oppose argument 1)
    # FIXED: Changed from con_keys[0] to con_keys[1] so opening score appears AFTER argument 1
    if "score_opening" in fmt_clips and len(con_keys) > 1:
        insertions.append(("score_opening", con_keys[1]))
    elif "score_opening" in fmt_clips and con_keys:
        # Fallback: if only one argument exists, put after first one
        insertions.append(("score_opening", con_keys[0] if len(con_keys) == 1 else con_keys[-1]))

    # arg1 → after c1, arg2 → after c2, etc.
    # (The progressive boards are numbered 1..N matching c1..cN)
    for i, con_key in enumerate(con_keys):
        if i == 0:
            continue  # c0 is used by opening above
        arg_clip = f"score_arg{i}"
        if arg_clip in fmt_clips:
            insertions.append((arg_clip, con_key))

    # Judges board after 'win'
    if "score_judges" in fmt_clips:
        insertions.append(("score_judges", "win"))

    # Final scoreboard — chain fallback: after judges, or win if no judges
    if "score" in fmt_clips:
        if "score_judges" in fmt_clips:
            insertions.append(("score", "score_judges"))
        else:
            insertions.append(("score", "win"))
    else:
        logger(f"⚠️ Final 'score' clip not in fmt_clips! Keys present: {list(fmt_clips.keys())}")

    # Apply in order (each new insertion becomes a valid anchor for later ones)
    for clip_key, anchor_key in insertions:
        anchor_pos = next((i for i, s in enumerate(pipeline) if s.get("key") == anchor_key), None)
        if anchor_pos is None:
            logger(f"⚠️ Anchor '{anchor_key}' not found — skipping {clip_key}")
            continue
        pipeline.insert(anchor_pos + 1, {"type": "video", "key": clip_key, "role": "score"})
        logger(f"✅ Inserted {clip_key} after {anchor_key}")

    return pipeline


# ── Subtitle map ──────────────────────────────────────────────────────────

def _build_subtitle_map(clip_map):
    """Build subtitle labels for all scoreboard keys. Dynamic for any argN."""
    static_labels = {
        "score_teaser":  "Scoreboard Preview",
        "score_opening": "Opening Scores",
        "score_judges":  "Individual Judge Marks",
        "score":         "FINAL VERDICT & WINNER",
    }
    result = {}
    for k in clip_map:
        if k in static_labels:
            result[k] = static_labels[k]
        elif k.startswith("score_arg") and k[9:].isdigit():
            result[k] = f"After Argument {k[9:]}: Running Total"
        else:
            result[k] = k.replace("_", " ").title()
    return result
