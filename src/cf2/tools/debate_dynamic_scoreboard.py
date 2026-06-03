"""
cf2/tools/debate_dynamic_scoreboard.py — Dynamic Scoreboard System

Updates scoreboard after each debate section

Migrated from: cf2/core/render/scoreboard/dynamic_scoreboard.py

NOTE: Currently not wired into unit_debate.py — superseded in practice by
debate_scoreboard_enhancer.py. Kept for future revival / reference.
Original description follows:

Dynamic Scoreboard System - Updates scoreboard after each debate section
Shows running scores throughout the debate instead of only at the end
"""

def generate_dynamic_scoreboards(debate_dir, md_suffix, fmt, fps, topic, sb_cfg, logger):
    """
    Generate incremental scoreboards showing running scores after each debate section
    Shows cumulative scores that grow as debate progresses
    """
    from pathlib import Path
    from cf2.tools.debate_score_extractor import resolve as extract_scores
    from cf2.tools.debate_score_renderer import render as render_scoreboard

    debate_dir = Path(debate_dir) if not isinstance(debate_dir, Path) else debate_dir

    scoreboards = {}
    stages = [
        "opening",
        "arg1",
        "arg2",
        "arg3",
        "judge_m",
        "judge_f",
        "judge_3",
        "final"
    ]

    for stage in stages:
        try:
            data = extract_scores(
                debate_dir, md_suffix,
                {
                    "debate_scoreboard_max_args": sb_cfg.get("max_args", 3),
                    "stage": stage,
                    "cumulative": True
                }
            )

            if not data:
                logger(f"⚠️ No data for stage: {stage}")
                continue

            board_path = debate_dir / f"scoreboard_{stage}_{fmt}.mp4"

            if not board_path.exists():
                logger(f"🎬 Rendering incremental {stage} → {board_path.name}")
                render_scoreboard(
                    data,
                    str(board_path),
                    fps,
                    4.0,
                    topic,
                    "Dynamic Intelligent",
                    1.0,
                    logger
                )
                scoreboards[stage] = str(board_path)
            else:
                logger(f"⏭️ {stage} scoreboard exists: {board_path.name}")
                scoreboards[stage] = str(board_path)

        except Exception as e:
            logger(f"❌ Error generating {stage} scoreboard: {e}")
            continue

    return scoreboards


def inject_dynamic_scoreboards_into_pipeline(pipeline, scoreboards, logger):
    insertions = [
        ("opening", "intro"),
        ("arg1", "c0"),
        ("arg2", "c1"),
        ("arg3", "c2"),
        ("judge_m", "aly"),
        ("judge_f", "judge_m"),
        ("judge_3", "judge_f"),
    ]

    for stage, after_key in insertions:
        if stage not in scoreboards:
            logger(f"⚠️ Skipping {stage}: scoreboard not generated")
            continue

        insert_pos = None
        for i, step in enumerate(pipeline):
            if step.get("key") == after_key:
                insert_pos = i + 1
                break

        if insert_pos is None:
            logger(f"⚠️ Could not find position for {stage} (after {after_key})")
            continue

        pipeline.insert(insert_pos, {
            "type": "video",
            "key": f"scoreboard_{stage}",
            "role": "score"
        })
        logger(f"✅ Inserted {stage} scoreboard after {after_key}")

    return pipeline


def inject_dynamic_scoreboards_into_clips(fmt_clips, scoreboards, debate_dir, fmt, logger):
    for stage, path in scoreboards.items():
        key = f"scoreboard_{stage}"
        fmt_clips[key] = {"path": path, "loops": [path]}
        logger(f"📎 Injected clip: {key}")

    return fmt_clips


def generate_dynamic_scoreboard_audio(scoreboards, block_dir, debate_config, ffmpeg, logger):
    import os
    from pathlib import Path

    audio_segments = []

    for stage, video_path in scoreboards.items():
        key = f"scoreboard_{stage}"
        audio_path = str(block_dir / f"{key}_audio.mp3")

        video_dur = ffmpeg.get_duration(video_path) or 4.0

        if ffmpeg.create_silent_mp3(audio_path, duration=video_dur):
            audio_segments.append((audio_path, video_dur, key))
            logger(f"🔇 Silent audio: {key} ({video_dur:.2f}s)")
        else:
            logger(f"❌ Failed to create audio for {key}")

    return audio_segments


def build_dynamic_scoreboard_subtitle_map(scoreboards, logger):
    subtitle_map = {}

    stage_labels = {
        "opening": "Opening: Scores So Far",
        "arg1": "Argument 1: Running Total",
        "arg2": "Argument 2: Running Total",
        "arg3": "Argument 3: Running Total",
        "judge_m": "Judge 1 - Male (Individual)",
        "judge_f": "Judge 2 - Female (Individual)",
        "judge_3": "Judge 3 - Neutral (Individual)",
        "final": "FINAL VERDICT & WINNER"
    }

    for stage in scoreboards.keys():
        key = f"scoreboard_{stage}"
        subtitle = stage_labels.get(stage, stage.upper())
        subtitle_map[key] = subtitle
        logger(f"📝 Subtitle: {key} → {subtitle}")

    return subtitle_map


def integrate_dynamic_scoreboards(
    pipeline,
    fmt_clips,
    debate_dir,
    md_suffix,
    fmt,
    fps,
    topic,
    sb_cfg,
    block_dir,
    debate_config,
    ffmpeg,
    logger
):
    from pathlib import Path
    
    debate_dir = Path(debate_dir) if not isinstance(debate_dir, Path) else debate_dir
    block_dir = Path(block_dir) if not isinstance(block_dir, Path) else block_dir

    logger("🎬 Starting dynamic scoreboard generation...")

    scoreboards = generate_dynamic_scoreboards(
        debate_dir, md_suffix, fmt, fps, topic, sb_cfg, logger
    )

    if not scoreboards:
        logger("⚠️ No dynamic scoreboards generated")
        return pipeline, fmt_clips, {}

    pipeline = inject_dynamic_scoreboards_into_pipeline(pipeline, scoreboards, logger)

    fmt_clips = inject_dynamic_scoreboards_into_clips(fmt_clips, scoreboards, debate_dir, fmt, logger)

    subtitle_map = build_dynamic_scoreboard_subtitle_map(scoreboards, logger)

    logger(f"✅ Dynamic scoreboards integrated: {len(scoreboards)} stages")

    return pipeline, fmt_clips, subtitle_map
