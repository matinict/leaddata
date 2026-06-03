"""
unit_prodcast.py — Podcast Generation Pipeline (CF2 Compliant)

Architecture:
unit_prodcast.py (Router)
├─▶src/cf2/core/clip_resolver.py
├─▶src/cf2/core/services/tts_service.py
├─▶src/cf2/core/services/ffmpeg_service.py
├─▶ prodcast_pipeline
├─▶ prodcast_publish_helper
├─▶ prodcast_script_generator
├─▶ prodcast_timeline_builder
└─▶ prodcast_video_generator
└─▶ prodcast_voice_generator

Rule alignment:
R3, R4, R6, R7, R19, R24, R25, R28, R30, R32, R33, R39
"""

from __future__ import annotations

import logging
import re
import subprocess

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from crewai import Crew, Process

from cf2.meta import (
    load_meta,
    mark_unit,
    save_meta,
    should_skip,
)

from cf2.crews.crew import CF2Crew
from cf2.tools import prodcast_pipeline


logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

class RunStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


MIN_SCRIPT_BYTES = 200
MIN_SCRIPT_M_BYTES = 150
MIN_AUDIO_BYTES = 1_000
MIN_VIDEO_BYTES = 500_000
MIN_INTRO_BYTES = 500

MINI_TARGET_CHARS = 2400
MINI_FLOOR_CHARS = 1200
MINI_CEILING_CHARS = 2700

DIALOGUE_LINE_RE = re.compile(
    r"^(Host|Guest):\s",
    re.MULTILINE,
)


DEFAULTS: dict[str, Any] = {
    "voice_host": "en-US-RogerNeural",
    "voice_guest": "en-US-AriaNeural",
    "tts_engine": "edge-tts",
    "audio_speed": 1.0,
    "pause_ms": 350,
    "intro_text": "Welcome to the Podcast.",
    "outro_text": "Thanks for tuning in.",
    "format": "host_guest",
    "min_exchanges": 12,
    "max_exchanges": 18,
    "channel": "PlayOwnAi",
    "max_script_chars": 3000,
    "mini_max_chars": MINI_TARGET_CHARS,
    "mini_outro": "That's a wrap — full episode in the description.",
}


# ============================================================================
# Paths
# ============================================================================

@dataclass(frozen=True)
class Paths:

    workspace: Path
    podcast_dir: Path

    script: Path
    script_m: Path

    audio: Path
    audio_m: Path

    video: Path
    video_m: Path

    @classmethod
    def from_workspace(
        cls,
        workspace: Path,
        channel: str,
        slug: str,
    ) -> "Paths":

        ws = workspace.resolve()

        pd = (ws / "podcast").resolve()

        safe_channel = (
            re.sub(r"[^a-zA-Z0-9_-]", "", channel)
            or "Channel"
        )

        return cls(
            workspace=ws,
            podcast_dir=pd,

            script=pd / "script.md",
            script_m=pd / "script-m.md",

            audio=pd / "audio.mp3",
            audio_m=pd / "audio-m.mp3",

            video=pd / f"{safe_channel}_{slug}_HD.mp4",
            video_m=pd / f"{safe_channel}_{slug}_Shorts.mp4",
        )


# ============================================================================
# Intro Resolver (Rule 30 — Config Controls Logic)
# ============================================================================

def _resolve_intro(inputs: dict[str, Any]) -> Path | None:
    """
    Resolve intro file path from config.
    Returns Path if valid file found, None otherwise.
    """
    if not inputs.get("prodcast_intro_enabled", False):
        return None

    raw = inputs.get("prodcast_intro_file", "")
    if not raw or not str(raw).strip():
        logger.warning(
            "Unit-Prodcast: intro enabled but no file specified — skipping intro"
        )
        return None

    intro_path = Path(raw)

    if not intro_path.exists():
        logger.warning(
            "Unit-Prodcast: intro file not found: %s — skipping intro",
            intro_path,
        )
        return None

    if intro_path.stat().st_size < MIN_INTRO_BYTES:
        logger.warning(
            "Unit-Prodcast: intro file too small (%d bytes) — skipping intro",
            intro_path.stat().st_size,
        )
        return None

    return intro_path


# ============================================================================
# Public Entry — Lock-Free (Rule 25.7)
# ============================================================================

def run(
    topic: str,
    workspace: Path,
    inputs: dict[str, Any],
    force: bool = False,
) -> str:

    # ── Disabled check (Rule 3.4) ─────────────────────────────────────────
    if not inputs.get("Unit-Prodcast", False):
        logger.info("Unit-Prodcast: disabled — skipping.")
        return "disabled"

    # ── Empty topic guard ─────────────────────────────────────────────────
    if not topic:
        logger.error("Unit-Prodcast: empty topic")
        return RunStatus.FAILED

    # ── Smart skip via meta (Rule 24) ─────────────────────────────────────
    if should_skip(workspace, "Unit-Prodcast", force, inputs=inputs):
        logger.info("Unit-Prodcast: already done (meta verified) — skipping.")
        return "done"

    # ── Resolve audio/video flags (Rule 30) ───────────────────────────────
    audio_on = inputs.get("prodcast_audio_enabled", True)
    video_on = inputs.get("prodcast_video_enabled", False)

    need_audio = audio_on or video_on
    need_mini = video_on or ("Shorts" in inputs.get("video_formats", []))

    # ── Resolve intro ─────────────────────────────────────────────────────
    intro_path = _resolve_intro(inputs)
    has_intro = intro_path is not None

    _log_mode(audio_on, video_on, has_intro, intro_path)

    # ── Resolve paths ─────────────────────────────────────────────────────
    channel = inputs.get(
        "channel",
        DEFAULTS["channel"],
    )

    slug = inputs.get(
        "topic_slug",
        inputs.get("filename", workspace.name),
    )

    paths = Paths.from_workspace(
        workspace=workspace,
        channel=channel,
        slug=slug,
    )

    paths.podcast_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ── File-based cache check (fast path before heavy work) ──────────────
    if (
        not force
        and _is_fully_cached(paths, audio_on, video_on)
    ):
        logger.info("Unit-Prodcast: cached — skipping")
        mark_unit(workspace, "Unit-Prodcast", "done", inputs)
        return RunStatus.DONE

    # ── Execute stages (NO LOCK CODE — executor.py holds the lock) ────────
    try:

        # =========================================================
        # Script (always needed if anything runs)
        # =========================================================

        if (
            _run_script_stage(
                topic=topic,
                paths=paths,
                inputs=inputs,
                force=force,
            )
            == RunStatus.FAILED
        ):
            return _record_failure(
                workspace,
                "script generation failed",
                inputs,
            )

        # =========================================================
        # Mini Script (only if Shorts needed)
        # =========================================================

        if need_mini:
            if (
                _run_script_mini_stage(
                    paths=paths,
                    inputs=inputs,
                    force=force,
                )
                == RunStatus.FAILED
            ):
                return _record_failure(
                    workspace,
                    "mini script failed",
                    inputs,
                )

        # =========================================================
        # Audio HD
        # =========================================================

        if need_audio:
            if (
                _run_voice_stage(
                    script_path=paths.script,
                    audio_path=paths.audio,
                    inputs=inputs,
                    force=force,
                    fmt="HD",
                )
                == RunStatus.FAILED
            ):
                return _record_failure(
                    workspace,
                    "audio HD failed",
                    inputs,
                )

            # Prepend intro to HD audio only (not Shorts)
            if has_intro:
                _run_intro_stage(
                    intro_path=intro_path,
                    audio_path=paths.audio,
                    label="HD",
                )

        # =========================================================
        # Audio Shorts
        # =========================================================

        if need_mini:
            if (
                _run_voice_stage(
                    script_path=paths.script_m,
                    audio_path=paths.audio_m,
                    inputs=inputs,
                    force=force,
                    fmt="Shorts",
                )
                == RunStatus.FAILED
            ):
                logger.warning("Unit-Prodcast: Shorts audio failed — continuing")

        # =========================================================
        # Video (only if enabled)
        # =========================================================

        if video_on:

            video_formats = inputs.get(
                "video_formats",
                ["Shorts"],
            )

            for fmt in video_formats:

                audio_src = (
                    paths.audio_m
                    if fmt == "Shorts"
                    else paths.audio
                )

                output_dst = (
                    paths.video_m
                    if fmt == "Shorts"
                    else paths.video
                )

                _run_video_stage(
                    audio_path=audio_src,
                    output_path=output_dst,
                    fmt=fmt,
                    topic=topic,
                    inputs=inputs,
                    force=force,
                )
        else:
            logger.info(
                "Unit-Prodcast: video skipped (prodcast_video_enabled=false)"
            )

        # ── Mark done (Rule 23 — meta.json is the brain) ─────────────────
        mark_unit(workspace, "Unit-Prodcast", "done", inputs)

        logger.info("Unit-Prodcast: DONE")

        return RunStatus.DONE

    except Exception as exc:

        logger.exception(
            "Unit-Prodcast: fatal — %s",
            exc,
        )

        return _record_failure(
            workspace,
            str(exc),
            inputs,
        )


# ============================================================================
# Mode Logger
# ============================================================================

def _log_mode(
    audio_on: bool,
    video_on: bool,
    has_intro: bool,
    intro_path: Path | None,
) -> None:
    """Log the execution mode."""
    parts = []

    if audio_on and video_on:
        parts.append("AUDIO + VIDEO")
    elif audio_on:
        parts.append("AUDIO ONLY")
    elif video_on:
        parts.append("VIDEO ONLY (audio as intermediate)")
    else:
        parts.append("NOTHING (both disabled)")

    if has_intro:
        parts.append(f"INTRO: {intro_path.name}")
    else:
        parts.append("INTRO: off")

    logger.info("Unit-Prodcast: mode = %s", " | ".join(parts))


# ============================================================================
# Intro Prepend Stage
# ============================================================================

def _run_intro_stage(
    intro_path: Path,
    audio_path: Path,
    label: str,
) -> bool:
    """
    Prepend intro audio file before the main podcast audio.
    Uses ffmpeg concat filter for safe re-encoding.
    Writes result back to the same audio_path (in-place replace via temp file).
    """
    if not audio_path.exists():
        logger.warning("Unit-Prodcast: intro skip [%s] — audio missing", label)
        return False

    intro_dur = _get_duration(str(intro_path))
    main_dur = _get_duration(str(audio_path))

    logger.info(
        "Unit-Prodcast: prepending intro [%s] (%.1fs) + main (%.1fs)",
        label,
        intro_dur,
        main_dur,
    )

    # Use temp file to avoid corruption on failure
    tmp_path = audio_path.with_suffix(".tmp.mp3")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(intro_path),
        "-i", str(audio_path),
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[outa]",
        "-map", "[outa]",
        "-c:a", "libmp3lame",
        "-b:a", "128k",
        str(tmp_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode != 0:
            last = ""
            if result.stderr:
                lines = [l for l in result.stderr.strip().splitlines() if l.strip()]
                last = lines[-1] if lines else "unknown"
            logger.error(
                "Unit-Prodcast: intro concat failed [%s] — %s",
                label,
                last,
            )
            tmp_path.unlink(missing_ok=True)
            return False

        # Replace original with temp
        tmp_path.replace(audio_path)

        final_dur = _get_duration(str(audio_path))
        final_kb = audio_path.stat().st_size // 1024

        logger.info(
            "Unit-Prodcast: intro applied [%s] → %.1fs total (%d KB)",
            label,
            final_dur,
            final_kb,
        )
        return True

    except subprocess.TimeoutExpired:
        logger.error("Unit-Prodcast: intro concat timed out [%s]", label)
        tmp_path.unlink(missing_ok=True)
        return False

    except Exception as exc:
        logger.error("Unit-Prodcast: intro concat error [%s] — %s", label, exc)
        tmp_path.unlink(missing_ok=True)
        return False


def _get_duration(file_path: str) -> float:
    """Get audio duration using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            file_path,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


# ============================================================================
# Script Generation
# ============================================================================

def _run_script_stage(
    topic: str,
    paths: Paths,
    inputs: dict[str, Any],
    force: bool,
) -> RunStatus:

    if (
        not force
        and _is_valid_file(
            paths.script,
            MIN_SCRIPT_BYTES,
        )
    ):

        logger.info(
            "Unit-Prodcast: script cached"
        )

        return RunStatus.DONE

    try:

        factory = CF2Crew(inputs=inputs)

        scriptwriter = (
            factory.prodcast_scriptwriter()
        )

        task = (
            factory.prodcast_write_script()
        )

        crew = Crew(
            agents=[scriptwriter],
            tasks=[task],
            process=Process.sequential,
            verbose=inputs.get(
                "verbose",
                False,
            ),
        )

        result = crew.kickoff(
            inputs=_build_script_inputs(
                topic,
                paths,
                inputs,
            )
        )

        text = _extract_text(result)

        if (
            not text
            or len(text) < MIN_SCRIPT_BYTES
        ):

            return RunStatus.FAILED

        paths.script.write_text(
            text,
            encoding="utf-8",
        )

        logger.info(
            "Unit-Prodcast: script.md ready"
        )

        return RunStatus.DONE

    except Exception as exc:

        logger.exception(
            "Unit-Prodcast: script failed — %s",
            exc,
        )

        return RunStatus.FAILED


def _build_script_inputs(
    topic: str,
    paths: Paths,
    inputs: dict[str, Any],
) -> dict[str, Any]:

    return {
        **inputs,

        "topic": topic,
        "workspace": str(paths.workspace),
        "podcast_dir": str(paths.podcast_dir),

        "format": inputs.get(
            "prodcast_format",
            DEFAULTS["format"],
        ),

        "intro_text": inputs.get(
            "prodcast_intro_text",
            DEFAULTS["intro_text"],
        ),

        "outro_text": inputs.get(
            "prodcast_outro_text",
            DEFAULTS["outro_text"],
        ),

        "min_exchanges": inputs.get(
            "prodcast_min_exchanges",
            DEFAULTS["min_exchanges"],
        ),

        "max_exchanges": inputs.get(
            "prodcast_max_exchanges",
            DEFAULTS["max_exchanges"],
        ),

        "voice_host": inputs.get(
            "prodcast_voice_host",
            DEFAULTS["voice_host"],
        ),

        "voice_guest": inputs.get(
            "prodcast_voice_guest",
            DEFAULTS["voice_guest"],
        ),
    }


# ============================================================================
# Mini Script
# ============================================================================

def _run_script_mini_stage(
    paths: Paths,
    inputs: dict[str, Any],
    force: bool,
) -> RunStatus:

    if (
        not force
        and _is_valid_file(
            paths.script_m,
            MIN_SCRIPT_M_BYTES,
        )
    ):
        return RunStatus.DONE

    if not paths.script.exists():
        return RunStatus.FAILED

    text = paths.script.read_text(
        encoding="utf-8",
    )

    budget = _resolve_mini_budget(inputs)

    mini = _compress_to_mini(
        full_text=text,
        max_chars=budget,
        mini_outro=inputs.get(
            "prodcast_mini_outro",
            DEFAULTS["mini_outro"],
        ),
    )

    paths.script_m.write_text(
        mini,
        encoding="utf-8",
    )

    return RunStatus.DONE


def _resolve_mini_budget(
    inputs: dict[str, Any]
) -> int:

    raw = inputs.get(
        "prodcast_mini_max_chars",
        DEFAULTS["mini_max_chars"],
    )

    try:
        val = int(raw)
    except Exception:
        val = MINI_TARGET_CHARS

    return max(
        MINI_FLOOR_CHARS,
        min(val, MINI_CEILING_CHARS),
    )


def _compress_to_mini(
    full_text: str,
    max_chars: int,
    mini_outro: str,
) -> str:

    if len(full_text) <= max_chars:
        return full_text

    turns = _extract_turns(full_text)

    out = []

    used = 0

    for turn in turns:

        size = len(turn)

        if used + size > max_chars:
            break

        out.append(turn)

        used += size

    out.append(
        f"Host: {mini_outro}"
    )

    return "\n\n".join(out)


def _extract_turns(
    text: str
) -> list[str]:

    matches = list(
        DIALOGUE_LINE_RE.finditer(text)
    )

    if not matches:
        return []

    turns = []

    for i, match in enumerate(matches):

        end = (
            matches[i + 1].start()
            if i + 1 < len(matches)
            else len(text)
        )

        turns.append(
            text[
                match.start():end
            ].strip()
        )

    return turns


# ============================================================================
# Voice Generation
# ============================================================================

def _run_voice_stage(
    script_path: Path,
    audio_path: Path,
    inputs: dict[str, Any],
    force: bool,
    fmt: str,
) -> RunStatus:

    if (
        not force
        and _is_valid_file(
            audio_path,
            MIN_AUDIO_BYTES,
        )
    ):
        return RunStatus.DONE

    if not script_path.exists():
        return RunStatus.FAILED

    try:

        from cf2.tools.prodcast_voice_generator import (
            run as voice_tool,
        )

        voice_tool(
            script_path=str(script_path),
            output_path=str(audio_path),
            voice_host=inputs.get(
                "prodcast_voice_host",
                DEFAULTS["voice_host"],
            ),
            voice_guest=inputs.get(
                "prodcast_voice_guest",
                DEFAULTS["voice_guest"],
            ),
            inputs=inputs,
            fmt=fmt,
        )

        return (
            RunStatus.DONE
            if audio_path.exists()
            else RunStatus.FAILED
        )

    except Exception as exc:

        logger.exception(
            "Unit-Prodcast: voice failed — %s",
            exc,
        )

        return RunStatus.FAILED


# ============================================================================
# Video Generation
# ============================================================================

def _run_video_stage(
    audio_path: Path,
    output_path: Path,
    fmt: str,
    topic: str,
    inputs: dict[str, Any],
    force: bool,
) -> RunStatus:

    if (
        not force
        and _is_valid_file(
            output_path,
            MIN_VIDEO_BYTES,
        )
    ):

        logger.info(
            "Unit-Prodcast: video cached"
        )

        return RunStatus.DONE

    if not audio_path.exists():

        logger.warning(
            "Unit-Prodcast: audio missing"
        )

        return RunStatus.SKIPPED

    pcfg = inputs.get(
        "prodcast_config",
        {},
    )

    clips_cfg = pcfg.get(
        "clips",
        {},
    )

    fmt_suffix = (
        clips_cfg.get(
            "_format_suffix",
            {},
        ).get(fmt, "")
    )

    script_path = (
        audio_path.parent / "script-m.md"
        if fmt == "Shorts"
        else audio_path.parent / "script.md"
    )

    script_lines = []

    if script_path.exists():

        script_lines = (
            script_path.read_text(
                encoding="utf-8"
            ).splitlines()
        )

    pipeline = prodcast_pipeline.build(
        fmt=fmt,
        script_lines=script_lines,
        has_intro=True,
        has_subscribe=True,
        clip_config=clips_cfg,
    )

    if not pipeline:

        logger.error(
            "Unit-Prodcast: empty pipeline"
        )

        return RunStatus.FAILED

    # =========================================================
    # Build line map
    # =========================================================

    line_map = {}

    host_i = 0
    guest_i = 0

    for line in script_lines:

        line = line.strip()

        if line.startswith("Host:"):

            line_map[f"p{host_i}"] = (
                line.replace("Host:", "")
                .strip()
            )

            host_i += 1

        elif line.startswith("Guest:"):

            line_map[f"c{guest_i}"] = (
                line.replace("Guest:", "")
                .strip()
            )

            guest_i += 1

    fmt_clips = {
        **clips_cfg.get("shared", {}),
        **clips_cfg.get(fmt, {}),
    }

    subtitle_map = (
        prodcast_pipeline.build_subtitle_map(
            pipeline=pipeline,
            line_map=line_map,
            fmt_clips=fmt_clips,
        )
    )

    covers = pcfg.get(
        "covers",
        {},
    )

    cover_raw = (
        covers.get(fmt)
        or covers.get("default")
        or inputs.get("prodcast_cover")
    )

    try:

        from cf2.tools.prodcast_video_generator import (
            run as video_tool,
        )

        result = video_tool(
            audio_path=str(audio_path),
            output_path=str(output_path),

            cover_path=(
                str(cover_raw)
                if cover_raw
                else ""
            ),

            fmt=fmt,

            fmt_suffix=fmt_suffix,

            pipeline=pipeline,
            subtitle_map=subtitle_map,

            inputs=inputs,
        )

        logger.info(
            "Unit-Prodcast: %s",
            result,
        )

        return RunStatus.DONE

    except Exception as exc:

        logger.exception(
            "Unit-Prodcast: video failed — %s",
            exc,
        )

        return RunStatus.FAILED


# ============================================================================
# Helpers
# ============================================================================

def _is_valid_file(
    path: Path,
    min_bytes: int,
) -> bool:

    return (
        path.exists()
        and path.stat().st_size >= min_bytes
    )


def _is_fully_cached(
    paths: Paths,
    audio_on: bool,
    video_on: bool,
) -> bool:

    # Script always required
    if not _is_valid_file(paths.script, MIN_SCRIPT_BYTES):
        return False

    need_mini = video_on or ("Shorts" in ["Shorts"])

    if audio_on:
        if not _is_valid_file(paths.audio, MIN_AUDIO_BYTES):
            return False

    if need_mini:
        if not _is_valid_file(paths.script_m, MIN_SCRIPT_M_BYTES):
            return False
        if not _is_valid_file(paths.audio_m, MIN_AUDIO_BYTES):
            return False

    if video_on:
        if not _is_valid_file(paths.video, MIN_VIDEO_BYTES):
            return False
        if not _is_valid_file(paths.video_m, MIN_VIDEO_BYTES):
            return False

    return True


def _extract_text(
    result: Any,
) -> str:

    if isinstance(result, str):
        return result

    for attr in (
        "raw",
        "result",
        "output",
    ):

        value = getattr(
            result,
            attr,
            None,
        )

        if (
            isinstance(value, str)
            and value.strip()
        ):
            return value

    return str(result)


def _record_failure(
    workspace: Path,
    reason: str,
    inputs: dict = None,
) -> str:

    logger.error(
        "Unit-Prodcast: %s",
        reason,
    )

    mark_unit(workspace, "Unit-Prodcast", "failed", inputs)

    meta = load_meta(workspace)
    meta.setdefault(
        "errors",
        {},
    )["Unit-Prodcast"] = reason
    save_meta(
        workspace,
        meta,
    )

    return RunStatus.FAILED
