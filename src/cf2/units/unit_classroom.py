"""
unit_classroom.py — Unit-Classroom Orchestrator (CF2 Compliant)
Mirrors unit_prodcast.py pattern exactly:
  unit_classroom.py
    → cf2.tools.classroom_audio_builder      (subUnitAudio)
    → cf2.tools.classroom_video_renderer     (subUnitVideo)
    → cf2.tools.classroom_subtitle_builder   (subUnitSubtitles)
    → cf2.core.llm_executor                  (fallback data generation)

Supports two modes via classroom_mode config:
  "group"   = croom profile — 2 Teachers + 8 Students (default)
  "single"  = ctutor profile — 1 Teacher + Hologram Screen

Rule 4 : One responsibility — orchestrate classroom video pipeline
Rule 6 : Writes only to workspace/classroom/
Rule D-1: Reads only Unit-Data outputs (falls back to free LLM if missing)

All data (roles, voices, prompts, defaults) comes from config — zero hardcoded values.
"""
from __future__ import annotations
from collections import defaultdict



import json
import logging
import re
import traceback

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from cf2.meta import load_meta, save_meta, acquire_lock, release_lock

logger = logging.getLogger(__name__)


# ============================================================================
# Constants — Code only, no data
# ============================================================================

class RunStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    LOCKED = "locked"
    DISABLED = "disabled"

MIN_SCRIPT_BYTES = 200
MIN_AUDIO_BYTES = 1_000
MIN_VIDEO_BYTES = 500_000

_FALLBACK_DEFAULTS: dict[str, Any] = {
    "channel": "CF2",
    "video_formats": ["Shorts", "HD"],
    "audio_speed": 1.05,
    "pause_ms": 350,
    "video_fps": 30,
    "watermark_enabled": True,
    "watermark_text": "@KidsThinkAI",
    "watermark_opacity": 60,
    "fallback_agent": "classroom_script_writer",
}

_FALLBACK_SCRIPT_PROMPT = (
    "Write a full classroom dialogue for topic: {topic}\n"
    "Use [T1] Teacher1: / [T2] Teacher2: / [S1]-[S8] Student: format.\n"
    "Include [PHASE:hook], [PHASE:explain], [PHASE:interaction] sections.\n"
    "Output ONLY the script."
)


# ============================================================================
# Config Reader — Single point of access to classroom_config
# ============================================================================

def _cfg(inputs: dict, key: str, default=None):
    """Read from classroom_config section of inputs.
    For video_formats and hologram, prefer the config file value (not flow override)."""
    if key == "video_formats":
        cfg_val = inputs.get("classroom_config", {}).get(key)
        if cfg_val:
            return cfg_val
    if key == "hologram":
        cfg_val = inputs.get("classroom_config", {}).get(key)
        if cfg_val:
            return cfg_val
        top_val = inputs.get(key)
        if top_val:
            return top_val
    return inputs.get(key, inputs.get("classroom_config", {}).get(key, default))


def _get_roles(inputs: dict) -> dict:
    """Get roles from config. Returns nested dict with teachers/students."""
    roles = _cfg(inputs, "roles", {})
    if roles:
        return roles
    # Default: single teacher only (works for both modes)
    return {
        "teachers": {
            "T1": {"role": "lead_teacher", "gender": "M", "voice": "en-US-AvaNeural",
                    "speech": "Clear structured question-driven", "label_color": "#4FC3F7", "personality": "Lead"},
        },
        "students": {}
    }


def _get_script_prompt(inputs: dict) -> str:
    """Get script prompt template from config."""
    return _cfg(inputs, "script_prompt", _FALLBACK_SCRIPT_PROMPT)


# ============================================================================
# Paths
# ============================================================================

@dataclass(frozen=True)
class Paths:
    workspace: Path
    classroom_dir: Path
    script: Path
    script_m: Path
    roles: Path
    quiz: Path

    @classmethod
    def from_workspace(cls, workspace: Path) -> "Paths":
        ws = workspace.resolve()
        cd = (ws / "classroom").resolve()
        return cls(
            workspace=ws,
            classroom_dir=cd,
            script=cd / "script.md",
            script_m=cd / "script-m.md",
            roles=cd / "roles.json",
            quiz=cd / "quiz.json",
        )

    def audio_for(self, fmt: str) -> Path:
        return self.classroom_dir / f"classroom_audio_{fmt}.mp3"

    def video_for(self, fmt: str, channel: str, slug: str) -> Path:
        """Use classroom_video_{fmt}.mp4 — matches executor cache check."""
        return self.classroom_dir / f"classroom_video_{fmt}.mp4"

    def srt_for(self, fmt: str) -> Path:
        return self.classroom_dir / f"classroom_{fmt}.srt"


# ============================================================================
# Voice Mapping — Built from config roles, never hardcoded
# ============================================================================

def _build_voice_mapping(paths: Paths, inputs: dict) -> dict:
    """
    Build voice mapping from config roles + roles.json on disk.
    Output: {"T1": "en-US-GuyNeural", "S1": "en-US-AnaNeural", ...}
    """
    mapping = {}

    config_roles = _get_roles(inputs)
    for tag, info in config_roles.get("teachers", {}).items():
        if "voice" in info:
            mapping[tag] = info["voice"]
    for tag, info in config_roles.get("students", {}).items():
        if "voice" in info:
            mapping[tag] = info["voice"]

    if paths.roles.exists():
        try:
            roles = json.loads(paths.roles.read_text("utf-8"))
            if "teachers" in roles or "students" in roles:
                for tag, info in roles.get("teachers", {}).items():
                    if "voice" in info:
                        mapping[tag] = info["voice"]
                for tag, info in roles.get("students", {}).items():
                    if "voice" in info:
                        mapping[tag] = info["voice"]
            elif isinstance(roles, list):
                for role_entry in roles:
                    tag = role_entry.get("tag", "")
                    voice = role_entry.get("voice", "")
                    if tag and voice:
                        mapping[tag] = voice
        except Exception as e:
            _log(f"⚠️  Failed to load roles.json for voice mapping: {e}")

    cfg_mapping = _cfg(inputs, "voice_mapping", {})
    mapping.update(cfg_mapping)

    mapping.setdefault("default", "en-US-AvaNeural")
    return mapping


# ============================================================================
# Script Format Validation
# ============================================================================

_SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+\w[\w\s\-]*?:\s+(.+)$")

def _validate_script_format(script_path: Path) -> int:
    """Validate script has [TAG] Name: format. Returns dialogue line count."""
    if not script_path.exists():
        return 0

    text = script_path.read_text(encoding="utf-8")
    dialogue_lines = sum(1 for l in text.splitlines() if _SPEAKER_RE.match(l.strip()))

    if dialogue_lines == 0:
        _log(f"⚠️  Script has 0 [TAG] Name: dialogue lines — audio will be silent!")
        for line in text.splitlines()[:10]:
            if line.strip():
                _log(f"   → {line.strip()[:80]}")
    else:
        _log(f"✅  Script format OK: {dialogue_lines} dialogue lines with [TAG] prefixes")

    return dialogue_lines


# ============================================================================
# LLM Fallback Data Generation
# ============================================================================

def _call_llm(prompt: str, agent_name: str, inputs: dict) -> str:
    """Call LLM through the project's central gateway."""
    try:
        from cf2.core.llm_executor import call_with_fallback

        def _completion_fn(cfg: dict) -> str:
            import litellm
            resp = litellm.completion(
                model=cfg["model"],
                messages=[{"role": "user", "content": prompt}],
                temperature=cfg.get("temperature", 0.7),
                max_tokens=cfg.get("max_tokens", 4096),
            )
            return resp.choices[0].message.content.strip()

        return call_with_fallback(agent_name, inputs, _completion_fn)

    except Exception as e:
        _log(f"⚠️  LLM executor failed: {e}")
        try:
            import requests as _req
            llm_cfg = inputs.get("llm_config", {})
            fb = llm_cfg.get("access_control", {}).get("local_fallback", "ollama/deepseek-r1:1.5b")
            model_name = fb.replace("ollama/", "", 1)
            _log(f"🆘  Raw Ollama last resort: {model_name}")
            resp = _req.post(
                "http://localhost:11434/api/generate",
                json={"model": model_name, "prompt": prompt, "stream": False},
                timeout=180,
            )
            if resp.status_code == 200:
                return resp.json().get("response", "").strip()
        except Exception as e2:
            _log(f"❌  Raw Ollama also failed: {e2}")
        return ""


def _strip_md_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return cleaned


def _fallback_generate_data(topic: str, paths: Paths, inputs: dict) -> RunStatus:
    """Generate script.md, roles.json, quiz.json via free LLM if missing."""
    agent = _cfg(inputs, "fallback_agent", _FALLBACK_DEFAULTS["fallback_agent"])
    ok = True

    # ── roles.json ──────────────────────────────────────────────────
    if not paths.roles.exists():
        config_roles = _get_roles(inputs)
        paths.roles.write_text(json.dumps(config_roles, indent=2), encoding="utf-8")
        _log("✅  roles.json generated from config")

    # ── script.md ───────────────────────────────────────────────────
    if not paths.script.exists():
        _log(f"🆘  Generating script.md via {agent}…")
        prompt_template = _get_script_prompt(inputs)

        # NEW: build a safe dict that returns "" for any missing key
        safe = defaultdict(str, {"topic": topic, **inputs})
        prompt = prompt_template.format_map(safe)   # ← no KeyError, ever

        result = _call_llm(prompt, agent, inputs)
        if result and len(result) >= MIN_SCRIPT_BYTES:
            result = _strip_md_fences(result)

            # --- FIX: LLM dropped [T1] brackets, restore them ---
            fixed = []
            for line in result.splitlines():
                s = line.strip()
                # Case 1: "Matin: text" → "[T1] Matin: text"
                if s.startswith("Matin:") and not s.startswith("["):
                    fixed.append(f"[T1] {s}")
                # Case 2: line looks like dialogue but missing tag
                elif s and ":" in s and not s.startswith("[") and not s.startswith("#") and len(s.split(":")[0].split()) <= 2:
                    # avoid fixing URLs or times
                    if not s.lower().startswith(("http", "https")):
                        fixed.append(f"[T1] Matin: {s}")
                    else:
                        fixed.append(line)
                else:
                    fixed.append(line)
            result = "\n".join(fixed)
            # --- end fix ---

            paths.script.write_text(result, encoding="utf-8")
            _log("✅  script.md generated")
            _validate_script_format(paths.script)
        else:
            _log(f"❌  Failed to generate script.md (got {len(result) if result else 0} chars)")
            ok = False

    # ── quiz.json ───────────────────────────────────────────────────
    if not paths.quiz.exists():
        quiz_data = _extract_quiz_from_script(paths.script)
        if quiz_data:
            paths.quiz.write_text(json.dumps(quiz_data, indent=2), encoding="utf-8")
            _log("✅  quiz.json extracted from script")
        else:
            _log(f"🆘  Generating quiz.json via {agent}…")
            prompt = (
                f"Create 3-5 quiz questions for a classroom video.\nTopic: {topic}\n\n"
                f"Output ONLY valid JSON (no markdown fences):\n"
                f'[{{"question": "Q?", "options": ["A) ...", "B) ...", "C) ...", "D) ..."], '
                f'"answer": "A", "explanation": "why"}}]'
            )
            result = _call_llm(prompt, agent, inputs)
            if result:
                try:
                    cleaned = _strip_md_fences(result)
                    json.loads(cleaned)
                    paths.quiz.write_text(cleaned, encoding="utf-8")
                    _log("✅  quiz.json generated")
                except json.JSONDecodeError as e:
                    _log(f"❌  Invalid JSON for quiz.json: {e}")
                    ok = False

    return RunStatus.DONE if ok else RunStatus.FAILED


def _extract_quiz_from_script(script_path: Path) -> list[dict]:
    """Try to parse quiz questions from [QUIZ] section in script.md."""
    if not script_path.exists():
        return []

    text = script_path.read_text(encoding="utf-8")
    quiz_start = text.find("[QUIZ]")
    if quiz_start == -1:
        return []

    quiz_end = text.find("[KEY POINTS]", quiz_start)
    if quiz_end == -1:
        quiz_end = len(text)

    quiz_text = text[quiz_start + 6:quiz_end].strip()
    questions = []
    for m in re.finditer(r"(\d+)\.\s*(.+?)\s*\((.+?)\)", quiz_text):
        questions.append({
            "question": m.group(2).strip(),
            "options": [],
            "answer": m.group(3).strip(),
            "explanation": m.group(3).strip(),
        })
    return questions if questions else []


# ============================================================================
# Mini Script — Truncate for Shorts format
# ============================================================================

def _create_mini_script(paths: Paths, inputs: dict) -> None:
    """Create script-m.md — truncated version of script.md for Shorts."""
    if not paths.script.exists():
        _log("⚠️  Cannot create mini script: script.md missing")
        return

    text = paths.script.read_text(encoding="utf-8")
    mini_max = _cfg(inputs, "mini_max_chars", 2400)

    if len(text) <= mini_max:
        paths.script_m.write_text(text, encoding="utf-8")
        _log(f"📝  Mini script: copied full ({len(text)} chars)")
        return

    lines = text.splitlines()
    out = []
    used = 0
    budget = mini_max - 200

    for line in lines:
        if line.strip().startswith("[PHASE:"):
            out.append(line)
            continue
        if "[PHASE:recap" in line or "[PHASE:fun_fact" in line:
            break
        if _SPEAKER_RE.match(line.strip()):
            if used + len(line) + 1 > budget:
                break
            out.append(line)
            used += len(line) + 1
        else:
            if used + len(line) + 1 <= mini_max:
                out.append(line)
                used += len(line) + 1

    mini_outro = _cfg(inputs, "mini_outro", "That is a taste of today's lesson. Watch the full video for more!")
    out.append("")
    #out.append(f"[T1] James: {mini_outro}")
    teacher = list(_get_roles(inputs)["teachers"].keys())[0]
    name = _get_roles(inputs)["teachers"][teacher]["name"]
    out.append(f"[{teacher}] {name}: {mini_outro}")

    mini_text = "\n".join(out)
    paths.script_m.write_text(mini_text, encoding="utf-8")
    _log(f"📝  Mini script: {len(mini_text)} chars (from {len(text)} full)")


# ============================================================================
# Public Entry
# ============================================================================

def run(topic: str, workspace: Path, inputs: dict, force: bool = False) -> str:
    if not inputs.get("Unit-Classroom", True):
        _log("⏭️  Unit-Classroom=false — skipping.")
        return RunStatus.DISABLED

    classroom_cfg = inputs.get("classroom_config", {})
    if not classroom_cfg.get("classroom_enabled", False):
        _log("⏭️  classroom_enabled=false — skipping.")
        return RunStatus.DISABLED

    # ── Determine mode: group (croom) or single (ctutor) ───────────────
    classroom_mode = _cfg(inputs, "classroom_mode", "group")
    is_ctutor = classroom_mode == "single"
    if is_ctutor:
        _log("🎓  CTutor mode — single teacher + hologram screen")
    else:
        _log("🏫  Classroom mode — multi-character group")

    paths = Paths.from_workspace(workspace)
    paths.classroom_dir.mkdir(parents=True, exist_ok=True)

    if not force and _is_fully_cached(paths, inputs):
        channel = inputs.get("channel", _cfg(inputs, "channel", _FALLBACK_DEFAULTS["channel"]))
        slug = inputs.get("topic_slug", workspace.name)
        for fmt in _cfg(inputs, "video_formats", _FALLBACK_DEFAULTS["video_formats"]):
            a = paths.audio_for(fmt)
            v = paths.video_for(fmt, channel, slug)
            _log(f"  Cache check [{fmt}]: audio={a.exists()} video={v.exists()}")
        _log("⏭️  Already done — skipping.")
        return RunStatus.DONE

    lock = acquire_lock(workspace, "Unit-Classroom")
    if not lock:
        return RunStatus.LOCKED

    meta = load_meta(workspace)
    meta.setdefault("status", {})
    meta["status"]["Unit-Classroom"] = "running"
    save_meta(workspace, meta)

    try:
        # ── Validate / Fallback required Unit-Data outputs ──────────
        missing = [p for p in [paths.script, paths.roles, paths.quiz] if not p.exists()]
        if missing:
            _log(f"⚠️  Missing Unit-Data outputs: {[p.name for p in missing]}")
            _log("🆘  Unit-Data disabled — generating via free-LLM fallback…")
            fb_result = _fallback_generate_data(topic, paths, inputs)
            if fb_result != RunStatus.DONE:
                still_missing = [p for p in [paths.script, paths.roles, paths.quiz] if not p.exists()]
                _log(f"❌  Still missing after fallback: {[p.name for p in still_missing]}")
                return _record_failure(workspace, meta, "data fallback failed")

        # ── Validate script format ──────────────────────────────────
        _validate_script_format(paths.script)

        # ── Mini Script ─────────────────────────────────────────────
        if not paths.script_m.exists() or force:
            _create_mini_script(paths, inputs)

        # ── Build voice mapping from config + roles.json ────────────
        voice_mapping = _build_voice_mapping(paths, inputs)
        _log(f"🗣️  Voice mapping: {voice_mapping}")

        # ── Hologram config ─────────────────────────────────────────
        hologram_cfg = _cfg(inputs, "hologram", {})
        holo_enabled = hologram_cfg.get("enabled", False) if hologram_cfg else False
        if holo_enabled:
            _log(f"👁️  Hologram enabled: mode={hologram_cfg.get('mode', 'floating_screen')}, "
                 f"sources={len(hologram_cfg.get('sources', []))}")
        else:
            hologram_cfg = {}

        # ── Audio & Video per format ────────────────────────────────
        video_formats = _cfg(inputs, "video_formats", _FALLBACK_DEFAULTS["video_formats"])
        _log(f"DEBUG: video_formats = {video_formats}")
        channel = inputs.get("channel", _cfg(inputs, "channel", _FALLBACK_DEFAULTS["channel"]))
        slug = inputs.get("topic_slug", workspace.name)

        for fmt in video_formats:
            script_src = paths.script_m if "Shorts" in fmt else paths.script
            audio_out = paths.audio_for(fmt)
            video_out = paths.video_for(fmt, channel, slug)

            # Audio
            if not audio_out.exists() or force:
                _log(f"🔊  Building audio [{fmt}]…")
                result = _run_audio_builder(inputs, script_src, audio_out, fmt, voice_mapping)
                if result == RunStatus.FAILED:
                    return _record_failure(workspace, meta, f"audio {fmt} failed")
            else:
                _log(f"⏭️  Audio exists [{fmt}]")

            # Video
            if not video_out.exists() or force:
                _log(f"🎥  Rendering video [{fmt}]…")
                result = _run_video_renderer(
                    inputs, topic, script_src, audio_out, video_out, fmt,
                    paths.classroom_dir, hologram_cfg=hologram_cfg,
                )
                if result == RunStatus.FAILED:
                    return _record_failure(workspace, meta, f"video {fmt} failed")
            else:
                _log(f"⏭️  Video exists [{fmt}]")

            # Subtitles
            srt_out = paths.srt_for(fmt)
            cc_out = paths.classroom_dir / "classroom_cc_en.txt"
            if not srt_out.exists() or force:
                _run_subtitle_builder(script_src, audio_out, srt_out, cc_out)

        # Cleanup temp dirs
        import shutil
        for sub in paths.classroom_dir.glob("_cls_*"):
            if sub.is_dir(): shutil.rmtree(sub, ignore_errors=True)
            else: sub.unlink(missing_ok=True)
        for f in paths.classroom_dir.glob("classroom_audio_*.mp3"):
            f.unlink(missing_ok=True)

        meta["status"]["Unit-Classroom"] = "done"
        meta.setdefault("outputs", {}).update({
            "classroom_video_Shorts.mp4": "exists" if paths.video_for("Shorts", channel, slug).exists() else "missing",
            "classroom_video_HD.mp4": "exists" if paths.video_for("HD", channel, slug).exists() else "missing",
        })
        if holo_enabled:
            meta["outputs"]["hologram"] = "enabled"
        if is_ctutor:
            meta["outputs"]["classroom_mode"] = "single"
        save_meta(workspace, meta)
        _log("✅  Done.")
        return RunStatus.DONE

    except Exception as exc:
        _log(f"❌  Exception: {exc}")
        _log(f"   Traceback: {traceback.format_exc()}")
        return _record_failure(workspace, meta, str(exc))

    finally:
        release_lock(lock)


# ============================================================================
# SubUnit Dispatchers
# ============================================================================

def _run_audio_builder(inputs: dict, script_path: Path, output_path: Path, fmt: str, voice_mapping: dict) -> RunStatus:
    if output_path.exists() and output_path.stat().st_size > MIN_AUDIO_BYTES and not inputs.get("force", False):
        return RunStatus.SKIPPED

    if not script_path.exists():
        _log(f"❌  Audio builder: script not found: {script_path}")
        return RunStatus.FAILED

    script_text = script_path.read_text(encoding="utf-8")
    if len(script_text.strip()) < 50:
        _log(f"❌  Audio builder: script too short ({len(script_text)} chars)")
        return RunStatus.FAILED

    dialogue_count = sum(1 for l in script_text.splitlines() if _SPEAKER_RE.match(l.strip()))
    _log(f"📄  Script for [{fmt}]: {script_path.name} ({len(script_text)} chars, {dialogue_count} dialogue lines)")

    if dialogue_count == 0:
        _log(f"❌  Audio builder: no [TAG] Name: dialogue lines found!")
        for line in script_text.splitlines()[:10]:
            if line.strip():
                _log(f"   → {line.strip()[:80]}")
        return RunStatus.FAILED

    try:
        from cf2.tools.classroom_audio_builder import run as audio_tool

        audio_cfg = dict(_cfg(inputs, "audio", {}))
        if voice_mapping:
            audio_cfg["voice_mapping"] = voice_mapping

        _log(f"🔧  Audio: speed={_cfg(inputs, 'audio_speed', _FALLBACK_DEFAULTS['audio_speed'])}, "
             f"pause={_cfg(inputs, 'pause_ms', _FALLBACK_DEFAULTS['pause_ms'])}ms, "
             f"voices={len(voice_mapping)} mapped")

        audio_tool(
            script_path=str(script_path),
            output_path=str(output_path),
            fmt=fmt,
            voice_mapping=voice_mapping,
            audio_speed=_cfg(inputs, "audio_speed", _FALLBACK_DEFAULTS["audio_speed"]),
            pause_ms=_cfg(inputs, "pause_ms", _FALLBACK_DEFAULTS["pause_ms"]),
            audio_cfg=audio_cfg,
        )

        if output_path.exists() and output_path.stat().st_size > MIN_AUDIO_BYTES:
            _log(f"✅  Audio [{fmt}] ready ({output_path.stat().st_size} bytes)")
            return RunStatus.DONE
        else:
            size = output_path.stat().st_size if output_path.exists() else 0
            _log(f"❌  Audio [{fmt}] output missing or too small ({size} bytes)")
            return RunStatus.FAILED

    except Exception as exc:
        _log(f"❌  Audio builder exception: {exc}")
        _log(f"   Traceback: {traceback.format_exc()}")
        return RunStatus.FAILED


def _run_video_renderer(inputs: dict, topic: str, script_path: Path,
                         audio_path: Path, output_path: Path, fmt: str,
                         workspace: Path, hologram_cfg: dict = None) -> RunStatus:
    if output_path.exists() and output_path.stat().st_size > MIN_VIDEO_BYTES and not inputs.get("force", False):
        return RunStatus.SKIPPED

    if not audio_path.exists():
        _log(f"❌  Video renderer: audio not found: {audio_path}")
        return RunStatus.FAILED

    try:
        from cf2.tools.classroom_video_renderer import run as video_tool

        clips_base = _cfg(inputs, "clips_base", "assets/classroom/clips")
        clip_config = _load_clip_config(inputs)

        if clip_config and "_clips_base" in clip_config:
            clips_base = clip_config["_clips_base"]

        _log(f"🎬  Video: clips_base={clips_base}, formats={list(clip_config.get('_format_suffix', {}).keys())}")

        video_tool(
            audio_path=str(audio_path),
            script_path=str(script_path),
            output_path=str(output_path),
            topic=topic,
            fmt=fmt,
            workspace=str(workspace),
            clip_config=clip_config,
            clips_base=clips_base,
            video_fps=_cfg(inputs, "video_fps", _FALLBACK_DEFAULTS["video_fps"]),
            watermark_enabled=_cfg(inputs, "watermark_enabled", _FALLBACK_DEFAULTS["watermark_enabled"]),
            watermark_text=_cfg(inputs, "watermark_text", _FALLBACK_DEFAULTS["watermark_text"]),
            watermark_opacity=_cfg(inputs, "watermark_opacity", _FALLBACK_DEFAULTS["watermark_opacity"]),
            bubble_cfg=_cfg(inputs, "bubble", {}),
            hologram_cfg=hologram_cfg or {},
        )

        if output_path.exists() and output_path.stat().st_size > MIN_VIDEO_BYTES:
            _log(f"✅  Video [{fmt}] ready ({output_path.stat().st_size} bytes)")
            return RunStatus.DONE
        else:
            size = output_path.stat().st_size if output_path.exists() else 0
            _log(f"❌  Video [{fmt}] output missing or too small ({size} bytes)")
            return RunStatus.FAILED

    except Exception as exc:
        _log(f"❌  Video renderer exception: {exc}")
        _log(f"   Traceback: {traceback.format_exc()}")
        return RunStatus.FAILED


def _run_subtitle_builder(script_path: Path, audio_path: Path,
                           srt_out: Path, cc_out: Path) -> None:
    try:
        from cf2.tools.classroom_subtitle_builder import run as sub_tool
        sub_tool(
            script_path=str(script_path),
            audio_path=str(audio_path),
            srt_out=str(srt_out),
            cc_out=str(cc_out),
        )
    except Exception as exc:
        _log(f"⚠️  Subtitle builder failed: {exc}")


def _load_clip_config(inputs: dict) -> dict:
    """Load clips config from the path specified in config."""
    cfg_file = (
        _cfg(inputs, "clips_config_file", None)
        or inputs.get("classroom_clips_config", None)
        or inputs.get("classroom_clips_file", None)
        or "input/clips/croom.json"
    )
    cfg_path = Path(cfg_file)
    if cfg_path.exists():
        try:
            data = json.loads(cfg_path.read_text("utf-8"))
            return data
        except Exception as e:
            _log(f"⚠️  Failed to load clips config {cfg_file}: {e}")
    else:
        _log(f"⚠️  Clips config not found: {cfg_file}")
    return {}


# ============================================================================
# Helpers
# ============================================================================

def _log(msg: str):
    print(f"[Unit-Classroom] {msg}")

def _is_fully_cached(paths: Paths, inputs: dict) -> bool:
    meta = load_meta(paths.workspace)
    if meta.get("status", {}).get("Unit-Classroom") != "done":
        return False

    required = [paths.script, paths.roles, paths.quiz]
    channel = inputs.get("channel", _cfg(inputs, "channel", _FALLBACK_DEFAULTS["channel"]))
    slug = inputs.get("topic_slug", paths.workspace.name)

    for fmt in _cfg(inputs, "video_formats", _FALLBACK_DEFAULTS["video_formats"]):
        required.append(paths.audio_for(fmt))
        required.append(paths.video_for(fmt, channel, slug))

    return all(p.exists() and p.stat().st_size > 100 for p in required)

def _record_failure(workspace: Path, meta: dict, reason: str) -> str:
    _log(f"❌  {reason}")
    meta.setdefault("status", {})["Unit-Classroom"] = "failed"
    meta.setdefault("errors", {})["Unit-Classroom"] = reason
    save_meta(workspace, meta)
    return RunStatus.FAILED
