from __future__ import annotations

"""
unit_dubbing.py — Unit-Dubbing Orchestrator (CF2 Compliant)
============================================================
Thin orchestrator that delegates all work to custom tools in src/cf2/tools/dub_*.py
"""

import os
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_mkldnn_bfloat16"] = "0"

import traceback
from pathlib import Path
from typing import Any
import json as _json

from cf2.meta import load_meta, save_meta, mark_unit
from cf2.tools import dub_pipeline
from cf2.tools import dub_transcribe, dub_ocr, dub_merge_context
from cf2.tools import dub_synthesize, dub_sync, dub_mux, dub_hologram, dub_crop
from cf2.core.services.ffmpeg_service import FFmpegService


def _log(msg: str):
    print(f"[Unit-Dubbing] {msg}")


def _paths(workspace: Path) -> dict:
    d = workspace / "dubbing"
    d.mkdir(parents=True, exist_ok=True)
    return {
        "dir":             d,
        "script":          d / "script.txt",
        "screen_ocr":      d / "screen_ocr.txt",
        "enhanced_script": d / "enhanced_script.txt",
        "dubbed":          d / "dubbed.mp3",
        "synced":          d / "dubbed_synced.mp3",
        "final":           d / "dubbed_final.mp4",
        "holo":            d / "dubbed_holo.mp4",
    }


# ── Post-step validators ────────────────────────────────────────────────────
# Each key maps to an optional validation function called AFTER the tool runs.
# Returns (ok: bool, reason: str)

def _validate_synthesize(p: dict) -> tuple[bool, str]:
    """Ensure dubbed.mp3 exists and is a valid audio file."""
    dubbed = p["dubbed"]
    if not dubbed.exists():
        return False, f"dubbed.mp3 missing: {dubbed}"
    if not FFmpegService.is_valid_audio(str(dubbed), logger=_log):
        return False, f"dubbed.mp3 failed audio integrity check: {dubbed}"
    return True, ""


def _validate_sync(p: dict) -> tuple[bool, str]:
    """Ensure dubbed_synced.mp3 exists and is valid."""
    synced = p["synced"]
    if not synced.exists():
        return False, f"dubbed_synced.mp3 missing: {synced}"
    if not FFmpegService.is_valid_audio(str(synced), logger=_log):
        return False, f"dubbed_synced.mp3 failed audio integrity check: {synced}"
    return True, ""


def _validate_merge(p: dict) -> tuple[bool, str]:
    """Ensure dubbed_final.mp4 exists and is non-trivial."""
    final = p["final"]
    if not final.exists():
        return False, f"dubbed_final.mp4 missing: {final}"
    if final.stat().st_size < 1024:
        return False, f"dubbed_final.mp4 too small: {final.stat().st_size} bytes"
    return True, ""


# Maps step key → post-validator (None = no extra validation)
STEP_VALIDATORS = {
    "transcribe":     None,
    "screen_ocr":     None,
    "merge_context":  None,
    "synthesize":     _validate_synthesize,
    "sync":           _validate_sync,
    "merge":          _validate_merge,
    "hologram":       None,
    "crop":           None,
}

TOOL_MAP = {
    "transcribe":    dub_transcribe,
    "screen_ocr":    dub_ocr,
    "merge_context": dub_merge_context,
    "synthesize":    dub_synthesize,
    "sync":          dub_sync,
    "merge":         dub_mux,
    "hologram":      dub_hologram,
    "crop":          dub_crop,
}


def run(
    topic: str,
    workspace: Path,
    inputs: dict[str, Any],
    force: bool = False,
) -> str:
    if not inputs.get("Unit-Dubbing", False):
        _log("disabled")
        return "disabled"

    dub_cfg = inputs.get("dubbing_config", {})
    # ── Runtime TTS engine override ──────────────────────────
    # Allows:
    #   make dub-ed
    #   make dub-pi
    #   make dub-gt
    #
    # while keeping XTTS as default in config.
    #
    # Environment variable is intentionally short:
    #   TTS=edge
    #   TTS=piper
    #
    override_engine = os.getenv("TTS")

    if override_engine:
        override_engine = override_engine.strip().lower()

        aliases = {
            "xt": "xtts",
            "xtts": "xtts",

            "ed": "edge",
            "edge": "edge",
            "edge-tts": "edge",

            "pi": "piper",
            "piper": "piper",

            "gt": "gtts",
            "gtts": "gtts",
        }

        resolved = aliases.get(override_engine)

        if resolved:
            dub_cfg["tts_engine"] = resolved
            _log(f"🔁 TTS override → {resolved}")
        else:
            _log(
                f"⚠️ Unknown TTS override '{override_engine}' "
                f"(using config default)"
            )
    video_path = dub_cfg.get("source_video", "")
    if not video_path or not Path(video_path).exists():
        _log("source_video not found")
        return "failed"

    p = _paths(workspace)
    meta = load_meta(workspace)
    meta.setdefault("status", {})["Unit-Dubbing"] = "running"
    save_meta(workspace, meta)

    try:
        pipe = dub_pipeline.build(
            source_lang=dub_cfg.get("source_lang", "en"),
            target_lang=dub_cfg.get("target_lang", "en"),
            has_ocr=dub_cfg.get("screen_ocr", {}).get("enabled", True),
            has_translate=False,
            tts_engine=dub_cfg.get("tts_engine", "edge"),
            clip_config={},
        )

        if subtask := inputs.get("subtask"):
            if subtask == "ocr":
                subtask = "screen_ocr"
            pipe = [s for s in pipe if s["key"] == subtask]

        _log(f"Pipeline: {[s['key'] for s in pipe]}")

        for step in pipe:
            key = step["key"]
            tool = TOOL_MAP.get(key)

            if not tool:
                _log(f"⚠️ No tool registered for step: {key}")
                continue

            # Run tool
            ok = tool.run(
                video=video_path,
                paths=p,
                config=dub_cfg,
                workspace=workspace,
                force=force,
                log=_log,
            )

            if not ok:
                return _fail(workspace, f"{key} failed", inputs)

            # Post-step validation
            validator = STEP_VALIDATORS.get(key)
            if validator:
                valid, reason = validator(p)
                if not valid:
                    _log(f"❌ {key} output validation failed: {reason}")
                    return _fail(workspace, reason, inputs)

            _log(f"✅ {key} done")
        # ── Write dubbing meta ───────────────────────────────────

        dubbing_meta = {
            "source_video":  video_path,
            "tts_engine":    dub_cfg.get("tts_engine", "edge"),
            "script_chars":  len(p["script"].read_text(encoding="utf-8").strip())
                             if p["script"].exists() else 0,
            "dubbed_mp3":    str(p["dubbed"]),
            "synced_mp3":    str(p["synced"]),
            "final_mp4":     str(p["final"]),
            "holo_mp4":      str(p["holo"]),
            "status":        "done",
        }

        meta_path = p["dir"] / "dubbing_meta.json"
        meta_path.write_text(
            _json.dumps(dubbing_meta, indent=2),
            encoding="utf-8",
        )
        _log("✅ dubbing_meta.json written")

        mark_unit(workspace, "Unit-Dubbing", "done", inputs)
        _log("Done")
        return "done"

    except Exception as e:
        _log("Exception: " + str(e))
        _log(traceback.format_exc())
        return _fail(workspace, str(e), inputs)


def _fail(workspace: Path, reason: str, inputs: dict = None) -> str:
    mark_unit(workspace, "Unit-Dubbing", "failed", inputs)
    meta = load_meta(workspace)
    meta.setdefault("errors", {})["Unit-Dubbing"] = reason
    save_meta(workspace, meta)
    return "failed"
