

cat src/cf2/units/unit_classroom.py
cat src/cf2/tools/classroom_audio_builder.py
cat src/cf2/tools/classroom_pipeline.py
cat src/cf2/tools/classroom_roles_generator.py
cat src/cf2/tools/classroom_script_generator.py
cat src/cf2/tools/classroom_script_parser.py
cat src/cf2/tools/classroom_subtitle_builder.py
cat src/cf2/tools/classroom_subtitle_builder.py
cat src/cf2/tools/classroom_video_renderer.py





# ── Unit-Classroom ────────────────────────────────────────────────────────
classroom_script_writer:
  role: >
    Kids Classroom Script Writer
  goal: >
    Write a 7-phase structured classroom dialogue for topic {topic}
    using 2 Teachers and 8 Students (ages 6-10). Max 12 words per line.
    Grade 3-5 vocabulary. Each student speaks at least once.
    Output strict format: [PHASE:name] then [TAG] Speaker: text lines.
  backstory: >
    You are a specialist in creating educational content for young learners.
    You write engaging age-appropriate classroom dialogues following a
    fixed 7-phase structure: hook, explain, interaction, example,
    reinforcement, fun_fact, recap_quiz. Never exceed 12 words per line.
    Ensure all 8 student personalities appear at least once.
    Format every line as: [TAG] Speaker: dialogue text
    Example: [T1] Teacher1: Why do clouds float?
             [S1-F] Curious: Is it because of wind?
    Always output [PHASE:name] before each phase block.



# ── Unit-Classroom Tasks ─────────────────────────────────────────────────
create_classroom_script:
  description: >
    Write a full classroom dialogue for topic: {topic}.
    Roles: [T1] Teacher1 (male lead), [T2] Teacher2 (female simplifier),
    [S1-F] Curious, [S2-M] Smart, [S3-F] Confused, [S4-M] Creative,
    [S5-F] Funny, [S6-M] Doubter, [S7-F] Quiet, [S8-M] Beginner.

    REQUIRED STRUCTURE in this exact order:

    [T1] Teacher1: Lesson Goal —
    One sentence stating what kids will learn.

    [T2] Teacher2: Today you will learn —
    3-4 bullet points in kid-friendly language listing specific skills or knowledge.

    [T1] Teacher1: Before we start, think —
    2-3 short questions to spark curiosity before the lesson begins.

    [PHASE:hook]
    [PHASE:explain]
    [PHASE:interaction]
    [PHASE:example]
    [PHASE:reinforcement]
    [PHASE:fun_fact]
    [PHASE:recap_quiz]

    [QUIZ]
    3 numbered questions with answers in (parentheses).

    [KEY POINTS]
    3-4 bullet takeaways.

    [T2] Teacher2:
    One warm closing sentence from a teacher to leave kids feeling good.

    Rules: max 12 words per line, grade 3-5 vocabulary, every student speaks
    at least once, 3-5 students active per phase.
  expected_output: >
    Full script saved to {classroom_dir}/script.md with all sections in order:
    LESSON GOAL, LEARNING OBJECTIVES, PRE-THINK, 7 PHASES, QUIZ, KEY POINTS,
    EMOTIONAL CLOSURE.
  agent: classroom_script_writer
  output_file: "{classroom_dir}/script.md"










  matin@mhpz:/var/POAi/CrewAiFlow/cf2$ cat src/cf2/units/unit_classroom.py
  cat src/cf2/tools/classroom_audio_builder.py
  cat src/cf2/tools/classroom_pipeline.py
  cat src/cf2/tools/classroom_roles_generator.py
  cat src/cf2/tools/classroom_script_generator.py
  cat src/cf2/tools/classroom_script_parser.py
  cat src/cf2/tools/classroom_subtitle_builder.py
  cat src/cf2/tools/classroom_subtitle_builder.py
  cat src/cf2/tools/classroom_video_renderer.py
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
  """
  src/cf2/tools/classroom_audio_builder.py
  Per-line TTS via cf2.core.tts global resolver.
  Fully config-driven — no provider logic here.
  """
  from pathlib import Path
  import os, subprocess, re
  import logging

  logger = logging.getLogger(__name__)

  _XTTS_MODEL = None
  _XTTS_CONFIG = None
  _XTTS_LATENTS = {}

  def _synthesize_xtts(text: str, output_path: str, speaker_wav: str) -> bool:
      """XTTS voice clone — copied from prodcast_voice_generator"""
      try:
          import torch
          import torchaudio
          from pathlib import Path
          from TTS.tts.configs.xtts_config import XttsConfig
          from TTS.tts.models.xtts import Xtts

          if not Path(speaker_wav).exists():
              logger.error("[XTTS] speaker wav not found: %s", speaker_wav)
              return False

          # split long text
          def split_text(t, max_chars=240):
              sentences = re.split(r'(?<=[.!?])\s+', t.strip())
              chunks, cur = [], ""
              for s in sentences:
                  if len(cur) + len(s) + 1 <= max_chars:
                      cur = (cur + " " + s).strip()
                  else:
                      if cur: chunks.append(cur)
                      if len(s) > max_chars:
                          for i in range(0, len(s), max_chars):
                              chunks.append(s[i:i+max_chars])
                          cur = ""
                      else:
                          cur = s
              if cur: chunks.append(cur)
              return chunks or [t[:max_chars]]

          chunks = split_text(text)

          global _XTTS_MODEL, _XTTS_CONFIG
          if _XTTS_MODEL is None:
              model_dir = Path("models/xtts")
              _XTTS_CONFIG = XttsConfig(); _XTTS_CONFIG.load_json(str(model_dir / "config.json"))
              _XTTS_MODEL = Xtts.init_from_config(_XTTS_CONFIG)
              _XTTS_MODEL.load_checkpoint(_XTTS_CONFIG, checkpoint_dir=str(model_dir), eval=True)
              _XTTS_MODEL.cpu()
              logger.info("[XTTS] model loaded (CPU)")

          if speaker_wav not in _XTTS_LATENTS:
              logger.info("[XTTS] computing latents for %s", speaker_wav)
              _XTTS_LATENTS[speaker_wav] = _XTTS_MODEL.get_conditioning_latents(
                  audio_path=[speaker_wav], gpt_cond_len=15, max_ref_length=30
              )
          gpt_cond, speaker_emb = _XTTS_LATENTS[speaker_wav]

          wavs = []
          for chunk in chunks:
              out = _XTTS_MODEL.inference(
                  text=chunk, language="en",
                  gpt_cond_latent=gpt_cond,
                  speaker_embedding=speaker_emb,
                  temperature=0.3, speed=1.1,
              )
              wavs.append(torch.tensor(out["wav"]))

          full_wav = torch.cat(wavs) if len(wavs) > 1 else wavs[0]
          torchaudio.save(output_path, full_wav.unsqueeze(0), 24000, format="mp3")
          return True
      except Exception as e:
          logger.error("[XTTS] synthesis failed: %s", e, exc_info=False)
          return False

  def _is_valid_mp3(path) -> bool:
      """Check MP3 has valid duration > 0.3s via ffprobe."""
      import subprocess
      try:
          r = subprocess.run(
              ["ffprobe", "-v", "error", "-show_entries",
               "format=duration", "-of", "default=nw=1:nk=1", str(path)],
              capture_output=True, text=True, timeout=5
          )
          if r.returncode != 0:
              return False
          return float(r.stdout.strip() or 0) > 0.3
      except Exception:
          return False



  _SECTION_SPEAKER = {
      "LESSON GOAL":         "T1",
      "LEARNING OBJECTIVES": "T2",
      "PRE-THINK":           "T1",
      "QUIZ":                "T1",
      "KEY POINTS":          "T2",
      "EMOTIONAL CLOSURE":   "T2",
  }


  import re as _re
  _QUIZ_KP_RE = _re.compile(r"^\[(QUIZ|KEY POINTS)\]\s*(.+)$", _re.IGNORECASE)

  def _expand_sections(script_txt: str) -> str:
      """Convert [SECTION]\ncontent into [Tx] Teacher: content lines."""
      out = []
      current = None
      for line in script_txt.splitlines():
          _qkm = _QUIZ_KP_RE.match(line.strip())
          if _qkm:
              _spk = "T1" if _qkm.group(1).upper() == "QUIZ" else "T2"
              _tn = "Teacher1" if _spk == "T1" else "Teacher2"
              out.append(f"[{_spk}] {_tn}: {_qkm.group(2).strip()}")
              continue
          s = line.strip()
          m = re.match(r"^\[([A-Z][A-Z\s\-_]+)\]\s*(.*)$", s)
          if m and m.group(1) in _SECTION_SPEAKER:
              current = _SECTION_SPEAKER[m.group(1)]
              inline = m.group(2).strip()
              if inline:
                  out.append(f"[{current}] Teacher{1 if current=='T1' else 2}: {inline}")
              continue
          if s.startswith("[PHASE:") or s.startswith("[T") or s.startswith("[S"):
              current = None
              out.append(line)
              continue
          if current and s and not s.startswith("["):
              tname = "Teacher1" if current == "T1" else "Teacher2"
              # Split bullet/numbered lines
              cleaned = re.sub(r"^[-*\d.)\s]+", "", s).strip()
              if cleaned:
                  out.append(f"[{current}] {tname}: " + ("\u2705 " + cleaned if current=="T2" else cleaned))
              continue
          out.append(line)
      return "\n".join(out)


  _SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+\w[\w\s\-]*?:\s+(.+)$")


  def run(
      script_path:    str,
      output_path:    str,
      fmt:            str = "HD",
      voice_mapping:  dict = None,            # legacy, ignored
      audio_speed:    float = 1.05,
      pause_ms:       int = 350,
      tts_tier:       str = None,
      unit_name:      str = "Unit-Classroom",
      audio_cfg:      dict = None,
  ) -> None:
      audio_cfg = audio_cfg or {}
      from cf2.core.tts import synthesize, resolve_tier_for_unit
      from cf2.core.services.audio_service import AudioService
      from cf2.core.services.ffmpeg_service import FFmpegService

      tier       = tts_tier or resolve_tier_for_unit(unit_name)
      script_txt = Path(script_path).read_text("utf-8")
      script_txt = _expand_sections(script_txt)
      out_path   = Path(output_path)
      seg_dir    = out_path.parent / f"_cls_segs_{fmt}"
      seg_dir.mkdir(parents=True, exist_ok=True)

      audio  = AudioService(logger=lambda m: print(f"[CLS-Audio] {m}"))
      ffmpeg = FFmpegService()

      pause_file = seg_dir / "_pause.mp3"
      if not pause_file.exists() or pause_file.stat().st_size < 100:
          import subprocess as _sp
          _r = _sp.run([
              "ffmpeg", "-y", "-f", "lavfi",
              "-i", f"anullsrc=r=24000:cl=mono",
              "-t", str(pause_ms / 1000.0),
              "-q:a", "9", "-acodec", "libmp3lame",
              str(pause_file)
          ], capture_output=True)
          if _r.returncode != 0:
              print(f"[CLS-Audio] ⚠️ Pause file creation failed: {_r.stderr.decode()[:200]}")

      segments, idx = [], 0
      for raw in script_txt.splitlines():
          m = _SPEAKER_RE.match(raw.strip())
          if not m:
              continue
          tag_base = m.group(1).split("-")[0].upper()
          text     = m.group(2).strip()
          seg_file = seg_dir / f"seg_{idx:04d}.mp3"

          # Re-generate if file missing OR too small OR corrupted
          regenerate = (
              not seg_file.exists()
              or seg_file.stat().st_size < 512
              or not _is_valid_mp3(seg_file)
          )
          if regenerate:
              if seg_file.exists():
                  seg_file.unlink()
              voice = None
              if voice_mapping:
                  voice = voice_mapping.get(tag_base)
              if isinstance(voice, str) and voice.startswith("xtts:"):
                  speaker_wav = voice.split("xtts:", 1)[1].strip()
                  ok = _synthesize_xtts(text, str(seg_file), speaker_wav)
                  provider = "xtts"
              else:
                  ok, provider = synthesize(
                      text=text, output_path=str(seg_file),
                      tier=tier, speaker_tag=tag_base,
                      logger_fn=lambda m: print(f"[CLS-Audio] {m}"),
                  )
              # Pitch up student voices to sound younger
              if ok and tag_base.startswith("S") and seg_file.exists():
                  _tmp = str(seg_file) + ".pitch.mp3"
                  _r = subprocess.run([
                      "ffmpeg", "-y", "-i", str(seg_file),
                      "-af", "asetrate=24000*1.18,aresample=24000,atempo=1/1.05",
                      "-b:a", "128k", _tmp
                  ], capture_output=True)
                  if _r.returncode == 0 and Path(_tmp).exists():
                      Path(_tmp).replace(seg_file)
              # Verify file is actually valid — corrupt files trigger regeneration
              if ok and not _is_valid_mp3(seg_file):
                  print(f"[CLS-Audio] ⚠️  Corrupt seg_{idx:04d}.mp3 — regenerating")
                  seg_file.unlink(missing_ok=True)
                  voice = None
              if voice_mapping:
                  voice = voice_mapping.get(tag_base)
              if isinstance(voice, str) and voice.startswith("xtts:"):
                  speaker_wav = voice.split("xtts:", 1)[1].strip()
                  ok = _synthesize_xtts(text, str(seg_file), speaker_wav)
                  provider = "xtts"
              else:
                  ok, provider = synthesize(
                      text=text, output_path=str(seg_file),
                      tier=tier, speaker_tag=tag_base,
                      logger_fn=lambda m: print(f"[CLS-Audio] {m}"),
                  )
                  # Last resort — silent placeholder
                  if not _is_valid_mp3(seg_file):
                      seg_file.unlink(missing_ok=True)
                      est = max(1.0, min(len(text.split()) * 0.35, 6.0))
                      ffmpeg.create_silent_mp3(str(seg_file), duration=est)
                      provider = "silent_fallback"

              label = provider if provider != "silent_fallback" else "🔇 silent"
              print(f"[CLS-Audio] {'✅' if ok else '❌'} [{label}] seg_{idx:04d}.mp3 ({tag_base})")

          segments.extend([str(seg_file), str(pause_file)])
          idx += 1

      if not segments:
          ffmpeg.create_silent_mp3(str(out_path), duration=5.0)
          return

      if not pause_file.exists():
          ffmpeg.create_silent_mp3(str(pause_file), duration=pause_ms / 1000.0)

      audio.concatenate_audio(segments, str(out_path))

      # Config-driven post-processing
      volume      = audio_cfg.get("volume", 1.0)
      normalize   = audio_cfg.get("normalize", False)
      norm_lufs   = audio_cfg.get("normalize_lufs", -16)
      bitrate     = audio_cfg.get("bitrate", "192k")
      sample_rate = audio_cfg.get("sample_rate", 44100)
      channels    = audio_cfg.get("channels", 2)

      af_filters = []
      if normalize:
          af_filters.append(f"loudnorm=I={norm_lufs}:TP=-1.5:LRA=11")
      elif volume and volume != 1.0:
          af_filters.append(f"volume={volume}")
      if audio_speed and audio_speed != 1.0:
          af_filters.append(f"atempo={audio_speed}")

      if af_filters:
          tmp = str(out_path) + ".tmp.mp3"
          r = subprocess.run(
              ["ffmpeg", "-y", "-i", str(out_path),
               "-af", ",".join(af_filters),
               "-ar", str(sample_rate), "-ac", str(channels),
               "-b:a", bitrate, tmp],
              capture_output=True
          )
          if r.returncode == 0 and os.path.exists(tmp):
              os.replace(tmp, str(out_path))
          elif os.path.exists(tmp):
              os.remove(tmp)
  """
  cf2/tools/classroom_pipeline.py — Classroom Pipeline Structure Builder
  Responsibility: Build the ordered execution plan for a classroom video.
  Pure function — no I/O, no side effects.
  Mirrors: debate_pipeline.py
  """
  from typing import List, Dict, Any
  import re

  _SPEAKER_RE = re.compile(r"^\[(\S+?)\]")
  _HOLO_RE = re.compile(r"^\[HOLO:(\w+)\]", re.IGNORECASE)


  def build(
      fmt: str,
      script_lines: List[str],
      has_intro: bool,
      has_subscribe: bool,
      clip_config: dict,
  ) -> List[Dict[str, Any]]:
      """
      Build classroom pipeline from script lines.
      Each dialogue line → one video step keyed by speaker tag (T1, T2, S1…S8).
      Hologram lines [HOLO:clip_id] → insert visual hologram clip.
      Structural steps (intro, sum, end, sbs) added around them.
      """
      pipeline: List[Dict[str, Any]] = []
      fmt_clips = {**clip_config.get("shared", {}), **clip_config.get(fmt, {})}

      if has_intro:
          pipeline.append({"type": "video", "key": "intro", "role": "intro"})

      for line in script_lines:
          stripped = line.strip()
          if not stripped:
              continue

          # --- Hologram insert ---
          holo_match = _HOLO_RE.match(stripped)
          if holo_match:
              clip_id = holo_match.group(1)
              pipeline.append({
                  "type": "hologram",
                  "key": clip_id,
                  "role": "visual",
                  "tag": "HOLO"
              })
              continue

          # --- Speaker dialogue ---
          m = _SPEAKER_RE.match(stripped)
          if not m:
              continue
          tag = m.group(1)
          tag_base = tag.split("-")[0].upper()
          if tag_base in fmt_clips:
              pipeline.append({"type": "block", "key": tag_base, "role": "speaker", "tag": tag})

      pipeline.append({"type": "block", "key": "sum", "role": "recap"})
      pipeline.append({"type": "video", "key": "end", "role": "end"})

      if has_subscribe:
          pipeline.append({"type": "video", "key": "sbs", "role": "outro"})

      return pipeline


  def build_subtitle_map(
      pipeline: List[Dict[str, Any]],
      line_map: Dict[str, str],
      fmt_clips: Dict[str, Any],
  ) -> Dict[str, str]:
      """
      Map each pipeline step key → subtitle text.
      video steps use fmt_clips subtext.
      block steps use the actual dialogue line text.
      hologram steps get empty subtitle (visual only).
      """
      subtitle_map = {}
      for step in pipeline:
          key = step["key"]
          step_type = step["type"]
          if step_type == "video":
              cfg = fmt_clips.get(key, {})
              subtitle_map[key] = cfg.get("subtext", " ") if isinstance(cfg, dict) else " "
          elif step_type == "hologram":
              # No subtitles for hologram visuals (or use clip_id as placeholder)
              subtitle_map[key] = " "
          else:
              subtitle_map[key] = line_map.get(step.get("tag", key), " ")
      return subtitle_map
  """
  cf2/tools/classroom_roles_generator.py
  subUnitRoles: generate roles.json from classroom_config.
  Called by unit_data.py (Rule D-6). Zero LLM calls.
  """
  import json
  from pathlib import Path

  _PERSONALITIES = {
      "S1": {"personality": "curious",  "speech": "Asks what/how/why — eager short questions"},
      "S2": {"personality": "smart",    "speech": "Confident concise correct answers"},
      "S3": {"personality": "confused", "speech": "I don't understand — gentle clarification"},
      "S4": {"personality": "creative", "speech": "Imaginative real-life connections"},
      "S5": {"personality": "funny",    "speech": "Playful brief humor"},
      "S6": {"personality": "doubter",  "speech": "But I thought — mild non-aggressive"},
      "S7": {"personality": "quiet",    "speech": "1-2 word impactful insights"},
      "S8": {"personality": "beginner", "speech": "Very simple vocabulary"},
  }

  _VOICE_DEFAULTS = {
      "T1": "en-US-AndrewNeural",
      "T2": "en-US-JennyNeural",
      "S1": "en-US-AnaNeural",
      "S2": "en-US-BrianNeural",
      "S3": "en-US-EmmaNeural",
      "S4": "en-US-ChristopherNeural",
      "S5": "en-US-MichelleNeural",
      "S6": "en-US-GuyNeural",
      "S7": "en-US-AriaNeural",
      "S8": "en-US-EricNeural",
  }

  _LABEL_COLORS = {
      "T1": "#4FC3F7", "T2": "#F48FB1",
      "S1": "#FFD54F", "S2": "#81C784",
      "S3": "#FF8A65", "S4": "#64B5F6",
      "S5": "#F06292", "S6": "#A1887F",
      "S7": "#90A4AE", "S8": "#CE93D8",
  }


  def run(workspace_dir: str, classroom_cfg: dict) -> str:
      classroom_dir = Path(workspace_dir) / "classroom"
      classroom_dir.mkdir(parents=True, exist_ok=True)
      roles_path = classroom_dir / "roles.json"

      if roles_path.exists():
          return "⏭️ Skipped — roles.json exists"

      vm     = classroom_cfg.get("voice_mapping", {})
      gd     = classroom_cfg.get("gender_distribution", {})
      male   = set(gd.get("male",   ["S2", "S4", "S6", "S8"]))
      stu_vm = vm.get("students", {})
      count  = classroom_cfg.get("student_count", 8)

      roles = {
          "teachers": {
              "T1": {
                  "role": "lead_teacher", "gender": "M",
                  "voice": vm.get("teacher_1", _VOICE_DEFAULTS["T1"]),
                  "speech": "Clear structured question-driven",
                  "label_color": _LABEL_COLORS["T1"],
                  "personality": "Lead Teacher",
              },
              "T2": {
                  "role": "helper_teacher", "gender": "F",
                  "voice": vm.get("teacher_2", _VOICE_DEFAULTS["T2"]),
                  "speech": "Warm relatable real-life analogies",
                  "label_color": _LABEL_COLORS["T2"],
                  "personality": "Helper Teacher",
              },
          },
          "students": {
              f"S{i}": {
                  **_PERSONALITIES.get(f"S{i}", {"personality": "beginner", "speech": "Simple vocabulary"}),
                  "gender":      "M" if f"S{i}" in male else "F",
                  "voice":       stu_vm.get(f"S{i}", _VOICE_DEFAULTS.get(f"S{i}", "en-US-JennyNeural")),
                  "label_color": _LABEL_COLORS.get(f"S{i}", "#FFFFFF"),
              }
              for i in range(1, count + 1)
          },
      }

      roles_path.write_text(json.dumps(roles, indent=2, ensure_ascii=False), encoding="utf-8")
      return f"✅ roles.json written: {roles_path}"
  """
  cf2/tools/classroom_script_generator.py
  subUnitScript: LLM generates classroom script.md + script-m.md + quiz.json
  Called by unit_data.py when Unit-Classroom=true (Rule D-6).
  Mirrors: prodcast_script_generator.py
  """
  import json, re
  from pathlib import Path


  def run(topic: str, workspace_dir: str, inputs: dict) -> str:
      from cf2.crews.crew import CF2Crew

      classroom_dir = Path(workspace_dir) / "classroom"
      classroom_dir.mkdir(parents=True, exist_ok=True)
      script_path = classroom_dir / "script.md"

      if script_path.exists() and script_path.stat().st_size > 200 and inputs.get("classroom_skip_if_cached", True):
          return f"⏭️ Skipped — script exists: {script_path}"

      factory = CF2Crew(inputs=inputs)
      crew_inputs = {
          **inputs,
          "topic":         topic,
          "classroom_dir": str(classroom_dir),
      }
      result = factory.crew().kickoff(
          agents=[factory.classroom_script_writer()],
          tasks=[factory.create_classroom_script()],
          inputs=crew_inputs,
      )
      raw = str(result)
      script_path.write_text(raw, encoding="utf-8")

      mini = _compress(raw)
      (classroom_dir / "script-m.md").write_text(mini, encoding="utf-8")

      quiz = _extract_quiz(raw)
      (classroom_dir / "quiz.json").write_text(
          json.dumps(quiz, indent=2, ensure_ascii=False), encoding="utf-8"
      )
      return f"✅ script.md written ({script_path.stat().st_size} chars)"


  def _compress(raw: str) -> str:
      skip = {"reinforcement", "fun_fact"}
      lines, skipping = [], False
      for line in raw.splitlines():
          m = re.match(r"^\[PHASE:(\w+)\]", line.strip(), re.IGNORECASE)
          if m:
              skipping = m.group(1).lower() in skip
          if not skipping:
              lines.append(line)
      return "\n".join(lines)


  def _extract_quiz(raw: str) -> dict:
      block = re.search(r"\[QUIZ\](.*?)(\[KEY|\Z)", raw, re.DOTALL | re.IGNORECASE)
      if not block:
          return {"question": "", "options": {}}
      text  = block.group(1).strip()
      lines = [l.strip() for l in text.splitlines() if l.strip()]
      q     = lines[0] if lines else ""
      opts  = {}
      for l in lines[1:]:
          m = re.match(r"^([A-C])[.)]\s+(.+)$", l)
          if m:
              opts[m.group(1)] = m.group(2)
      return {"question": q, "options": opts}
  """
  cf2/tools/classroom_script_parser.py
  Parse classroom script.md into structured lines.
  Each line: [TAG-G] Speaker: text
  """
  import re
  from dataclasses import dataclass, field
  from typing import List, Optional

  _PHASE_RE   = re.compile(r"^\[PHASE:(\w+)\]", re.IGNORECASE)
  _SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+(\w[\w\s\-]*?):\s+(.+)$")
  _QUIZ_RE    = re.compile(r"^\[QUIZ\](.*)", re.IGNORECASE)
  _KEY_RE     = re.compile(r"^\[KEY POINTS?\](.*)", re.IGNORECASE)


  @dataclass
  class ScriptLine:
      phase:    str
      tag:      str        # e.g. T1, S1-F, S2-M
      tag_base: str        # e.g. T1, S1, S2
      speaker:  str
      text:     str
      line_no:  int


  @dataclass
  class ScriptBlock:
      phase: str
      lines: List[ScriptLine] = field(default_factory=list)
      quiz:  Optional[str]    = None
      keys:  List[str]        = field(default_factory=list)


  def parse(raw: str) -> List[ScriptBlock]:
      blocks: List[ScriptBlock] = []
      current_phase = "hook"
      current_block = ScriptBlock(phase=current_phase)

      for i, raw_line in enumerate(raw.splitlines(), 1):
          line = raw_line.strip()
          if not line or line.startswith("#"):
              continue

          m = _PHASE_RE.match(line)
          if m:
              if current_block.lines:
                  blocks.append(current_block)
              current_phase = m.group(1).lower()
              current_block = ScriptBlock(phase=current_phase)
              continue

          m = _QUIZ_RE.match(line)
          if m:
              current_block.quiz = m.group(1).strip()
              continue

          m = _KEY_RE.match(line)
          if m:
              current_block.keys.append(m.group(1).strip())
              continue

          m = _SPEAKER_RE.match(line)
          if m:
              tag      = m.group(1)
              tag_base = tag.split("-")[0].upper()
              current_block.lines.append(ScriptLine(
                  phase    = current_phase,
                  tag      = tag,
                  tag_base = tag_base,
                  speaker  = m.group(2).strip(),
                  text     = m.group(3).strip(),
                  line_no  = i,
              ))

      if current_block.lines:
          blocks.append(current_block)
      return blocks


  def flat_lines(blocks: List[ScriptBlock]) -> List[ScriptLine]:
      return [l for b in blocks for l in b.lines]


  def raw_dialogue_lines(raw: str) -> List[str]:
      """Return only raw dialogue lines (no PHASE/QUIZ/KEY lines)."""
      return [
          l.strip() for l in raw.splitlines()
          if l.strip() and _SPEAKER_RE.match(l.strip())
      ]
  """
  cf2/tools/classroom_subtitle_builder.py
  subUnitSubtitle: script.md + audio.mp3 → .srt + cc_en.txt
  Equal-duration estimation per dialogue line.
  """
  from pathlib import Path
  import re

  _SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+(\w[\w\s\-]*?):\s+(.+)$")


  def _ts(sec: float) -> str:
      h  = int(sec // 3600)
      m  = int((sec % 3600) // 60)
      s  = int(sec % 60)
      ms = int((sec - int(sec)) * 1000)
      return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


  def run(
      script_path: str,
      audio_path: str,
      srt_out: str,
      cc_out: str,
  ) -> None:
      from cf2.core.services.audio_service import AudioService

      audio_svc  = AudioService(logger=lambda m: None)
      total_dur  = audio_svc.get_duration(audio_path) or 60.0
      script_txt = Path(script_path).read_text("utf-8")

      lines = [
          (m.group(1), m.group(2).strip(), m.group(3).strip())
          for line in script_txt.splitlines()
          if (m := _SPEAKER_RE.match(line.strip()))
      ]
      if not lines:
          return

      seg_dur  = total_dur / len(lines)
      srt_blks, cc_rows = [], []

      for i, (tag, speaker, text) in enumerate(lines):
          start = i * seg_dur
          end   = start + seg_dur - 0.05
          label = f"[{tag}] {speaker}: {text}"
          srt_blks.extend([str(i + 1), f"{_ts(start)} --> {_ts(end)}", label, ""])
          cc_rows.append(label)

      Path(srt_out).write_text("\n".join(srt_blks), encoding="utf-8")
      Path(cc_out).write_text("\n".join(cc_rows),  encoding="utf-8")
  """
  cf2/tools/classroom_subtitle_builder.py
  subUnitSubtitle: script.md + audio.mp3 → .srt + cc_en.txt
  Equal-duration estimation per dialogue line.
  """
  from pathlib import Path
  import re

  _SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+(\w[\w\s\-]*?):\s+(.+)$")


  def _ts(sec: float) -> str:
      h  = int(sec // 3600)
      m  = int((sec % 3600) // 60)
      s  = int(sec % 60)
      ms = int((sec - int(sec)) * 1000)
      return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


  def run(
      script_path: str,
      audio_path: str,
      srt_out: str,
      cc_out: str,
  ) -> None:
      from cf2.core.services.audio_service import AudioService

      audio_svc  = AudioService(logger=lambda m: None)
      total_dur  = audio_svc.get_duration(audio_path) or 60.0
      script_txt = Path(script_path).read_text("utf-8")

      lines = [
          (m.group(1), m.group(2).strip(), m.group(3).strip())
          for line in script_txt.splitlines()
          if (m := _SPEAKER_RE.match(line.strip()))
      ]
      if not lines:
          return

      seg_dur  = total_dur / len(lines)
      srt_blks, cc_rows = [], []

      for i, (tag, speaker, text) in enumerate(lines):
          start = i * seg_dur
          end   = start + seg_dur - 0.05
          label = f"[{tag}] {speaker}: {text}"
          srt_blks.extend([str(i + 1), f"{_ts(start)} --> {_ts(end)}", label, ""])
          cc_rows.append(label)

      Path(srt_out).write_text("\n".join(srt_blks), encoding="utf-8")
      Path(cc_out).write_text("\n".join(cc_rows),  encoding="utf-8")
  """
  classroom_video_renderer.py — Per-segment renderer with random animal/shape bubbles
                                 + Hologram overlay support
  Destination: src/cf2/tools/classroom_video_renderer.py

  Kids 6-10 attraction features:
    - 14 random shapes per segment:
        Geometric: rounded-rect, circle, cloud, starburst, ribbon, hexagon
        Animals:   cat, dog, bunny, bird, fish, fox, panda, owl
    - Random screen position (8 zones + jitter)
    - Each speaker keeps unique color + emoji
    - 3-phase clips: init/loop/trails (same format as prodcast)
    - Clip resolution via cf2.core.clip_resolver (global, shared with prodcast/debate)

  Hologram features:
    - [HOLO:source_id:segment_id] tags in script trigger hologram overlays
    - Hologram overlays are large (35-60% of frame), positioned per config
    - HD: bottom_left, center_right, bottom_right, etc.
    - Shorts: center_bottom like a phone landscape screen
    - Zoom parameter controls source magnification (2x = show center 50%)
    - clip_speed controls playback speed (1.5x = faster tutorial)
    - animation controls entry/exit effects (fade_in, slide_up, none)
    - Character animation plays in background behind the hologram panel
  """
  from __future__ import annotations
  import json
  import logging
  import re
  import subprocess
  import textwrap
  import random
  import math
  from typing import Any, Optional
  from pathlib import Path
  from cf2.core import clip_resolver as common_resolver
  from cf2.core.paths import OUTPUT_ROOT


  _QUIZ_KP_RE = re.compile(r"^\[(QUIZ|KEY POINTS)\]\s*(.+)$", re.IGNORECASE)

  def _expand_sections(s):
      import re
      sec = {"LESSON GOAL":"T1","LEARNING OBJECTIVES":"T2","PRE-THINK":"T1",
             "QUIZ":"T1","KEY POINTS":"T2","EMOTIONAL CLOSURE":"T2"}
      out, cur = [], None
      for line in s.splitlines():
          _qkm = _QUIZ_KP_RE.match(line.strip())
          if _qkm:
              _spk = "T1" if _qkm.group(1).upper() == "QUIZ" else "T2"
              _tn = "Teacher1" if _spk == "T1" else "Teacher2"
              out.append(f"[{_spk}] {_tn}: {_qkm.group(2).strip()}")
              continue
          t = line.strip()
          m = re.match(r"^\[([A-Z][A-Z\s\-_]+)\]\s*(.*)$", t)
          if m and m.group(1) in sec:
              cur = sec[m.group(1)]
              inline = m.group(2).strip()
              if inline:
                  out.append(f"[{cur}] Teacher{1 if cur=='T1' else 2}: {inline}")
              continue
          if t.startswith("[PHASE:") or t.startswith("[T") or t.startswith("[S"):
              cur = None
              out.append(line); continue
          if cur and t and not t.startswith("["):
              tn = "Teacher1" if cur == "T1" else "Teacher2"
              cleaned = re.sub(r"^[-*\d.)\s]+", "", t).strip()
              if cleaned: out.append(f"[{cur}] {tn}: " + ("\u2705 " + cleaned if cur=="T2" else cleaned))
              continue
          out.append(line)
      return "\n".join(out)


  _SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+([\w][\w\s\-]*?):\s+(.+)$")
  _HOLO_RE    = re.compile(r"^\[HOLO:([^\]]+)\]$", re.IGNORECASE)

  _STYLES = {
      "T1": ((59, 130, 246),  (37, 99, 235),  "\U0001F393"),
      "T2": ((139, 92, 246),  (124, 58, 237), "\U0001F4DA"),
      "S1": ((16, 185, 129),  (5, 150, 105),  "\U0001F31F"),
      "S2": ((6, 182, 212),   (14, 116, 144), "\U000026A1"),
      "S3": ((245, 158, 11),  (217, 119, 6),  "\U0001F914"),
      "S4": ((239, 68, 68),   (220, 38, 38),  "\U0001F3A8"),
      "S5": ((236, 72, 153),  (219, 39, 119), "\U0001F602"),
      "S6": ((99, 102, 241),  (79, 70, 229),  "\U0001F9D0"),
      "S7": ((20, 184, 166),  (13, 148, 136), "\U0001F33C"),
      "S8": ((249, 115, 22),  (234, 88, 12),  "\U0001F680"),
  }
  _DEFAULT = ((107, 114, 128), (75, 85, 99), "\U0001F4AC")

  _SHAPES = [
      "rounded", "circle", "cloud", "starburst", "ribbon", "hexagon",
      "cat", "dog", "bunny", "bird", "fish", "fox", "panda", "owl",
  ]

  _POSITIONS = [
      "top_left", "top_center", "top_right",
      "mid_left", "mid_right",
      "bottom_left", "bottom_center", "bottom_right",
  ]


  # ── Helpers ───────────────────────────────────────────────────────────────────

  def _ffprobe_duration(path: str) -> float:
      try:
          r = subprocess.run(
              ["ffprobe", "-v", "error", "-show_entries",
               "format=duration", "-of", "default=nw=1:nk=1", str(path)],
              capture_output=True, text=True, timeout=5
          )
          return float(r.stdout.strip() or 0)
      except Exception:
          return 0.0


  # ── Clip Resolution (uses global clip_resolver) ──────────────────────────────

  def _resolve_clip_sequence(key, fmt_clips, clips_base, use_prefix, fmt_suffix=""):
      pipeline = [{"key": key}]

      sequences = common_resolver.resolve_clip_sequences(
          pipeline=pipeline,
          fmt_clips=fmt_clips,
          intro_path=None,
          clips_base=clips_base,
          use_prefix=use_prefix,
          fmt_suffix=fmt_suffix,
      )

      seq = sequences.get(key, {})
      result = {"init": "", "loop": "", "trails": ""}

      paths = seq.get("paths", [])
      if paths and len(paths) > 0:
          result["init"] = paths[0][0]

      loops = seq.get("loops", [])
      if loops and len(loops) > 0:
          result["loop"] = loops[0][0]

      tails = seq.get("tail", [])
      if tails and len(tails) > 0:
          result["trails"] = tails[0][0]

      if not result["loop"]:
          result["loop"] = result["init"]
      if not result["trails"]:
          result["trails"] = result["loop"]

      return result


  # ── Geometric shape drawers ───────────────────────────────────────────────────

  def _draw_rounded(d, box, fill, outline, w=4):
      d.rounded_rectangle(box, radius=28, fill=fill, outline=outline, width=w)

  def _draw_circle(d, box, fill, outline, w=4):
      d.ellipse(box, fill=fill, outline=outline, width=w)

  def _draw_cloud(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw, bh = x2 - x1, y2 - y1
      d.rounded_rectangle([x1, y1 + bh * 0.25, x2, y2 - bh * 0.05],
                            radius=int(bh * 0.4), fill=fill, outline=outline, width=w)
      r = int(bh * 0.32)
      for px, py in [(x1 + bw * 0.22, y1 + bh * 0.10),
                      (x1 + bw * 0.50, y1),
                      (x1 + bw * 0.78, y1 + bh * 0.12)]:
          d.ellipse([px - r, py, px + r, py + 2 * r],
                     fill=fill, outline=outline, width=w)

  def _draw_starburst(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
      rxo, ryo = (x2 - x1) // 2, (y2 - y1) // 2
      rxi, ryi = int(rxo * 0.65), int(ryo * 0.65)
      pts = []
      for i in range(24):
          a = math.pi * i / 12
          rx = rxo if i % 2 == 0 else rxi
          ry = ryo if i % 2 == 0 else ryi
          pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
      d.polygon(pts, fill=fill, outline=outline)

  def _draw_ribbon(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      cut = 30
      pts = [(x1 + cut, y1), (x2 - cut, y1), (x2, (y1 + y2) // 2),
             (x2 - cut, y2), (x1 + cut, y2), (x1, (y1 + y2) // 2)]
      d.polygon(pts, fill=fill, outline=outline)

  def _draw_hexagon(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
      rx, ry = (x2 - x1) // 2, (y2 - y1) // 2
      pts = []
      for i in range(6):
          a = math.pi / 3 * i + math.pi / 6
          pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
      d.polygon(pts, fill=fill, outline=outline)


  # ── Animal shape drawers ──────────────────────────────────────────────────────

  def _draw_cat(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      ear_h = (y2 - y1) * 0.18
      ear_w = (x2 - x1) * 0.18
      d.polygon([(x1 + ear_w, y1 + ear_h), (x1 + ear_w * 0.3, y1),
                 (x1 + ear_w * 2, y1 + ear_h * 0.5)],
                fill=fill, outline=outline)
      d.polygon([(x2 - ear_w, y1 + ear_h), (x2 - ear_w * 0.3, y1),
                 (x2 - ear_w * 2, y1 + ear_h * 0.5)],
                fill=fill, outline=outline)
      d.ellipse([x1, y1 + ear_h * 0.7, x2, y2], fill=fill, outline=outline, width=w)

  def _draw_dog(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      d.ellipse([x1, y1 + bh * 0.05, x1 + bw * 0.25, y1 + bh * 0.55],
                fill=fill, outline=outline, width=w)
      d.ellipse([x2 - bw * 0.25, y1 + bh * 0.05, x2, y1 + bh * 0.55],
                fill=fill, outline=outline, width=w)
      d.ellipse([x1 + bw * 0.10, y1 + bh * 0.10, x2 - bw * 0.10, y2],
                fill=fill, outline=outline, width=w)

  def _draw_bunny(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      ear_w = bw * 0.14
      ear_h = bh * 0.40
      cx = (x1 + x2) // 2
      d.ellipse([cx - ear_w * 1.6, y1, cx - ear_w * 0.4, y1 + ear_h],
                fill=fill, outline=outline, width=w)
      d.ellipse([cx + ear_w * 0.4, y1, cx + ear_w * 1.6, y1 + ear_h],
                fill=fill, outline=outline, width=w)
      d.ellipse([x1, y1 + ear_h * 0.85, x2, y2],
                fill=fill, outline=outline, width=w)

  def _draw_bird(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      d.ellipse([x1 + bw * 0.05, y1 + bh * 0.15, x2 - bw * 0.05, y2 - bh * 0.10],
                fill=fill, outline=outline, width=w)
      d.polygon([(x2 - bw * 0.05, y1 + bh * 0.40),
                 (x2 + bw * 0.06, y1 + bh * 0.50),
                 (x2 - bw * 0.05, y1 + bh * 0.55)],
                fill=outline, outline=outline)
      d.ellipse([x1 + bw * 0.30, y1 + bh * 0.40, x1 + bw * 0.65, y1 + bh * 0.75],
                fill=outline, outline=outline, width=2)

  def _draw_fish(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      d.polygon([(x1, y1 + bh * 0.25), (x1 + bw * 0.25, y1 + bh * 0.50),
                 (x1, y1 + bh * 0.75)],
                fill=fill, outline=outline)
      d.ellipse([x1 + bw * 0.20, y1 + bh * 0.10, x2, y2 - bh * 0.10],
                fill=fill, outline=outline, width=w)

  def _draw_fox(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      d.polygon([(x1, y1 + bh * 0.05), (x1 + bw * 0.20, y1),
                 (x1 + bw * 0.30, y1 + bh * 0.30)],
                fill=fill, outline=outline)
      d.polygon([(x2, y1 + bh * 0.05), (x2 - bw * 0.20, y1),
                 (x2 - bw * 0.30, y1 + bh * 0.30)],
                fill=fill, outline=outline)
      d.polygon([(x1 + bw * 0.10, y1 + bh * 0.20),
                 (x2 - bw * 0.10, y1 + bh * 0.20),
                 ((x1 + x2) // 2, y2)],
                fill=fill, outline=outline)

  def _draw_panda(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      ear_r = bw * 0.14
      d.ellipse([x1 + bw * 0.05, y1, x1 + bw * 0.05 + ear_r * 2, y1 + ear_r * 2],
                fill=outline, outline=outline)
      d.ellipse([x2 - bw * 0.05 - ear_r * 2, y1, x2 - bw * 0.05, y1 + ear_r * 2],
                fill=outline, outline=outline)
      d.ellipse([x1, y1 + ear_r, x2, y2], fill=fill, outline=outline, width=w)

  def _draw_owl(d, box, fill, outline, w=4):
      x1, y1, x2, y2 = box
      bw = x2 - x1
      bh = y2 - y1
      d.polygon([(x1 + bw * 0.15, y1 + bh * 0.15),
                 (x1 + bw * 0.25, y1),
                 (x1 + bw * 0.35, y1 + bh * 0.15)],
                fill=fill, outline=outline)
      d.polygon([(x2 - bw * 0.15, y1 + bh * 0.15),
                 (x2 - bw * 0.25, y1),
                 (x2 - bw * 0.35, y1 + bh * 0.15)],
                fill=fill, outline=outline)
      d.ellipse([x1, y1 + bh * 0.10, x2, y2], fill=fill, outline=outline, width=w)


  _SHAPE_FNS = {
      "rounded":   _draw_rounded,
      "circle":    _draw_circle,
      "cloud":     _draw_cloud,
      "starburst": _draw_starburst,
      "ribbon":    _draw_ribbon,
      "hexagon":   _draw_hexagon,
      "cat":       _draw_cat,
      "dog":       _draw_dog,
      "bunny":     _draw_bunny,
      "bird":      _draw_bird,
      "fish":      _draw_fish,
      "fox":       _draw_fox,
      "panda":     _draw_panda,
      "owl":       _draw_owl,
  }

  _INSET = {
      "rounded": 18, "circle": 60, "cloud": 30, "starburst": 70,
      "ribbon": 40, "hexagon": 50,
      "cat": 40, "dog": 40, "bunny": 50, "bird": 35,
      "fish": 50, "fox": 45, "panda": 40, "owl": 45,
  }


  def _pick_position(cw, ch, bw, bh, key):
      mx = int(cw * 0.04)
      my = int(ch * 0.05)
      if key.startswith("top"):
          y = my
      elif key.startswith("mid"):
          y = (ch - bh) // 2
      else:
          y = ch - bh - my
      if key.endswith("left"):
          x = mx
      elif key.endswith("right"):
          x = cw - bw - mx
      else:
          x = (cw - bw) // 2
      x += random.randint(-20, 20)
      y += random.randint(-15, 15)
      return max(10, min(cw - bw - 10, x)), max(10, min(ch - bh - 10, y))


  # ── Bubble PNG generator ──────────────────────────────────────────────────────

  def _make_bubble_png(path, tag, name, text, cw, ch, seed, bubble_cfg=None):
      bubble_cfg = bubble_cfg or {}
      from PIL import Image, ImageDraw, ImageFont

      rng = random.Random(seed)
      bg, border, emoji = _STYLES.get(tag, _DEFAULT)

      is_short = ch > cw
      shape = rng.choice(_SHAPES)
      position = rng.choice(_POSITIONS)

      FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
      FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
      try:
          name_font  = ImageFont.truetype(FONT_BOLD, 32 if not is_short else 26)
          text_font  = ImageFont.truetype(FONT_REG,  26 if not is_short else 22)
          tag_font   = ImageFont.truetype(FONT_BOLD, 20)
          emoji_font = ImageFont.truetype(FONT_BOLD, 34 if not is_short else 28)
      except Exception:
          name_font = text_font = tag_font = emoji_font = ImageFont.load_default()

      char_limit = 30 if is_short else 38
      wrapped = textwrap.wrap(text, width=char_limit) or [text]

      pad = 22
      line_h = 34 if not is_short else 28
      text_block_h = len(wrapped) * line_h
      header_h = 50

      is_animal = shape in ("cat", "dog", "bunny", "bird", "fish", "fox", "panda", "owl")
      extra = 80 if is_animal else 30

      bubble_w = min(int(cw * 0.55),
                     max(420, max(len(l) for l in wrapped) * 17) + pad * 2 + extra)
      bubble_h = pad + header_h + 8 + text_block_h + pad + extra

      bx, by = _pick_position(cw, ch, bubble_w, bubble_h, position)

      img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
      draw = ImageDraw.Draw(img)

      so = 5
      sbox = [bx + so, by + so, bx + bubble_w + so, by + bubble_h + so]
      _SHAPE_FNS[shape](draw, sbox, (0, 0, 0, 70), (0, 0, 0, 70), 1)

      box = [bx, by, bx + bubble_w, by + bubble_h]
      _op = int(bubble_cfg.get("opacity", 130))
      _SHAPE_FNS[shape](draw, box, (*bg, _op), (*border, min(255, _op + 70)), 4)

      if is_animal:
          eye_y = by + int(bubble_h * 0.30)
          eye_r = 12
          draw.ellipse([bx + bubble_w * 0.30 - eye_r, eye_y - eye_r,
                         bx + bubble_w * 0.30 + eye_r, eye_y + eye_r],
                        fill=(255, 255, 255, 240))
          draw.ellipse([bx + bubble_w * 0.70 - eye_r, eye_y - eye_r,
                         bx + bubble_w * 0.70 + eye_r, eye_y + eye_r],
                        fill=(255, 255, 255, 240))
          pr = 5
          draw.ellipse([bx + bubble_w * 0.30 - pr, eye_y - pr,
                         bx + bubble_w * 0.30 + pr, eye_y + pr], fill=(0, 0, 0, 255))
          draw.ellipse([bx + bubble_w * 0.70 - pr, eye_y - pr,
                         bx + bubble_w * 0.70 + pr, eye_y + pr], fill=(0, 0, 0, 255))

      inset = _INSET.get(shape, 20)
      cx = bx + inset
      cy = by + inset + (40 if is_animal else 0)

      bubble_cx = bx + bubble_w // 2
      name_w = draw.textbbox((0, 0), name, font=name_font)[2]
      header_w = 48 + name_w
      hx = bubble_cx - header_w // 2
      draw.text((hx, cy), emoji, font=emoji_font, fill=(255, 255, 255, 255))
      draw.text((hx + 48, cy + 4), name, font=name_font, fill=(255, 255, 255, 255))

      tag_text = f"[{tag}]"
      tw_ = draw.textbbox((0, 0), tag_text, font=tag_font)[2]
      tx = bx + bubble_w - tw_ - inset - 8
      ty = by + inset
      draw.rounded_rectangle([tx - 8, ty - 4, tx + tw_ + 8, ty + 26],
                              radius=10, fill=(255, 255, 255, 60))
      draw.text((tx, ty), tag_text, font=tag_font, fill=(255, 255, 0, 240))

      div_y = cy + header_h - 4
      draw.line([(cx, div_y), (bx + bubble_w - inset, div_y)],
                 fill=(255, 255, 255, 90), width=2)

      ty = div_y + 12
      for line in wrapped:
          lw = draw.textbbox((0, 0), line, font=text_font)[2]
          lx = bubble_cx - lw // 2
          draw.text((lx + 2, ty + 2), line, font=text_font, fill=(0, 0, 0, 90))
          draw.text((lx, ty), line, font=text_font, fill=(255, 255, 255, 250))
          ty += line_h

      img.save(path, "PNG")


  # ── Hologram overlay compositing ──────────────────────────────────────────────

  def _build_hologram_frame(
      bg_clip_path,
      holo_clip_path,
      audio_path: str,
      audio_dur: float,
      output_path: str,
      w: int, h: int, fps: int,
      topic: str = "",
      position: str = "bottom_left",
      scale_pct: float = 0.55,
      zoom: float = 1.0,
      clip_speed: float = 1.0,
      animation: dict = None,
  ) -> bool:
      """
      Composite hologram overlay onto a character background clip.

      Parameters
      ----------
      bg_clip_path   : character animation clip (looped), or None for solid bg
      holo_clip_path : pre-rendered hologram overlay clip
      position       : "bottom_left", "center_right", "bottom_right",
                       "center_bottom", "center_left", "center"
      scale_pct      : panel width as fraction of canvas width
      zoom           : source magnification from config
                       1.0 = fit whole source
                       2.0 = center 50% (zoomed in on code output)
      clip_speed     : playback speed of hologram clip
                       1.0 = normal, 1.5 = 50% faster, 2.0 = double speed
      animation      : dict with entry/exit effects
                       {"entry": "fade_in", "entry_duration": 0.5,
                        "exit": "none", "exit_duration": 0.0,
                        "slide_direction": "up"}
      """
      animation = animation or {}

      if not holo_clip_path or not Path(holo_clip_path).exists():
          return False
      holo_dur = _ffprobe_duration(holo_clip_path)
      if holo_dur < 0.3:
          return False

      is_shorts = h > w

      # ── Background ──────────────────────────────────────────────────
      has_bg = bg_clip_path and Path(bg_clip_path).exists() and _ffprobe_duration(bg_clip_path) > 0.3
      if has_bg:
          cd = _ffprobe_duration(bg_clip_path)
          loop = ["-stream_loop", "-1"] if cd < audio_dur else []
          inputs = [*loop, "-i", bg_clip_path]
          base_vf = (
              f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
              f"crop={w}:{h},fps={fps}[base]"
          )
      else:
          inputs = ["-f", "lavfi", "-i",
                    f"color=c=0x1a1a2e:s={w}x{h}:r={fps}:d={audio_dur:.3f}"]
          base_vf = "[0:v]copy[base]"

      # ── Hologram sizing ──────────────────────────────────────────────
      border = 3

      if is_shorts:
          holo_w = int(w * 0.92)
          holo_h = int(holo_w * 9 / 16)
      else:
          holo_w = int(w * scale_pct)
          holo_h = int(holo_w * 9 / 16)

      inner_w = holo_w - 2 * border
      inner_h = holo_h - 2 * border

      # ── Position ────────────────────────────────────────────────────
      margin_x = int(w * 0.02)
      margin_y = int(h * 0.02)

      if is_shorts or position == "center_bottom":
          holo_x = (w - holo_w) // 2
          holo_y = h - holo_h - margin_y
      elif position == "bottom_right":
          holo_x = w - holo_w - margin_x
          holo_y = h - holo_h - margin_y
      elif position == "bottom_left":
          holo_x = margin_x
          holo_y = h - holo_h - margin_y
      elif position == "center_right":
          holo_x = w - holo_w - margin_x
          holo_y = (h - holo_h) // 2
      elif position == "center_left":
          holo_x = margin_x
          holo_y = (h - holo_h) // 2
      elif position == "center":
          holo_x = (w - holo_w) // 2
          holo_y = (h - holo_h) // 2
      else:
          holo_x = margin_x
          holo_y = h - holo_h - margin_y

      topic_f = ""
      if topic:
          t_esc = topic.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
          topic_f = (f",drawtext=text='Topic\\: {t_esc}':"
                     f"fontcolor=white:fontsize=44:"
                     f"box=1:boxcolor=black@0.55:boxborderw=12:"
                     f"x=40:y=35:enable='gte(t,0)'")

      # ── Hologram filter chain ────────────────────────────────────────
      #
      # Step 1: Speed adjustment  (setpts=PTS/speed)
      # Step 2: Zoom/scale/crop   (fit or zoom into source)
      # Step 3: Border padding    (cyan border around panel)
      # Step 4: Entry/exit animation (fade_in, slide_up, etc.)
      #
      holo_filter_parts = []

      # Step 1: Speed
      if clip_speed != 1.0:
          holo_filter_parts.append(f"setpts=PTS/{clip_speed:.2f}")

      # Step 2: Zoom + scale + crop
      if zoom <= 1.0:
          # Fit whole source inside panel
          holo_filter_parts.append(
              f"scale={inner_w}:{inner_h}:force_original_aspect_ratio=decrease"
          )
          holo_filter_parts.append(
              f"pad={inner_w}:{inner_h}:(ow-iw)/2:(oh-ih)/2:color=0x0d1117"
          )
      else:
          # Zoom: scale source larger, crop center
          zoom_w = int(inner_w * zoom)
          zoom_h = int(inner_h * zoom)
          holo_filter_parts.append(
              f"scale={zoom_w}:{zoom_h}:force_original_aspect_ratio=increase"
          )
          holo_filter_parts.append(
              f"crop={inner_w}:{inner_h}"
          )

      # Step 3: Cyan border
      holo_filter_parts.append(
          f"pad={holo_w}:{holo_h}:{border}:{border}:color=0x00e5ff"
      )

      # Step 4: Animation
      entry_type = animation.get("entry", "none")
      entry_dur = float(animation.get("entry_duration", 0.5))
      exit_type = animation.get("exit", "none")
      exit_dur = float(animation.get("exit_duration", 0.0))

      if entry_type == "fade_in" and entry_dur > 0:
          holo_filter_parts.append(
              f"fade=t=in:st=0:d={entry_dur:.2f}"
          )
      elif entry_type == "slide_up" and entry_dur > 0:
          # Slide up: start off-screen at bottom, move to final position
          # We handle this via animated overlay position instead of filter
          pass  # handled below in overlay

      if exit_type == "fade_out" and exit_dur > 0:
          exit_start = max(0, audio_dur - exit_dur)
          holo_filter_parts.append(
              f"fade=t=out:st={exit_start:.2f}:d={exit_dur:.2f}"
          )

      holo_vf = f"[1:v]{','.join(holo_filter_parts)}[holo]"

      # ── Build overlay with optional slide animation ──────────────────
      slide_dir = animation.get("slide_direction", "up")

      if entry_type == "slide_up" and entry_dur > 0:
          # Animate overlay Y position: slide from bottom of canvas to final Y
          ed = entry_dur
          if slide_dir == "up":
              overlay_expr = (
                  f"overlay='{holo_x}':"
                  f"if(lt(t\\,{ed:.2f})\\,"
                  f"{h}-({h}-{holo_y})*t/{ed:.2f}\\,"
                  f"{holo_y})"
              )
          elif slide_dir == "left":
              overlay_expr = (
                  f"overlay='"
                  f"if(lt(t\\,{ed:.2f})\\,"
                  f"{w}-({w}-{holo_x})*t/{ed:.2f}\\,"
                  f"{holo_x})':'{holo_y}'"
              )
          elif slide_dir == "right":
              overlay_expr = (
                  f"overlay='"
                  f"if(lt(t\\,{ed:.2f})\\,"
                  f"-{holo_w}+({holo_x}+{holo_w})*t/{ed:.2f}\\,"
                  f"{holo_x}'):'{holo_y}'"
              )
          else:
              overlay_expr = f"overlay={holo_x}:{holo_y}"
      elif entry_type == "fade_in" and entry_dur > 0:
          # fade_in is handled in filter, overlay position is static
          overlay_expr = f"overlay={holo_x}:{holo_y}"
      else:
          overlay_expr = f"overlay={holo_x}:{holo_y}"

      vf = (
          f"{base_vf};"
          f"{holo_vf};"
          f"[base][holo]{overlay_expr}{topic_f}[out]"
      )

      # Hologram clip loop flag
      holo_loop = ["-stream_loop", "-1"] if holo_dur < audio_dur else []

      cmd = [
          "ffmpeg", "-y",
          *inputs,
          *holo_loop, "-i", holo_clip_path,
          "-i", audio_path,
          "-filter_complex", vf,
          "-map", "[out]", "-map", "2:a",
          "-t", f"{audio_dur:.3f}",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "128k",
          output_path,
      ]

      r = subprocess.run(cmd, capture_output=True, text=True)
      if r.returncode != 0:
          print(f"[CLS-Vid] ⚠️  Hologram composite failed: {r.stderr[-300:]}")
          return False
      return Path(output_path).exists() and Path(output_path).stat().st_size > 1000


  # ── Segment builder ───────────────────────────────────────────────────────────

  def _build_segment(clip_path, audio_path, audio_dur, bubble_png, output_path,
                      w, h, fps, topic="", bubble_cfg=None):
      bubble_cfg = bubble_cfg or {}
      has_clip = clip_path and Path(clip_path).exists() and _ffprobe_duration(clip_path) > 0.3
      if has_clip:
          cd = _ffprobe_duration(clip_path)
          loop = ["-stream_loop", "-1"] if cd < audio_dur else []
          inputs = [*loop, "-i", clip_path]
          scale = (f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
                   f"crop={w}:{h},fps={fps}[base]")
      else:
          inputs = ["-f", "lavfi", "-i",
                     f"color=c=0x1a1a2e:s={w}x{h}:r={fps}:d={audio_dur:.3f}"]
          scale = "[0:v]copy[base]"

      topic_f = ""
      if topic:
          t_esc = topic.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
          topic_f = (f",drawtext=text='Topic\\: {t_esc}':"
                     f"fontcolor=white:fontsize=44:"
                     f"box=1:boxcolor=black@0.55:boxborderw=12:"
                     f"x=40:y=35:enable='gte(t,0)'")

      ox, oy = "0", "0"
      vf = f"{scale};[base][1:v]overlay={ox}:{oy}:format=auto{topic_f}[out]"

      if bubble_png is None:
          cmd = [
              "ffmpeg", "-y", *inputs,
              "-i", audio_path,
              "-filter_complex", scale.replace("[base]", "[out]"),
              "-map", "[out]", "-map", "1:a",
              "-t", f"{audio_dur:.3f}",
              "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "128k",
              output_path
          ]
          r = subprocess.run(cmd, capture_output=True, text=True)
          return r.returncode == 0 and Path(output_path).exists()

      cmd = [
          "ffmpeg", "-y", *inputs,
          "-loop", "1", "-i", bubble_png,
          "-i", audio_path,
          "-filter_complex", vf,
          "-map", "[out]", "-map", "2:a",
          "-t", f"{audio_dur:.3f}",
          "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "128k",
          output_path
      ]
      r = subprocess.run(cmd, capture_output=True, text=True)
      if r.returncode != 0:
          print(f"[CLS-Vid] ⚠️  ffmpeg: {r.stderr[-300:]}")
          return False
      return Path(output_path).exists() and Path(output_path).stat().st_size > 1000


  # ── Entry ─────────────────────────────────────────────────────────────────────

  def run(audio_path, script_path, output_path, topic, fmt, workspace,
           clip_config=None, clips_base="assets/classroom/clips", video_fps=30,
           watermark_enabled=True, watermark_text="@KidsThinkAI", watermark_opacity=60,
           bubble_cfg=None, hologram_cfg=None):
      """
      Render classroom video with bubble overlays and optional hologram panels.

      hologram_cfg : dict from profile "hologram" section
                     {
                       "enabled": true,
                       "mode": "floating_screen",
                       "position": "bottom_left",
                       "position_shorts": "center_bottom",
                       "scale_pct": 0.55,
                       "zoom": 1.0,
                       "clip_speed": 1.0,
                       "animation": {
                         "entry": "fade_in",
                         "entry_duration": 0.5,
                         "slide_direction": "up",
                         "exit": "none",
                         "exit_duration": 0.0
                       },
                       "sources": [...]
                     }
      """
      bubble_cfg   = bubble_cfg or {}
      hologram_cfg = hologram_cfg or {}
      ws = Path(workspace)
      out_path = Path(output_path)
      script = Path(script_path).read_text("utf-8")
      script = _expand_sections(script)

      if clip_config is None:
          cfg_path = Path("input/clips/croom.json")
          clip_config = json.loads(cfg_path.read_text("utf-8")) if cfg_path.exists() else {}

      # ── Merge clips via global resolver ──────────────────────────────
      suffix = clip_config.get("_format_suffix", {}).get(fmt, "")
      clips_base_cfg = clip_config.get("_clips_base", clips_base)
      use_prefix = bool(clip_config.get("_folder_prefix", True))
      fmt_clips = common_resolver.merge_clips(clip_config, fmt, suffix)

      # ── Determine format early ───────────────────────────────────────
      is_shorts = "Short" in fmt
      width, height = (1080, 1920) if is_shorts else (1920, 1080)

      # ── Hologram service setup ───────────────────────────────────────
      holo_enabled = hologram_cfg.get("enabled", False)
      holo_clips_map: dict[str, str] = {}

      if holo_enabled:
          try:
              from cf2.core.services.hologram import HologramService
              holo_svc = HologramService(runtime_root=OUTPUT_ROOT)
              holo_svc.prepare(ws.parent.name, hologram_cfg)

              for src_cfg in hologram_cfg.get("sources", []):
                  src_id = src_cfg.get("id", "")
                  for seg_cfg in src_cfg.get("clips", src_cfg.get("segments", [])):
                      seg_id = seg_cfg.get("id", "")
                      resolved = holo_svc.resolve(ws.parent.name, src_id, seg_id)
                      if resolved and resolved.exists():
                          holo_clips_map[seg_id] = str(resolved)
                          print(f"[CLS-Vid] 👁️  Hologram clip ready: {seg_id} → {resolved.name}")

              if holo_clips_map:
                  print(f"[CLS-Vid] 👁️  {len(holo_clips_map)} hologram clips available")
              else:
                  print(f"[CLS-Vid] ⚠️  Hologram enabled but no clips resolved")
          except Exception as e:
              print(f"[CLS-Vid] ⚠️  Hologram service error: {e}")
              holo_enabled = False

      # ── Parse script lines (speakers + hologram tags) ───────────────
      lines = []

      for i, raw in enumerate(script.splitlines()):
          stripped = raw.strip()
          holo_match = _HOLO_RE.match(stripped)
          if holo_match:
              continue
          m = _SPEAKER_RE.match(stripped)
          if m:
              tag, name, text = m.group(1), m.group(2).strip(), m.group(3).strip()
              lines.append((tag.split("-")[0].upper(), name, text))

      if not lines:
          print("[CLS-Vid] ❌ No dialogue lines parsed")
          return

      # ── Determine which speaker lines get hologram overlay ──────────
      holo_line_map: dict[int, str] = {}
      active_holo = None
      line_idx = 0
      for raw_line in script.splitlines():
          stripped = raw_line.strip()
          holo_match = _HOLO_RE.match(stripped)
          if holo_match:
              holo_id = holo_match.group(1)
              if ":" in holo_id:
                  parts = holo_id.split(":", 1)
                  resolved_key = parts[1] if parts[1] in holo_clips_map else holo_id
              else:
                  resolved_key = holo_id
              active_holo = resolved_key if resolved_key in holo_clips_map else None
              continue

          m = _SPEAKER_RE.match(stripped)
          if m:
              if active_holo:
                  holo_line_map[line_idx] = active_holo
              line_idx += 1

      seg_audio_dir = ws / f"_cls_segs_{fmt}"
      seg_video_dir = ws / f"_cls_clips_{fmt}"
      bubble_dir    = ws / f"_cls_bubbles_{fmt}"
      seg_video_dir.mkdir(parents=True, exist_ok=True)
      bubble_dir.mkdir(parents=True, exist_ok=True)

      # ── Resolve clip sequences for each speaker tag ─────────────────
      resolved = {}
      for tag_base, _, _ in lines:
          if tag_base not in resolved:
              clip_seq = _resolve_clip_sequence(tag_base, fmt_clips, clips_base_cfg, use_prefix, fmt_suffix=suffix)
              resolved[tag_base] = clip_seq
              init_name = Path(clip_seq["init"]).name if clip_seq["init"] else "(solid)"
              loop_name = Path(clip_seq["loop"]).name if clip_seq["loop"] else "(solid)"
              trail_name = Path(clip_seq["trails"]).name if clip_seq["trails"] else "(solid)"
              if init_name == loop_name == trail_name:
                  print(f"[CLS-Vid] 🎬 {tag_base:6s} → {init_name}")
              else:
                  print(f"[CLS-Vid] 🎬 {tag_base:6s} → init={init_name} loop={loop_name} trail={trail_name}")

      # ── Read hologram config — all from config, zero hardcodes ──────
      if is_shorts:
          holo_position = hologram_cfg.get("position_shorts", "center_bottom")
      else:
          holo_position = hologram_cfg.get("position", "bottom_left")
      holo_scale_pct = float(hologram_cfg.get("scale_pct", 0.55))
      holo_zoom = float(hologram_cfg.get("zoom", 1.0))
      holo_clip_speed = float(hologram_cfg.get("clip_speed", 1.0))
      holo_animation = hologram_cfg.get("animation", {})

      print(f"[CLS-Vid] 🎬 Building {len(lines)} segments (hologram={'ON' if holo_enabled else 'OFF'})...")
      seg_videos = []

      for i, (tag, name, text) in enumerate(lines):
          audio_seg  = seg_audio_dir / f"seg_{i:04d}.mp3"
          video_seg  = seg_video_dir / f"clip_{i:04d}.mp4"
          bubble_png = bubble_dir / f"bubble_{i:04d}.png"

          if not audio_seg.exists():
              continue
          ad = _ffprobe_duration(str(audio_seg))
          if ad < 0.3:
              continue

          if video_seg.exists() and _ffprobe_duration(str(video_seg)) > 0.3:
              seg_videos.append(str(video_seg))
              continue

          # ── Decide: hologram overlay or bubble? ─────────────────────
          holo_seg_id = holo_line_map.get(i)
          holo_clip_path = holo_clips_map.get(holo_seg_id) if holo_seg_id else None

          if holo_clip_path and Path(holo_clip_path).exists():
              # ── Hologram segment: character bg + large hologram overlay ──
              clip_seq = resolved.get(tag, {"init": "", "loop": "", "trails": ""})
              bg_clip = clip_seq.get("loop") or clip_seq.get("init") or ""

              ok = _build_hologram_frame(
                  bg_clip_path=bg_clip,
                  holo_clip_path=holo_clip_path,
                  audio_path=str(audio_seg),
                  audio_dur=ad,
                  output_path=str(video_seg),
                  w=width, h=height, fps=video_fps,
                  topic=topic if i == 0 else "",
                  position=holo_position,
                  scale_pct=holo_scale_pct,
                  zoom=holo_zoom,
                  clip_speed=holo_clip_speed,
                  animation=holo_animation,
              )
              if ok:
                  seg_videos.append(str(video_seg))
                  pct = (i + 1) / len(lines) * 100
                  print(f"[CLS-Vid] ✅ clip_{i:04d} [{tag}] 🖥️HOLO:{holo_seg_id} \"{text[:25]}\" ({ad:.1f}s) [{pct:.0f}%]")
              else:
                  print(f"[CLS-Vid] ⚠️  Hologram failed, falling back to bubble for clip_{i:04d}")
                  holo_clip_path = None

          if not holo_clip_path or not (Path(video_seg).exists() and Path(video_seg).stat().st_size > 1000):
              # ── Normal bubble segment ───────────────────────────────
              engine = (bubble_cfg or {}).get("engine", "pillow")
              if engine == "pillow":
                  _make_bubble_png(str(bubble_png), tag, name, text, width, height,
                                    seed=i * 31 + hash(tag) % 1000, bubble_cfg=bubble_cfg)
              elif engine == "none":
                  bubble_png = None

              clip_seq = resolved.get(tag, {"init": "", "loop": "", "trails": ""})
              clip = clip_seq.get("loop") or clip_seq.get("init") or ""

              ok = _build_segment(clip, str(audio_seg), ad, str(bubble_png),
                                   str(video_seg), width, height, video_fps,
                                   topic if i == 0 else "", bubble_cfg)
              if ok:
                  seg_videos.append(str(video_seg))
                  pct = (i + 1) / len(lines) * 100
                  print(f"[CLS-Vid] ✅ clip_{i:04d} [{tag}] {name}: \"{text[:25]}\" ({ad:.1f}s) [{pct:.0f}%]")
              else:
                  print(f"[CLS-Vid] ❌ clip_{i:04d} ({tag})")

      if not seg_videos:
          print("[CLS-Vid] ❌ No segments built")
          return

      # ── Bookend clips ───────────────────────────────────────────────
      def _build_bookend(key, dur=4.0, is_intro=False):
          clip_seq = _resolve_clip_sequence(key, fmt_clips, clips_base_cfg, use_prefix, fmt_suffix=suffix)
          clip = clip_seq.get("init") or clip_seq.get("loop") or ""
          if not clip or not Path(clip).exists():
              return None
          out = seg_video_dir / f"_bookend_{key}.mp4"
          if out.exists() and _ffprobe_duration(str(out)) > 0.3:
              return str(out)
          cd = _ffprobe_duration(clip)
          loop = ["-stream_loop", "-1"] if cd < dur else []
          cfg_block = fmt_clips.get(key, {})
          if isinstance(cfg_block, dict):
              subtext = cfg_block.get("subtext", "")
          else:
              subtext = ""
          text_filter = ""
          if subtext:
              t_esc = subtext.replace("'", "\u2019").replace(":", "\\:").replace("%", "%%")
              text_filter = (f",drawtext=text='{t_esc}':"
                             f"fontcolor=white:fontsize=42:"
                             f"box=1:boxcolor=black@0.7:boxborderw=15:"
                             f"x=(w-text_w)/2:y=h*0.78:line_spacing=10")
          narration_path = None
          if subtext:
              try:
                  from cf2.core.tts import synthesize, resolve_tier_for_unit
                  narration_path = str(seg_video_dir / f"_bookend_{key}_audio.mp3")
                  tier = resolve_tier_for_unit("Unit-Classroom")
                  ok, _ = synthesize(text=subtext, output_path=narration_path,
                                      tier=tier, speaker_tag="T2",
                                      logger_fn=lambda m: None)
                  if ok and Path(narration_path).exists():
                      nd = _ffprobe_duration(narration_path)
                      if nd > dur:
                          dur = nd + 0.5
                  else:
                      narration_path = None
              except Exception:
                  narration_path = None

          if narration_path:
              audio_input = ["-i", narration_path]
          else:
              audio_input = ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]

          cmd = [
              "ffmpeg", "-y", *loop, "-i", clip,
              *audio_input,
              "-filter_complex",
              f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
              f"crop={width}:{height},fps={video_fps}{text_filter}[v]",
              "-map", "[v]", "-map", "1:a",
              "-t", f"{dur:.3f}",
              "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "128k",
              str(out)
          ]
          r = subprocess.run(cmd, capture_output=True, text=True)
          if r.returncode != 0:
              print(f"[CLS-Vid] ⚠️  bookend {key}: {r.stderr[-200:]}")
              return None
          return str(out)

      intro = _build_bookend("intro", dur=4.0, is_intro=True)
      sbs   = _build_bookend("sbs",   dur=4.0)
      end   = _build_bookend("end",   dur=3.0)

      final_seq = []
      if intro: final_seq.append(intro); print(f"[CLS-Vid] 🎬 +intro (4s)")
      final_seq.extend(seg_videos)
      if sbs:   final_seq.append(sbs); print(f"[CLS-Vid] 🎬 +sbs (4s)")
      if end:   final_seq.append(end); print(f"[CLS-Vid] 🎬 +end (3s)")
      seg_videos = final_seq

      concat_txt = ws / f"_cls_concat_{fmt}.txt"
      with open(concat_txt, "w") as f:
          for v in seg_videos:
              f.write(f"file '{v}'\n")

      print(f"[CLS-Vid] 🔗 Concat {len(seg_videos)} → {out_path.name}")
      r = subprocess.run([
          "ffmpeg", "-y", "-f", "concat", "-safe", "0",
          "-i", str(concat_txt), "-c", "copy", str(out_path)
      ], capture_output=True, text=True)

      if r.returncode != 0:
          subprocess.run([
              "ffmpeg", "-y", "-f", "concat", "-safe", "0",
              "-i", str(concat_txt),
              "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
              "-c:a", "aac", "-b:a", "128k", str(out_path)
          ], capture_output=True)

      final_dur = _ffprobe_duration(str(out_path))
      holo_info = f" + {len(holo_clips_map)} hologram" if holo_clips_map else ""
      print(f"[CLS-Vid] ✅ {out_path.name} ({final_dur:.1f}s, {len(seg_videos)} segs{holo_info})")
  (cf2) matin@mhpz:/var/POAi/CrewAiFlow/cf2$
