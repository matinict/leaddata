
"""
config.py — Compatibility shim for CF2
This file exists so any external script or legacy import that does
from config import PATHS, get_topic_dir, slugify, ...
continues to work without modification.
⚠️  DO NOT add logic here.
All real implementations live in:
cf2.core.paths         → path constants + topic workspace helpers
cf2.core.config_loader → profile loading + deep-merge (Rule 27)
cf2.meta               → meta.json read/write/lock (Rule 23, 25)
cf2.core.llm_resolver  → LLM model resolution + fallback (Rule 28)
cf2.core.llm_circuit   → circuit breaker state (Rule 28)
This file is a thin re-export layer only.
"""
# ── Path constants ─────────────────────────────────────────────────────────
# Rule 18: OUTPUT_ROOT is the topic workspace root (.runtime/output/{slug}/)
# Rule 19: No hardcoded paths — everything flows from PROJECT_ROOT in paths.py
from cf2.core.paths import (
    PROJECT_ROOT,
    INPUT_DIR,
    OUTPUT_ROOT,        # resolves to .runtime/output/  (NOT project-root output/)
    RUNTIME_PATHS,
    get_topic_dir,
    get_topic_paths,
    get_log_path,
    get_cache_path,
)

# Legacy alias: old code imported PATHS["output"], PATHS["secrets"] etc.
# All paths now live under .runtime/ — never at the project root.
PATHS = {
    "root"   : PROJECT_ROOT,
    "input"  : INPUT_DIR,
    "output" : OUTPUT_ROOT,                  # .runtime/output/
    "logs"   : RUNTIME_PATHS["logs"],        # .runtime/logs/
    "secrets": RUNTIME_PATHS["secrets"],     # .runtime/secrets/
    "cache"  : RUNTIME_PATHS["cache"],       # .runtime/cache/
}

# ── Rule 21: Slug generation ───────────────────────────────────────────────
# Canonical implementation lives in core/topic_resolver.py.
# Reproduced here only so `from config import slugify` still works.
# MUST stay byte-for-byte identical to topic_resolver.py (Rule 36).
import re as _re
_STOP_WORDS = {
    "the",  "a",  "an",  "and",  "or",  "but",  "in",  "on",  "at",  "to",  "for",
    "of",  "is",  "are",  "was",  "were",  "be",  "by",  "from",  "with",  "as",
    "if",  "can",  "will",  "should",  "would",  "could",  "have",  "has",  "had",
}

def slugify(topic: str) -> str:
    """
    Convert topic to PascalCase slug (Rule 21).
    Take first 3 meaningful words, skip stop words, join in PascalCase.
    Max 60 characters. Must stay in sync with cf2.core.topic_resolver.slugify.
    Example: 'Iceland Has Yet BEATS Every Country' → 'IcelandYetBeats'
    """
    words = [w for w in _re.split(r'[\s\-_()?!|#]+', topic.lower())
             if w and w not in _STOP_WORDS and len(w) > 1]
    meaningful = words[:3] or _re.split(r'[\s\-_]+', topic.lower())[:3]
    return "".join(w.capitalize() for w in meaningful)[:60]

# ── Rule 22: Collision-free slug (workspace CREATION only) ────────────────
def _find_collision_free_slug(base_slug: str) -> str:
    """
    Append __01, __02 … until a free folder name is found (Rule 22).
    ⚠️  ONLY call this when CREATING a new workspace.
        NEVER call this when READING an existing workspace (Rule 38 bug fix).
        read_meta() uses slugify() directly, not this function.
    """
    if not (OUTPUT_ROOT / base_slug).exists():
        return base_slug
    counter = 1
    while (OUTPUT_ROOT / f"{base_slug}__{counter:02d}").exists():
        counter += 1
    return f"{base_slug}__{counter:02d}"

# ── Rule 23: meta.json helpers ─────────────────────────────────────────────
# Thin wrappers — real implementation is in cf2.meta which takes a workspace
# Path. These wrappers accept a raw topic string for backward compatibility.
import json as _json
def read_meta(topic: str) -> dict:
    """
    Read meta.json for an existing workspace.
    Uses slugify() directly — NOT _find_collision_free_slug() — because
    the workspace already exists. Using the collision helper here would
    produce a wrong path (e.g. EvaFrameworkNew__01) and silently return {}
    even when the real meta.json is present. (Rule 38 bug fix.)
    """
    slug = slugify(topic)                        # ← exact slug, no collision suffix
    f = OUTPUT_ROOT / slug / "meta.json"
    if f.exists():
        try:
            return _json.loads(f.read_text())
        except Exception:
            return {}
    return {}

def write_meta(topic: str, data: dict) -> None:
    """Rule 23: Guarantee topic is persisted in meta.json."""
    data["topic"] = topic  # ✅ Force-sync topic before disk write
    slug = slugify(topic)
    f = OUTPUT_ROOT / slug / "meta.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, indent=2))

def mark_done(topic: str, unit: str):
    meta = read_meta(topic)
    meta.setdefault("status", {})[unit] = "done"
    write_meta(topic, meta)

def is_done(topic: str, unit: str) -> bool:
    """Rule 24: Smart Skip — returns True if unit status is 'done'."""
    return read_meta(topic).get("status", {}).get(unit) == "done"

# ── Rule 25: Lock helpers ──────────────────────────────────────────────────
def acquire_lock(topic: str) -> bool:
    """Create .lock file. Returns False if already locked (Rule 25)."""
    lock = OUTPUT_ROOT / slugify(topic) / ".lock"
    if lock.exists():
        return False
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("locked")
    return True

def release_lock(topic: str):
    """Remove .lock file on clean exit (Rule 25)."""
    lock = OUTPUT_ROOT / slugify(topic) / ".lock"
    if lock.exists():
        lock.unlink()

# ── Rule 27: Config profile loader ────────────────────────────────────────
# UPDATED: Now searches input/profile/ automatically for profile JSONs.
# This keeps flow_controller.py clean and respects the subdirectory hierarchy.
from cf2.core.config_loader import load_config as _base_load_config
from pathlib import Path

def load_profile(profile_name: str) -> dict:
    """
    Rule 27 Profile Loader with input/profile/ support.
    1. Checks input/profile/{name}.json
    2. Falls back to input/data{name}.json (standard CF2)
    3. Falls back to input/{name}.json
    """
    # 1. Check subdirectory: input/profile/travelonly.json
    profile_sub = INPUT_DIR / "profile" / f"{profile_name}.json"
    if profile_sub.exists():
        return _base_load_config(str(profile_sub))

    # 2. Standard CF2: input/datatravelonly.json
    profile_standard = INPUT_DIR / f"data{profile_name}.json"
    if profile_standard.exists():
        return _base_load_config(str(profile_standard))

    # 3. Root fallback: input/travelonly.json
    profile_root = INPUT_DIR / f"{profile_name}.json"
    if profile_root.exists():
        return _base_load_config(str(profile_root))

    # 4. Final fallback to base config
    return _base_load_config("data.json")

# ── Rule 37: Resolve *_file paths to absolute ─────────────────────────────
import os as _os
import json as _json
def resolve_config_paths(inputs: dict) -> dict:
    """
    Rule 37: Walk inputs dict and resolve any *_file key whose value is a
    relative path to an absolute path. Also loads external JSON files
    referenced by pointer keys (e.g. debate_3d_clips_file → debate_3d_clips).
    Path routing priority (fixed — do not change without updating Rule 37):
      1. Already absolute            → leave untouched
      2. Starts with 'input/'        → PROJECT_ROOT / value
      3. Matches a secret pattern    → .runtime/secrets/ basename
      4. Anything else               → INPUT_DIR / basename

    Pointer expansion (new — supports clips3d.json pattern):
      Any  key ending in '_file' that points to a .json file and has a
      sibling key with the same name minus '_file' will be loaded and
      injected inline. Example:
         "debate_3d_clips_file": "input/clips3d.json"
        → loads clips3d.json and sets "debate_3d_clips": { ... }
    """
    _secrets_dir = str(RUNTIME_PATHS["secrets"])
    _secret_patterns = {"client_secret", "client_secrets", "token",
                        "credentials", "api_key", "secret", "credential"}

    def _is_secret(filename: str) -> bool:
        lower = filename.lower()
        return any(p in lower for p in _secret_patterns)

    def _resolve_path(v: str) -> str:
        """Resolve a single relative path string to absolute."""
        if _os.path.isabs(v):
            return v
        if v.startswith("input/"):
            return str(PROJECT_ROOT / v)
        if _is_secret(v):
            return _os.path.join(_secrets_dir, _os.path.basename(v))
        return str(INPUT_DIR / _os.path.basename(v))

    def _walk(obj):
        if isinstance(obj, dict):
            # Collect keys first to avoid mutating dict during iteration
            for k, v in list(obj.items()):
                if isinstance(v, str) and k.endswith("_file") and not _os.path.isabs(v):
                    resolved = _resolve_path(v)
                    obj[k] = resolved

                    # Pointer expansion: if key is "foo_file" and value is a
                    # .json file, load it and inject as "foo" if not already set.
                    inline_key = k[:-5]          # strip "_file" suffix
                    if (resolved.endswith(".json")
                            and inline_key not in obj
                            and _os.path.exists(resolved)):
                        try:
                            obj[inline_key] = _json.loads(
                                open(resolved).read()
                            )
                        except Exception:
                            pass    # bad JSON — leave expansion to the caller
                elif isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    _walk(item)
        return obj

    return _walk(inputs)

# ── Debug helpers ──────────────────────────────────────────────────────────
def print_paths():
    print("📁 CF2 Paths:")
    for k, v in PATHS.items():
        print(f"  {k:10}: {v}")

def test_slug():
    tests = [
        "Iceland Has Yet BEATS Every Country in Peace? (18 Years #1 | GPI Shock)",
        "Is AI Actually Dangerous?",
        "The Future of Work in 2026",
        "EVA Framework for New Evaluating Voice Agents",
        "Is American Innovation Continues to Lead the World?",
    ]
    print("\n🧪 Slug Tests (Rule 21):")
    for t in tests:
        print(f"  {t[:55]:55} → {slugify(t)}")

if __name__ == "__main__":
    print_paths()
    test_slug()

=================================================================================
# ─────────────────────────────────────────────────────────────────────────────
# CF2 — CrewAI Flow Factory Makefile
# Usage: make <target> [p=profile] [t=topic] [u=unit]
# All commands use `uv run` — change to `python -m` if not using uv.
# ─────────────────────────────────────────────────────────────────────────────
RUN = uv run python -m cf2.main
p ?= 3d  # Default profile if none specified

# ── Profiles & Status ──────────────────────────────────────────────────────
profiles:
	$(RUN) --list-profiles

status:
	$(RUN) --status --profile $(p)

# ── Single Unit Runners ────────────────────────────────────────────────────
scout:
	$(RUN) --unit Unit-Scout --profile $(p)

data:
	$(RUN) --unit Unit-Data --profile $(p)

debate:
	$(RUN) --unit Unit-Debate --profile $(p)

definition:
	$(RUN) --unit Unit-Definition --profile $(p)

animation:
	$(RUN) --unit Unit-Animation --profile $(p)

comparison:
	$(RUN) --unit Unit-Comparison --profile $(p)

pack:
	$(RUN) --unit Unit-Packaging --profile $(p)

publish:
	$(RUN) --unit Unit-Publisher --profile $(p)

advertise:
	$(RUN) --unit Unit-Advertise --profile $(p)

# ── TravelOnly Pipeline (Profile: travelonly) ──────────────────────────────
travelonly:
	$(RUN) --profile travelonly

travelonly-force:
	$(RUN) --profile travelonly --force

leaddata:
	$(RUN) --unit Unit-LeadData --profile travelonly

leaddata-force:
	$(RUN) --unit Unit-LeadData --profile travelonly --force

# ── Full Pipeline (Respects Unit-* flags in config) ────────────────────────
run-full:
	$(RUN) --profile $(p)

# ── Force Re-runs (Bypass Smart-Skip) ─────────────────────────────────────
force-scout:
	$(RUN) --unit Unit-Scout --profile $(p) --force

force-data:
	$(RUN) --unit Unit-Data --profile $(p) --force

force-debate:
	$(RUN) --unit Unit-Debate --profile $(p) --force

force-pack:
	$(RUN) --unit Unit-Packaging --profile $(p) --force

force-publish:
	$(RUN) --unit Unit-Publisher --profile $(p) --force

force-advertise:
	$(RUN) --unit Unit-Advertise --profile $(p) --force

# ── 3D Pipeline Shortcuts (Respects Unit-* flags in data3d.json) ──────────
3d:
	$(RUN) --profile 3d

3d-force:
	$(RUN) --profile 3d --force

3d-data:
	$(RUN) --unit Unit-Data --profile 3d

3d-pack:
	$(RUN) --unit Unit-Packaging --profile 3d

3d-scout:
	$(RUN) --unit Unit-Scout --profile 3d

3d-force-debate:
	$(RUN) --unit Unit-Debate --profile 3d --force

3d-pack-force:
	$(RUN) --unit Unit-Packaging --profile 3d --force

3d-full:
	$(RUN) --profile 3d --force

3d-topic:
	$(RUN) --unit Unit-Debate --profile 3d --topic "$(t)"

# ── Bengali Debug Shortcuts (Profile: Bn) ─────────────────────────────────
bn:
	$(RUN) --unit Unit-Debate --profile Bn

bn-data:
	$(RUN) --unit Unit-Data --profile Bn

bn-pack:
	$(RUN) --unit Unit-Packaging --profile Bn

# ── Podcast Profiles (pcm=Male/Female, pcf=Female/Male) ───────────────────
pcm:
	$(RUN) --profile pcm

pcf:
	$(RUN) --profile pcf

pcm-force:
	$(RUN) --profile pcm --force

pcf-force:
	$(RUN) --profile pcf --force

pcm-topic:
	$(RUN) --unit Unit-Prodcast --profile pcm --topic "$(t)"

pcf-topic:
	$(RUN) --unit Unit-Prodcast --profile pcf --topic "$(t)"

pcm-dry:
	$(RUN) --unit Unit-Prodcast --profile pcm --dry-run

pcf-dry:
	$(RUN) --unit Unit-Prodcast --profile pcf --dry-run

# ── Classroom Profile (croom - 2 Teachers / 8+ Students) ──────────────────
croom:
	$(RUN) --profile croom

croom-force:
	$(RUN) --profile croom --force

croom-unit:
	$(RUN) --unit Unit-Classroom --profile croom

croom-unit-force:
	$(RUN) --unit Unit-Classroom --profile croom --force

croom-topic:
	$(RUN) --unit Unit-Classroom --profile croom --topic "$(t)"

croom-dry:
	$(RUN) --unit Unit-Classroom --profile croom --dry-run

# ── CTutor Profile (ctutor - 1 Teacher + Hologram Screen) ─────────────────
ctutor:
	$(RUN) --profile ctutor

ctutor-force:
	$(RUN) --profile ctutor --force

ctutor-unit:
	$(RUN) --unit Unit-Classroom --profile ctutor

ctutor-unit-force:
	$(RUN) --unit Unit-Classroom --profile ctutor --force

ctutor-topic:
	$(RUN) --unit Unit-Classroom --profile ctutor --topic "$(t)"

ctutor-dry:
	$(RUN) --unit Unit-Classroom --profile ctutor --dry-run

# ── Dry Run (Shows execution plan, runs nothing) ──────────────────────────
dry:
	$(RUN) --unit $(u) --profile $(p) --dry-run

# ── LLM Health Dashboard ──────────────────────────────────────────────────
llm:
	@uv run python -c "import json, pathlib; f=pathlib.Path('.runtime/cache/llm_status.json'); d=json.loads(f.read_text()) if f.exists() else {}; print('LLM STATUS -', len(d), 'models'); [print(k, v.get('status','?'), v.get('last_call','')[:19]) for k,v in sorted(d.items())] if d else print('No LLM calls yet')"

llm-status: llm

lls:
	@watch -n 3 "make llm"

llm-json:
	@cat .runtime/cache/llm_status.json 2>/dev/null | python -m json.tool || echo "No status file yet"

# ── Help ──────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  CF2 Make Targets"
	@echo "  ============================================================"
	@echo "  make profiles               List available profiles"
	@echo "  make status p=3d            Show pipeline status"
	@echo ""
	@echo "  Units (p=profile)"
	@echo "  make data p=3d              Run Unit-Data"
	@echo "  make debate p=3d            Run Unit-Debate"
	@echo "  make pack p=3d              Run Unit-Packaging"
	@echo "  make scout p=3d             Run Unit-Scout"
	@echo ""
	@echo "  TravelOnly (Profile: travelonly)"
	@echo "  make travelonly             Run TravelOnly pipeline"
	@echo "  make leaddata               Run Unit-LeadData directly"
	@echo "  make travelonly-force       Force re-run TravelOnly"
	@echo ""
	@echo "  Podcast (pcm=Male Host, pcf=Female Host)"
	@echo "  make pcm                    Run Podcast Male-Host pipeline"
	@echo "  make pcf                    Run Podcast Female-Host pipeline"
	@echo "  make pcm-force              Force re-run pcm"
	@echo "  make pcf-force              Force re-run pcf"
	@echo "  make pcm-topic t='...'      Run pcm with custom topic"
	@echo "  make pcf-topic t='...'      Run pcf with custom topic"
	@echo ""
	@echo "  Classroom (croom - 2 Teachers / 8+ Students)"
	@echo "  make croom                  Run Classroom pipeline"
	@echo "  make croom-force            Force re-run Classroom"
	@echo "  make croom-unit             Run Unit-Classroom only"
	@echo "  make croom-unit-force       Force re-run Unit-Classroom"
	@echo "  make croom-topic t='...'    Run with custom topic"
	@echo ""
	@echo "  CTutor (ctutor - 1 Teacher + Hologram Screen)"
	@echo "  make ctutor                 Run CTutor pipeline"
	@echo "  make ctutor-force           Force re-run CTutor"
	@echo "  make ctutor-unit            Run Unit-Classroom only (ctutor)"
	@echo "  make ctutor-unit-force      Force re-run Unit-Classroom (ctutor)"
	@echo "  make ctutor-topic t='...'   Run with custom topic"
	@echo ""
	@echo "  3D Pipeline (Profile: 3d)"
	@echo "  make 3d                     Run 3D pipeline"
	@echo "  make 3d-force               Force re-run 3D"
	@echo "  make 3d-data                Run Unit-Data (3D profile)"
	@echo "  make 3d-pack                Run Unit-Packaging (3D profile)"
	@echo ""
	@echo "  Bengali (Profile: Bn)"
	@echo "  make bn                     Run Unit-Debate Bengali"
	@echo "  make bn-data                Run Unit-Data Bengali"
	@echo ""
	@echo "  Force Re-runs (p=profile)"
	@echo "  make force-data p=3d        Force Unit-Data"
	@echo "  make force-debate p=3d      Force Unit-Debate"
	@echo "  make force-pack p=3d        Force Unit-Packaging"
	@echo ""
	@echo "  LLM Health"
	@echo "  make llm                    LLM status dashboard"
	@echo "  make llm-json               Raw LLM status JSON"
	@echo "  make lls                    Live-watch LLM status (3s refresh)"
	@echo ""
	@echo "  Dry Run"
	@echo "  make dry u=Unit-Debate p=3d Dry-run any unit+profile"
	@echo ""

=================================================================================
"""
meta.py — State, Smart-Skip & File Contract Manager
Rules Implemented:
  Rule 23: Centralized meta.json tracking & status reporting
  Rule 24: Smart Skip + Config Drift Detection
  Rule D-7: Physical file verification before trusting meta status
  Rule 25: Atomic file locking to prevent race conditions
"""
import json
import os
import re  # ✅ ADD THIS LINE!
import fcntl
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

# ── Constants ───────────────────────────────────────────────────────────────
META_FILE = "meta.json"
LOCK_FILE = ".lock"

VALID_UNITS = [
    "Unit-Scout",
    "Unit-Data",
    "Unit-LeadData",
    "Unit-Debate",
    "Unit-Definition",
    "Unit-Animation",
    "Unit-Comparison",
    "Unit-Prodcast",      # ✅ Rule 23: Explicitly tracked
    "Unit-Classroom",     # ✅ NEW
    "Unit-Packaging",
    "Unit-Publisher",
    "Unit-Advertise",
]

# Rule 24b: Config keys that invalidate cache when changed
UNIT_CONFIG_KEYS = {
    "Unit-Data": [
        "min_virality_score", "use_web_search", "platforms", "niches",
        "granularity", "start", "end"
    ],
    "Unit-Debate": [
        "debate_max_chars", "debate_format", "debate_video_enabled",
        "debate_merge_enabled", "debate_background_enabled"
    ],
    "Unit-Animation": [
        "animation_styles", "bar_merge_enabled", "bar_race_audio_enabled"
    ],
    "Unit-Definition": [
        "definition_max_chars", "definition_video", "image_gen_backend"
    ],
    "Unit-Comparison": [
        "comparison_max_chars", "comparison_format"
    ],
    "Unit-Prodcast": [      # ✅ Rule 24: Cache invalidation triggers
        "prodcast_max_script_chars", "prodcast_format",
        "prodcast_voice_host", "prodcast_voice_guest",
        "prodcast_tts_engine", "prodcast_video_enabled",
        "prodcast_video_style", "prodcast_skip_if_cached",
        "prodcast_audio_speed", "prodcast_pause_between_lines_ms"
    ],
    "Unit-Classroom": [     # ✅ NEW
        "classroom_enabled", "classroom_video_formats",
        "classroom_audio_speed", "classroom_pause_between_lines_ms",
        "classroom_skip_if_cached",
    ],
    "Unit-Publisher": [
        "upload_privacy", "upload_category_id", "upload_cc",
        "social_platforms", "schedule_post"
    ],
}

# ── Core I/O ────────────────────────────────────────────────────────────────
def load_meta(workspace: Path, topic: str = "") -> Dict[str, Any]:
    """Load meta.json. Creates default structure if missing."""
    path = workspace / META_FILE
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return _create_default_meta(workspace, topic)

def _create_default_meta(workspace: Path, topic: str = "") -> Dict[str, Any]:
    """Rule 23: Initialize clean state with pending status for all units."""
    meta = {
        "version": "2.0",
        "slug": workspace.name,
        "topic": topic,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": {u: "pending" for u in VALID_UNITS},
        "config_hash": {},
        "errors": {}
    }
    save_meta(workspace, meta)
    return meta

def save_meta(workspace: Path, data: Dict[str, Any]) -> None:
    """Atomic write using tmp + replace (prevents corruption on crash)."""
    path = workspace / META_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp_path = path.with_suffix('.tmp')
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp_path.replace(path)
    except Exception as e:
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"Failed to save meta.json: {e}")

# ── Config Fingerprint & Marking ────────────────────────────────────────────
def _config_hash(unit: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a snapshot of tracked config keys for drift detection."""
    keys = UNIT_CONFIG_KEYS.get(unit, [])
    return {k: inputs.get(k) for k in keys}

def mark_unit(workspace: Path, unit: str, status: str, inputs: dict = None) -> None:
    """Update unit status and store config hash on completion (Required by executor.py)."""
    meta = load_meta(workspace)
    meta["status"].setdefault(unit, "pending")   # safe for units added after meta was created
    meta["status"][unit] = status
    meta[f"{unit}_at"] = datetime.now(timezone.utc).isoformat()
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Store config fingerprint on 'done' to enable future drift detection
    if status == "done" and inputs and unit in UNIT_CONFIG_KEYS:
        meta.setdefault("config_hash", {})[unit] = _config_hash(unit, inputs)

    save_meta(workspace, meta)

# ── Rule D-7 & 24: Smart Skip & Verification ────────────────────────────────
def verify_unit_done(unit: str, workspace: Path, inputs: Dict[str, Any] = None) -> bool:
    """Rule D-7: Verify meta says 'done' AND physical output files exist."""
    meta = load_meta(workspace)
    if meta.get("status", {}).get(unit) != "done":
        return False

    # File contract checks
    if unit == "Unit-Data":
        # Only check artifacts for blocks that are actually enabled
        from cf2.units.unit_data import CONSUMER_REQUIREMENTS, BLOCK_ARTIFACTS
        checks = []
        for u, blocks in CONSUMER_REQUIREMENTS.items():
            if (inputs or {}).get(u, False):
                for block in blocks:
                    checks.extend(BLOCK_ARTIFACTS.get(block, ()))
    elif unit == "Unit-Prodcast":
        checks = ["podcast/audio.mp3"]
        if inputs and inputs.get("prodcast_video_enabled"):
            # ✅ FIX: Match the dynamic Rule 33 naming from unit_prodcast.py Paths dataclass
            channel = inputs.get("channel", "Channel")
            slug = inputs.get("topic_slug", workspace.name)
            safe_channel = re.sub(r"[^a-zA-Z0-9_-]", "", channel) or "Channel"
            checks.append(f"podcast/{safe_channel}_{slug}_HD.mp4")
    elif unit == "Unit-Debate":
        checks = ["debate/decide.md"]
    elif unit == "Unit-Animation":
        checks = ["animation/output.mp4"]
    elif unit == "Unit-Classroom":
        checks = [
            "classroom/script.md",
            "classroom/roles.json",
            "classroom/quiz.json",
        ]
        cfg = (inputs or {}).get("classroom_config", {})
        fmts = cfg.get("video_formats") or (inputs or {}).get("classroom_video_formats", ["HD"])
        for fmt in fmts:
            checks.append(f"classroom/classroom_video_{fmt}.mp4")
    else:
        checks = []

    if checks:
        missing = [c for c in checks if not (workspace / c).exists()]
        if missing:
            print(f"  ↩️  {unit} reset — missing files: {missing}")
            meta["status"][unit] = "failed"
            save_meta(workspace, meta)
            return False
    return True

def should_skip(workspace: Path, unit: str, force: bool = False, inputs: Dict[str, Any] = None) -> bool:
    """Rule 24: Master Smart-Skip Logic + Config Drift Detection."""
    if force:
        return False
    if not verify_unit_done(unit, workspace, inputs):
        return False

    # Config drift detection: skip if cached, but invalidate if inputs changed
    if unit in UNIT_CONFIG_KEYS:
        meta = load_meta(workspace)
        old_config = meta.get("config_hash", {}).get(unit, {})
        current_config = {k: inputs.get(k) for k in UNIT_CONFIG_KEYS[unit]}

        if current_config != old_config:
            print(f"  🔄  {unit} config changed — cache invalidated")
            meta["config_hash"][unit] = current_config
            meta["status"][unit] = "pending"
            save_meta(workspace, meta)
            return False

    return True

def update_status(workspace: Path, unit: str, status: str, error: str = None) -> None:
    """Quick helper for units to update their status without full meta reload."""
    meta = load_meta(workspace)
    meta["status"].setdefault(unit, "pending")
    meta["status"][unit] = status
    if error:
        meta.setdefault("errors", {})[unit] = error
    save_meta(workspace, meta)

def show_status(workspace: Path) -> None:
    """Rule 23: CLI status printer."""
    meta = load_meta(workspace)
    print(f"\n📊  Status: {meta.get('slug', 'Unknown')} ({meta.get('topic', 'N/A')})")
    print("-" * 50)
    for unit in VALID_UNITS:
        status = meta.get("status", {}).get(unit, "unknown")
        icon = "✅" if status == "done" else "❌" if status == "failed" else "⏳"
        print(f"  {icon} {unit:<20} {status}")
    print()

# ── Rule 25: File Locking ───────────────────────────────────────────────────
def acquire_lock(workspace: Path, unit: str = "global") -> Optional[Path]:
    """Acquire exclusive lock. Returns lock path on success, None on failure."""
    lock_file = workspace / LOCK_FILE
    try:
        fd = open(lock_file, 'w')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(f"{unit} | {datetime.now(timezone.utc).isoformat()}\n")
        fd.flush()
        return lock_file
    except (IOError, OSError):
        print(f"  🔒  {unit} locked by another process. Aborting.")
        return None

def release_lock(lock_file: Optional[Path]) -> None:
    """Release exclusive lock and cleanup file."""
    if lock_file and lock_file.exists():
        try:
            with open(lock_file, 'r') as f:
                fd = f.fileno()
            fcntl.flock(fd, fcntl.LOCK_UN)
            lock_file.unlink(missing_ok=True)
        except Exception:
            pass

# ── Subtask Tracking (Required by Unit-LeadData) ────────────────────────
def mark_subtask(workspace: Path, unit: str, subtask: str, status: str) -> None:
    """
    Track individual subtask status inside a unit.
    Stores data under meta["subtasks"][unit][subtask].
    """
    meta = load_meta(workspace)

    # Initialize nested dicts if they don't exist
    if "subtasks" not in meta:
        meta["subtasks"] = {}
    if unit not in meta["subtasks"]:
        meta["subtasks"][unit] = {}

    meta["subtasks"][unit][subtask] = status
    meta["updated_at"] = datetime.now(timezone.utc).isoformat()

    save_meta(workspace, meta)

=================================================================================
"""
🎛️ flow_controller.py — Orchestrator ONLY (~150 lines)
main.py calls run(). That is it.
Rules implemented:
Rule 2:  FlowController = sole decision authority (load config here)
Rule 19: Deep-merge profiles (data.json + data3d.json)
Rule 23: Resolve all *_file paths to absolute before units run
Scout-first fix:
When topic='auto' + Unit-Scout enabled → workspace creation is DEFERRED.
Unit-Scout runs first (in _scout_staging/), then the real topic is resolved
from the populated queue and the real workspace is created.
"""
import os
import sys
import json
import signal as _signal
import warnings
import logging
from pathlib import Path
from datetime import datetime, timezone
from crewai.flow.flow import Flow, listen, start
from cf2.core.logging_setup import setup as setup_logging
from cf2.meta                      import load_meta, save_meta, show_status
from cf2.core.topic_resolver       import resolve_topic, generate_slug, resolve_workspace, pick_from_queue
from cf2.core.executor             import run_unit
from cf2.cli.cli                   import parse_args, apply_cli_overrides, install_sigint_handler
from config                        import load_profile, resolve_config_paths

# Suppress noisy warnings
warnings.filterwarnings("ignore", message=".*skip_file_prefixes.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

# 🔥 Pipeline Execution Order
PIPELINE_ORDER = [
    "Unit-Scout",
    "Unit-Data",
    "Unit-LeadData",
    "Unit-Debate",
    "Unit-Prodcast",
    "Unit-Classroom",
    "Unit-Definition",
    "Unit-Animation",
    "Unit-Comparison",
    "Unit-Packaging",
    "Unit-Publisher",
    "Unit-Advertise",
]
_AUTO = "auto"

# ── Flow ───────────────────────────────────────────────────────────────────
class VideoFactoryFlow(Flow):
    @start()
    def initialize(self):
        print("\n" + "=" * 60)
        print("🎬  CF2 — CrewAI Flow Factory")
        print("=" * 60)

    @listen(initialize)
    def run_pipeline(self):
        inputs = self.state.get("inputs", {})
        unit   = inputs.get("_unit")
        force  = inputs.get("_force", False)

        # ── Scout-first: resolve real topic + workspace when topic=auto ───
        if inputs.get("_topic", "").lower() == _AUTO:
            inputs = _scout_then_resolve(inputs, force)
            if not inputs:
                print("❌  Scout ran but queue still empty — aborting.")
                return
            self.state["inputs"] = inputs

        topic     = inputs["_topic"]
        workspace = Path(inputs["_workspace"])

        if unit:
            # Single unit execution
            run_unit(unit, topic, workspace, inputs, force)
        else:
            # Full pipeline execution
            print(f"🔄  Full pipeline — {workspace.name}")
            skip_scout = inputs.get("_scout_done", False)
            for u in PIPELINE_ORDER:
                # 🔥 CRITICAL FIX: Enforce Unit-* switches at Flow level (Rule 6/24)
                # If config says false, skip instantly. Zero LLM, zero API calls.
                if not inputs.get(u, False):
                    print(f"⏭️  SKIP: {u} disabled (Unit switch=false in config)")
                    continue

                if u == "Unit-Scout" and skip_scout:
                    continue

                run_unit(u, topic, workspace, inputs, force)

        print("\n✅  Flow complete.\n")

# ── Scout-first helper ─────────────────────────────────────────────────────
def _scout_then_resolve(inputs: dict, force: bool) -> dict | None:
    from cf2.core.paths import OUTPUT_ROOT
    staging = OUTPUT_ROOT / "_scout_staging"
    staging.mkdir(parents=True, exist_ok=True)
    print("🔍  topic=auto — running Unit-Scout to discover topic...")
    run_unit("Unit-Scout", _AUTO, staging, inputs, force)

    topic = pick_from_queue(inputs)
    if not topic:
        return None

    slug      = generate_slug(topic)
    workspace = resolve_workspace(topic, slug)
    _init_meta(workspace, topic, slug)

    print(f"\n📁  Workspace : {workspace}")
    print(f"🏷️   Slug      : {slug}")
    print(f"📝  Topic     : {topic}")

    inputs["topic"]       = topic
    inputs["_topic"]      = topic
    inputs["_workspace"]  = str(workspace)
    inputs["_slug"]       = slug
    inputs["_scout_done"] = True
    _flatten_inputs(inputs, slug)
    return inputs

# ── Flatten all template variables once before kickoff ────────────────────
def _flatten_inputs(inputs: dict, slug: str) -> dict:
    def flatten_recursive(obj, parent_key=''):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                new_key = f"{parent_key}_{k}" if parent_key else k
                if k.endswith("_config") and isinstance(v, dict):
                    flatten_recursive(v, parent_key)
                else:
                    inputs.setdefault(new_key, v)
                    flatten_recursive(v, new_key)
        return obj
    flatten_recursive(inputs)

    inputs.setdefault("filename",   slug)
    inputs.setdefault("topic_slug", slug)

    engine = inputs.get("tts_engine", "edge-tts")
    voices = inputs.get("edge_tts_voices" if engine == "edge-tts" else "piper_voices", {})
    inputs.setdefault("tts_voices", json.dumps(voices, ensure_ascii=False))

    # 🔥 DEFAULT CONFIG VALUES (Append-only per Rule 29)
    D = {
        "debate_definition_enabled": False, "debate_max_chars": 3000,
        "debate_mini_max_chars": 300, "debate_mini_enabled": False,
        "debate_secs_per_line": 3.5, "debate_video_enabled": False,
        "debate_merge_enabled": False, "debate_mini_merge_enabled": False,
        "debate_background_enabled": False, "debate_background_prompt": "",
        "debate_bg_opacity": 150, "image_gen_backend": "auto",
        "intro_enabled": False, "intro_context": "", "intro_duration": 5,
        "animation_styles": ["bar_race"], "bar_merge_enabled": False,
        "bar_race_audio_enabled": False, "definition_max_chars": 15000,
        "definition_video": False, "force_refresh": False, "fps": 4.9,
        "fps_hd_offset": 1.37, "video_fps": 30, "audio_speed": 1.1,
        "audio_speed_hd": 1.0, "video_formats": ["Shorts"],
        "video_style": ["debate"], "watermark_enabled": True,
        "watermark_text": "@PlayOwnAi", "watermark_opacity": 60,
        "yt_metadata_lang": 35, "yt_cc_lang": 6, "upload_youtube_video": False,
        "upload_privacy": "private", "upload_category_id": "28",
        "upload_cc": False, "upload_cc_lang": 35, "upload_md_lang": 35,
        "upload_notify_subscribers": False, "upload_client_secrets_file": "input/client_secrets.json",
        "upload_token_file": "input/token.json", "upload_facebook_video": False,
        "fb_privacy_status": "SELF", "fb_credentials_file": "input/fb_credentials.json",
        "social_share_enabled": False, "social_share_dry_run": False,
        "social_platforms": ["LinkedIn"], "schedule_post": False,
        "schedule_datetime": "", "schedule_timezone": "UTC",
        "force_scraping": False, "platforms": [], "niches": [],
        "min_virality_score": 75, "output_queue_size": 10,
        "auto_consume": True, "use_web_search": False,
        "scraping_url_file": "data/scraping_url.json",
        "start": None, "end": None, "granularity": "yearly",
        "use_label_mappings": True,

        "prodcast_enabled": False, "prodcast_script_source": "debate",
        "prodcast_max_script_chars": 3000, "prodcast_format": "host_guest",
        "prodcast_intro_enabled": True, "prodcast_outro_enabled": True,
        "prodcast_tts_engine": "edge-tts", "prodcast_voice_host": "en-US-RogerNeural",
        "prodcast_voice_guest": "en-US-AriaNeural", "prodcast_audio_speed": 1.0,
        "prodcast_audio_lang": "en", "prodcast_pause_between_lines_ms": 350,
        "prodcast_video_enabled": False, "prodcast_video_style": "waveform",
        "prodcast_video_width": 1920, "prodcast_video_height": 1080,
        "prodcast_video_fps": 30, "prodcast_video_bg_color": "#0a0a0a",
        "prodcast_video_waveform_color": "#00d4ff", "prodcast_show_title": True,
        "prodcast_show_subtitle": True, "prodcast_subtitle": "@360Debate Podcast",
        "prodcast_watermark_enabled": True, "prodcast_watermark_text": "@360Debate",
        "prodcast_shorts_enabled": False, "prodcast_shorts_count": 3,
        "prodcast_shorts_duration": 60, "prodcast_generate_transcript": True,
        "prodcast_transcript_format": "srt", "prodcast_skip_if_cached": True,
        "prodcast_config_file": "input/unit_prodcast_config.json",

        "classroom_enabled": False, "classroom_age_group": "kids_6_10",
        "classroom_video_formats": ["Shorts", "HD"], "classroom_audio_speed": 1.05,
        "classroom_pause_between_lines_ms": 350, "classroom_watermark_enabled": True,
        "classroom_watermark_text": "@KidsThinkAI", "classroom_generate_subtitles": True,
        "classroom_generate_cc": True, "classroom_bgm_enabled": False,
        "classroom_bgm_volume": 0.15, "classroom_skip_if_cached": True,
        "classroom_config_file": "input/unit_classroom_config.json",
    }

    for k, v in D.items():
        inputs.setdefault(k, v)
    return inputs

# ── Helpers ────────────────────────────────────────────────────────────────
def _init_meta(workspace: Path, topic: str, slug: str):
    meta = load_meta(workspace, topic)  # ✅ Pass topic to meta creation
    if not meta.get("slug"):
        meta["slug"] = slug
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_meta(workspace, meta)

# ── Entry point ────────────────────────────────────────────────────────────
def run(profile: str = "data.json"):
    setup_logging()
    args = parse_args()
    from cf2.cli.cli import handle_early_exit
    if handle_early_exit(args):
        return

    profile_name = args.profile or profile
    inputs = load_profile(profile_name)
    inputs = resolve_config_paths(inputs)
    inputs = apply_cli_overrides(inputs, args)

    topic    = resolve_topic(inputs)
    is_auto  = topic.lower() == _AUTO
    scout_on = bool(inputs.get("Unit-Scout") or inputs.get("social_scout_unit"))

    if not topic:
        print("❌  No topic. Use --topic or set topic in input/data.json")
        sys.exit(1)

    inputs["topic"] = topic

    if is_auto and scout_on:
        slug      = _AUTO.capitalize()
        workspace = Path("(pending)")
        print(f"\n📝  Topic     : auto → Unit-Scout will pick from queue")
        print(f"🗂️   Profile   : {profile_name}")
    else:
        slug = generate_slug(topic)
        workspace = resolve_workspace(topic, slug)
        _init_meta(workspace, topic, slug)
        print(f"\n📁  Workspace : {workspace}")
        print(f"🏷️   Slug      : {slug}")
        print(f"📝  Topic     : {topic}")
        print(f"🗂️   Profile   : {profile_name}")

    if args.status and not is_auto:
        show_status(workspace)
        return

    inputs["_topic"]     = topic
    inputs["_workspace"] = str(workspace)
    inputs["_slug"]      = slug
    inputs["_force"]     = args.force
    if args.unit:
        inputs["_unit"]  = args.unit

    if not is_auto:
        _flatten_inputs(inputs, slug)

    orig_sigint = install_sigint_handler()
    flow = VideoFactoryFlow()
    flow.state["inputs"] = inputs
    try:
        flow.kickoff()
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("🛑  CF2 INTERRUPTED — re-run to continue from last completed unit.")
        print("=" * 60)
        sys.exit(130)
    finally:
        _signal.signal(_signal.SIGINT, orig_sigint)

if __name__ == "__main__":
    run()

=================================================================================
matin@mhpz:/var/POAi/CrewAiFlow/cf2$ tree
.
├── assets
│   ├── bubble
│   ├── classroom
│   │   ├── clips
│   │   │   ├── 00_intro
│   │   │   │   └── Intro.mkv
│   │   │   ├── 01_ad1
│   │   │   │   ├── Bji3s.mkv
│   │   │   │   └── Bji3s_s.mkv
│   │   │   ├── 02_T1
│   │   │   │   └── T1.mkv
│   │   │   ├── 03_T2
│   │   │   │   └── T2F.mkv
│   │   │   ├── 04_S1
│   │   │   │   └── S1.mkv
│   │   │   ├── 05_S2
│   │   │   │   └── S2M.mkv
│   │   │   ├── 06_S3
│   │   │   │   └── S3F.mkv
│   │   │   ├── 07_S4
│   │   │   │   ├── S11R.mkv
│   │   │   │   └── S4F.mkv
│   │   │   ├── 08_S5
│   │   │   │   └── S5F.mkv
│   │   │   ├── 09_S6
│   │   │   │   └── S6.mkv
│   │   │   ├── 10_S7
│   │   │   │   └── S7.mkv
│   │   │   ├── 11_S8
│   │   │   │   └── S8.mkv
│   │   │   ├── 14_sum
│   │   │   │   └── T2F.mkv
│   │   │   ├── 16_ad2
│   │   │   │   ├── Bji1.mkv
│   │   │   │   ├── Bji1_s.mkv
│   │   │   │   ├── Bji4s.mkv
│   │   │   │   ├── try.mkv
│   │   │   │   └── try_s.mkv
│   │   │   ├── 17_end
│   │   │   └── 18_sbs
│   │   │       ├── sub.mkv
│   │   │       └── sub_s.mkv
│   │   └── cover.png
│   ├── debate
│   │   ├── 00_intro
│   │   │   ├── int2s.mkv
│   │   │   ├── int5s.mkv
│   │   │   └── intro.mkv
│   │   ├── 01_ad1
│   │   │   ├── Bji000.mkv
│   │   │   ├── Bji3s.mkv
│   │   │   └── Bji4s.mkv
│   │   ├── 02_p0
│   │   │   ├── 360D.png
│   │   │   ├── 360D_s.png
│   │   │   ├── p03s.mkv
│   │   │   ├── p0fl23s.mkv
│   │   │   └── p0fl.mkv
│   │   ├── 03_c0
│   │   │   ├── adufl3s.mkv
│   │   │   ├── c0efl5s.mkv
│   │   │   ├── c0fl20s.mkv
│   │   │   └── c0fl.mkv
│   │   ├── 04_p1
│   │   │   ├── Arg1.mkv
│   │   │   └── p0fl.mkv
│   │   ├── 05_c1
│   │   │   ├── adufl3s.mkv
│   │   │   ├── c0fl.mkv
│   │   │   └── CA1.mkv
│   │   ├── 06_p2
│   │   │   ├── Arg2.mkv
│   │   │   └── p0fl.mkv
│   │   ├── 07_c2
│   │   │   ├── adufl3s.mkv
│   │   │   ├── c0fl.mkv
│   │   │   └── CA2.mkv
│   │   ├── 08_p3
│   │   │   ├── arg3h.mkv
│   │   │   ├── Arg3.mkv
│   │   │   └── p0fl.mkv
│   │   ├── 09_c3
│   │   │   ├── adufl3s.mkv
│   │   │   ├── c0fl.mkv
│   │   │   └── CA3.mkv
│   │   ├── 10_p4
│   │   │   ├── arg4h.mkv
│   │   │   ├── arg4.mkv
│   │   │   └── p0fl.mkv
│   │   ├── 11_c4
│   │   │   ├── c0fl.mkv
│   │   │   └── CA4.mkv
│   │   ├── 12_p5
│   │   │   └── p0fl.mkv
│   │   ├── 13_c5
│   │   │   └── c0fl.mkv
│   │   ├── 14_sum
│   │   │   ├── aly.mkv
│   │   │   ├── jMfl.mkv
│   │   │   └── sum.mkv
│   │   ├── 15_aly
│   │   │   ├── ds.jpg
│   │   │   ├── ds.mkv
│   │   │   └── jFfl.mkv
│   │   ├── 16_ad2
│   │   │   ├── Bji1.mkv
│   │   │   └── tr1ly.mkv
│   │   ├── 17_win
│   │   │   ├── cwin2.mkv
│   │   │   ├── cwin.mkv
│   │   │   ├── cwin_s.mkv
│   │   │   ├── jCfl.mkv
│   │   │   ├── jCfl_s.mkv
│   │   │   ├── nwin.mkv
│   │   │   ├── nwin_s.mkv
│   │   │   ├── pwin.mkv
│   │   │   └── pwin_s.mkv
│   │   └── 18_sbs
│   │       ├── sub2s.mkv
│   │       ├── sub2s_s.mkv
│   │       ├── sub.mkv
│   │       └── sub_s.mkv
│   ├── img
│   │   ├── debate_hd.png
│   │   ├── debate_shorts.png
│   │   ├── TrendsHD.jpg
│   │   └── TrendsShorts.jpg
│   ├── mp3
│   │   └── score.mp3
│   ├── podcast
│   │   ├── cover.png
│   │   ├── cover_s.png
│   │   ├── HFR
│   │   │   ├── 00_intro
│   │   │   │   └── Intro.mkv
│   │   │   ├── 01_ad1
│   │   │   │   ├── Bji3s.mkv
│   │   │   │   └── Bji3s_s.mkv
│   │   │   ├── 02_h0
│   │   │   │   ├── 3ER.png
│   │   │   │   ├── 3ER_s.png
│   │   │   │   ├── E9.mkv
│   │   │   │   ├── E9_s.mkv
│   │   │   │   ├── H0.mkv
│   │   │   │   ├── H0_s.mkv
│   │   │   │   ├── HF1.mkv
│   │   │   │   ├── HF1_s.mkv
│   │   │   │   ├── HF2.mkv
│   │   │   │   ├── LH1.mkv
│   │   │   │   ├── LH1_s.mkv
│   │   │   │   ├── LHH1.mkv
│   │   │   │   ├── TF0.mkv
│   │   │   │   └── THF0.mkv
│   │   │   ├── 03_g0
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── GL1.mkv
│   │   │   │   ├── GL1_s.mkv
│   │   │   │   ├── GL2.mkv
│   │   │   │   ├── GL2_s.mkv
│   │   │   │   ├── TGF0.mkv
│   │   │   │   └── TH0.mkv
│   │   │   ├── 04_h1
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── @HF1.mkv
│   │   │   │   ├── HF1_s.mkv
│   │   │   │   ├── HF2.mkv
│   │   │   │   ├── HF2_s.mkv
│   │   │   │   ├── LHH1.mkv
│   │   │   │   └── THH0.mkv
│   │   │   ├── 05_g1
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── GL1.mkv
│   │   │   │   ├── GL1_s.mkv
│   │   │   │   ├── GL2.mkv
│   │   │   │   ├── GL2_s.mkv
│   │   │   │   └── TGH0.mkv
│   │   │   ├── 06_h2
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── HF1.mkv
│   │   │   │   ├── HF1_s.mkv
│   │   │   │   ├── HF2.mkv
│   │   │   │   ├── HF2_s.mkv
│   │   │   │   └── LHH1.mkv
│   │   │   ├── 07_g2
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── GL1.mkv
│   │   │   │   ├── GL1_s.mkv
│   │   │   │   ├── GL2.mkv
│   │   │   │   └── GL2_s.mkv
│   │   │   ├── 08_h3
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── E3_s.mkv
│   │   │   │   ├── HF1.mkv
│   │   │   │   ├── HF1_s.mkv
│   │   │   │   ├── HF2.mkv
│   │   │   │   ├── HF2_s.mkv
│   │   │   │   └── LHH1.mkv
│   │   │   ├── 09_g3
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── GL1.mkv
│   │   │   │   ├── GL1_s.mkv
│   │   │   │   ├── GL2.mkv
│   │   │   │   └── GL2_s.mkv
│   │   │   ├── 10_h4
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── HF1.mkv
│   │   │   │   ├── HF1_s.mkv
│   │   │   │   ├── HF2.mkv
│   │   │   │   ├── HF2_s.mkv
│   │   │   │   ├── LHH1.mkv
│   │   │   │   └── THH0.mkv
│   │   │   ├── 11_g4
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── GL1.mkv
│   │   │   │   ├── GL1_s.mkv
│   │   │   │   ├── GL2.mkv
│   │   │   │   ├── GL2_s.mkv
│   │   │   │   └── TGH0.mkv
│   │   │   ├── 12_h5
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── HF1.mkv
│   │   │   │   ├── HF1_s.mkv
│   │   │   │   ├── HF2.mkv
│   │   │   │   ├── HF2_s.mkv
│   │   │   │   └── THH0.mkv
│   │   │   ├── 13_g5
│   │   │   │   ├── E3.mkv
│   │   │   │   ├── GL1.mkv
│   │   │   │   ├── GL1_s.mkv
│   │   │   │   ├── GL2.mkv
│   │   │   │   └── GL2_s.mkv
│   │   │   ├── 16_ad2
│   │   │   │   ├── Bji1.mkv
│   │   │   │   ├── Bji1_s.mkv
│   │   │   │   ├── Bji4s.mkv
│   │   │   │   ├── try.mkv
│   │   │   │   └── try_s.mkv
│   │   │   └── 18_sbs
│   │   │       ├── sub.mkv
│   │   │       └── sub_s.mkv
│   │   └── male
│   │       ├── 00_intro
│   │       │   ├── int5s.mkv
│   │       │   ├── int5s_s.mkv
│   │       │   └── intro.mkv
│   │       ├── 01_ad1
│   │       │   ├── Bji3s.mkv
│   │       │   └── Bji3s_s.mkv
│   │       ├── 02_p0
│   │       │   ├── 360P.png
│   │       │   ├── h01.mkv
│   │       │   ├── Std15s.mkv
│   │       │   └── std4s.mkv
│   │       ├── 03_c0
│   │       │   ├── g01.mkv
│   │       │   ├── std4s.mkv
│   │       │   └── Std7s.mkv
│   │       ├── 04_p1
│   │       │   └── h01.mkv
│   │       ├── 05_c1
│   │       │   ├── g01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 06_p2
│   │       │   └── h01.mkv
│   │       ├── 07_c2
│   │       │   ├── g01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 08_p3
│   │       │   └── h01.mkv
│   │       ├── 09_c3
│   │       │   ├── g01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 10_p4
│   │       │   ├── h01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 11_c4
│   │       │   ├── g01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 12_p5
│   │       │   ├── h01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 13_c5
│   │       │   ├── g01.mkv
│   │       │   └── std4s.mkv
│   │       ├── 16_ad2
│   │       │   ├── Bji1.mkv
│   │       │   ├── Bji1_s.mkv
│   │       │   ├── Bji4s.mkv
│   │       │   ├── try.mkv
│   │       │   └── try_s.mkv
│   │       └── 18_sbs
│   │           └── sub.mkv
│   └── voices
│       ├── matin2.wav
│       ├── matin3.mp3
│       ├── matin3.wav
│       ├── matin.wav
│       ├── RaadEn_clean.wav
│       ├── RaadEn.wav
│       └── raad.wav
├── auth_helper.py
├── cf2_resource_manager_auto.sh
├── cf2-resource-manager.desktop
├── cf2_resource_manager.sh
├── config.py
├── data
│   ├── fonts
│   ├── label_mappings.json
│   ├── lang.json
│   ├── scraping
│   │   └── url
│   │       ├── au.json
│   │       ├── bd.json
│   │       ├── ca.json
│   │       ├── cn.json
│   │       ├── eu.json
│   │       ├── in.json
│   │       ├── ir.json
│   │       ├── my.json
│   │       ├── ru.json
│   │       └── us.json
│   ├── scraping_url.json
│   ├── topic_archive.json
│   ├── topic_memory.json
│   └── weak_words.json
├── fix_duplicate_captions.py
├── get_tiktok_token.py
├── input
│   ├── clips
│   │   ├── croom.json
│   │   ├── ctutor.json
│   │   ├── @podcast_pcf.json
│   │   ├── podcast_pcf.json
│   │   └── podcast_pcm.json
│   ├── clips3d.json
│   ├── data3d.json
│   ├── dataBn.json
│   ├── data.json
│   ├── lead_stats.json
│   ├── llm_conf.json
│   ├── profile
│   │   ├── audience.json
│   │   ├── croom.json
│   │   ├── ctutor.json
│   │   ├── debate.json
│   │   ├── kidifycode.json
│   │   ├── pcf.json
│   │   ├── pcm.json
│   │   ├── travelonly.json
│   │   └── travelonly.schema1.json
│   ├── README.md
│   ├── schemas
│   │   ├── ctutor_schema.json
│   │   ├── ctutor_schema_updated.json
│   │   ├── data.schema.json
│   │   ├── data_schema_leaddata_patch.json
│   │   └── unit_classroom_config.schema.json
│   ├── score3d.json
│   ├── tts_conf.json
│   ├── unit_animation_config.json
│   ├── unit_classroom_config.json
│   ├── unit_debate_config.json
│   ├── unit_leaddata_config.json
│   ├── unit_podcast_config.json
│   ├── unit_scout_config.json
│   └── workspace.json
├── interleave_patch.py
├── linkedinScraping.py
├── linkedinScrap.py
├── Makefile
├── models
│   ├── alba_medium.onnx
│   ├── en_GB-scott-medium.onnx
│   ├── en_US-amy-medium.onnx
│   ├── en_US-lessac-medium.onnx
│   ├── flux
│   │   └── schnell
│   ├── joe_medium.onnx
│   ├── piper
│   │   ├── en_US-amy-medium.onnx
│   │   ├── en_US-amy-medium.onnx.json
│   │   ├── en_US-lessac-medium.onnx
│   │   └── en_US-lessac-medium.onnx.json
│   ├── rvc
│   ├── sdxl-lightning
│   ├── stable-diffusion
│   │   ├── Lykon_dreamshaper-8
│   │   │   ├── feature_extractor
│   │   │   │   └── preprocessor_config.json
│   │   │   ├── image.png
│   │   │   ├── model_index.json
│   │   │   ├── README.md
│   │   │   ├── safety_checker
│   │   │   │   └── config.json
│   │   │   ├── scheduler
│   │   │   │   └── scheduler_config.json
│   │   │   ├── text_encoder
│   │   │   │   └── config.json
│   │   │   ├── tokenizer
│   │   │   │   ├── merges.txt
│   │   │   │   ├── special_tokens_map.json
│   │   │   │   ├── tokenizer_config.json
│   │   │   │   └── vocab.json
│   │   │   ├── unet
│   │   │   │   └── config.json
│   │   │   └── vae
│   │   │       └── config.json
│   │   └── youtube-thumbnail
│   │       └── FLUX-youtube-thumbnails.safetensors
│   ├── stylettsz
│   └── xtts
│       ├── config.json
│       ├── dvae.pth
│       ├── hash.md5
│       ├── LICENSE.txt
│       ├── mel_stats.pth
│       ├── model.pth
│       ├── README.md
│       ├── samples
│       │   ├── de_sample.wav
│       │   ├── en_sample.wav
│       │   ├── es_sample.wav
│       │   ├── fr_sample.wav
│       │   ├── ja-sample.wav
│       │   ├── pt_sample.wav
│       │   ├── tr_sample.wav
│       │   └── zh-cn-sample.wav
│       ├── speakers_xtts.pth
│       └── vocab.json
├── playwrightScraping.py
├── __pycache__
│   └── config.cpython-311.pyc
├── pyproject.toml
├── ramcc.sh
├── Refactor
│   ├── AGENTS.md
│   ├── auth_helper.py
│   ├── cli.md
│   ├── COMPLETE_FIX_SUMMARY.md
│   ├── Crew
│   │   ├── crews.md
│   │   └── Sys.md
│   ├── DataUnitRule.md
│   ├── DebateKids.md
│   ├── debate_video3d.md
│   ├── debate_video_refactor.md
│   ├── DebatVideo3D.md
│   ├── DebatVideo.md
│   ├── debug.md
│   ├── Flow-BasedRebuildPlan.md
│   ├── flow_controller.md
│   ├── goal.md
│   ├── goal-m.md
│   ├── md2pdf.md
│   ├── merge_config.md
│   ├── PackagingRuideRule.md
│   ├── ProjectDetails.md
│   ├── README.md
│   ├── Rule.md
│   ├── run_xtts_full.py
│   ├── SCHEMA_clips_SUMMARY.md
│   ├── score.md
│   ├── Service
│   │   ├── CloneVoices
│   │   │   ├── Code.md
│   │   │   ├── pcf.md
│   │   │   ├── Plan.md
│   │   │   ├── PlanUv.md
│   │   │   ├── testBn.md
│   │   │   └── thinking.md
│   │   ├── Hologram
│   │   │   ├── OCR.Md
│   │   │   ├── PlanFinal.md
│   │   │   └── Plan.md
│   │   ├── post.md
│   │   └── ReDub
│   │       └── Think.md
│   ├── TASK_INDEX_MAP.md
│   ├── TEASER_ARGUMENTS_BEFORE_AFTER.md
│   ├── TEASER_ARGUMENTS_FIX.md
│   ├── TeaserDEPLOYMENT_GUIDE.txt
│   ├── test.py
│   ├── tree.md
│   └── Unit
│       ├── Channel.md
│       ├── ClassRoom
│       │   ├── Audio.md
│       │   ├── Ca
│       │   │   └── CountNum.md
│       │   ├── CaMathElSchool.md
│       │   ├── CharRoles.md
│       │   ├── ClassRoom.md
│       │   ├── Code
│       │   │   ├── HologramClipThink.md
│       │   │   ├── HologramPlan.md
│       │   │   ├── KidifyThink.md
│       │   │   ├── KidifyThink.pdf
│       │   │   └── Plan.md
│       │   ├── ctutor
│       │   │   ├── Plan.md
│       │   │   └── Tink.md
│       │   ├── Fund.md
│       │   ├── Story.md
│       │   ├── Student.md
│       │   ├── Teacher.md
│       │   └── Unit-Classroom.md
│       ├── Debate
│       │   ├── Plan.md
│       │   └── Rv.md
│       ├── flow_controller.md
│       ├── KidsLearn
│       │   ├── solution.md
│       │   ├── thinking2.md
│       │   ├── thinking3.md
│       │   ├── thinking4.md
│       │   ├── thinking.md
│       │   ├── Unit-KidsLearn.md
│       │   └── Unit-KidsLearn.pdf
│       ├── LeadData
│       │   ├── HotTravelBuyers.md
│       │   ├── leaddata_enrich_osint.md
│       │   ├── LeadDataPlan.md
│       │   ├── LeadDataPlan.pdf
│       │   ├── leaddata_Real_enrich_osint.md
│       │   ├── milky.md
│       │   ├── Tr
│       │   │   └── source.md
│       │   ├── TravelIntentDetection.md
│       │   ├── Travel.md
│       │   ├── Unit-DataSupport.md
│       │   ├── Unit-DataVsLeadData.md
│       │   └── Unit-DataVsLeadData.pdf
│       ├── Prodcast
│       │   ├── asset.md
│       │   ├── scripts
│       │   │   └── create_debate_shorts_symlinks.py
│       │   ├── StageDesign.md
│       │   ├── Unit-Prodcast.md
│       │   └── Unit-Prodcast.pdf
│       ├── unit_data.md
│       ├── unit_packaging.md
│       ├── UnitPlan.md
│       ├── unit_publisher.md
│       └── units.md
├── run_xtts_full.py
├── run_xtts_test.py
├── setup_voice_clone.sh
├── smoke_test.py
├── src
│   └── cf2
│       ├── cli
│       │   ├── cli.py
│       │   ├── __init__.py
│       │   └── __pycache__
│       │       ├── cli.cpython-311.pyc
│       │       └── __init__.cpython-311.pyc
│       ├── core
│       │   ├── clip_resolver.py
│       │   ├── clip_resolver.py.bak
│       │   ├── compress
│       │   │   ├── decide_compressor.py
│       │   │   ├── __init__.py
│       │   │   └── __pycache__
│       │   │       ├── decide_compressor.cpython-311.pyc
│       │   │       └── __init__.cpython-311.pyc
│       │   ├── config_loader.py
│       │   ├── dependency_resolver.py
│       │   ├── executor.py
│       │   ├── __init__.py
│       │   ├── llm_circuit.py
│       │   ├── llm_executor.py
│       │   ├── llm_resolver.py
│       │   ├── logging_setup.py
│       │   ├── parser
│       │   │   ├── debate_parser_3d.py
│       │   │   ├── debate_parser.py
│       │   │   └── md_parser.py
│       │   ├── paths.py
│       │   ├── progress_tracker.py
│       │   ├── __pycache__
│       │   │   ├── clip_resolver.cpython-311.pyc
│       │   │   ├── config_loader.cpython-311.pyc
│       │   │   ├── dependency_resolver.cpython-311.pyc
│       │   │   ├── executor.cpython-311.pyc
│       │   │   ├── __init__.cpython-311.pyc
│       │   │   ├── __init__.cpython-312.pyc
│       │   │   ├── llm_circuit.cpython-311.pyc
│       │   │   ├── llm_executor.cpython-311.pyc
│       │   │   ├── llm_resolver.cpython-311.pyc
│       │   │   ├── logging_setup.cpython-311.pyc
│       │   │   ├── paths.cpython-311.pyc
│       │   │   ├── progress_tracker.cpython-311.pyc
│       │   │   ├── registry.cpython-311.pyc
│       │   │   ├── topic_resolver.cpython-311.pyc
│       │   │   ├── utils.cpython-312.pyc
│       │   │   └── weak_words.cpython-311.pyc
│       │   ├── registry.py
│       │   ├── services
│       │   │   ├── audio_service.py
│       │   │   ├── ffmpeg_service.py
│       │   │   ├── hologram.py
│       │   │   ├── hologram.py.bak
│       │   │   ├── __pycache__
│       │   │   │   ├── audio_service.cpython-311.pyc
│       │   │   │   ├── ffmpeg_service.cpython-311.pyc
│       │   │   │   ├── hologram.cpython-311.pyc
│       │   │   │   └── tts_service.cpython-311.pyc
│       │   │   ├── tts_service.py
│       │   │   └── voice_clone
│       │   │       ├── __init__.py
│       │   │       └── xtts_service.py
│       │   ├── subtitle
│       │   │   └── subtitle_builder.py
│       │   ├── topic_resolver.py
│       │   ├── tts
│       │   │   ├── base.py
│       │   │   ├── __init__.py
│       │   │   ├── providers
│       │   │   │   ├── edge.py
│       │   │   │   ├── elevenlabs.py
│       │   │   │   ├── gtts.py
│       │   │   │   ├── __init__.py
│       │   │   │   ├── piper.py
│       │   │   │   └── __pycache__
│       │   │   │       ├── edge.cpython-311.pyc
│       │   │   │       └── __init__.cpython-311.pyc
│       │   │   ├── __pycache__
│       │   │   │   ├── base.cpython-311.pyc
│       │   │   │   ├── __init__.cpython-311.pyc
│       │   │   │   └── resolver.cpython-311.pyc
│       │   │   └── resolver.py
│       │   ├── utils.py
│       │   └── weak_words.py
│       ├── crews
│       │   ├── config
│       │   │   ├── agents.yaml
│       │   │   └── tasks.yaml
│       │   ├── crew.py
│       │   ├── crew.py.bak
│       │   ├── __init__.py
│       │   └── __pycache__
│       │       ├── crew.cpython-311.pyc
│       │       └── __init__.cpython-311.pyc
│       ├── flow_controller.py
│       ├── __init__.py
│       ├── main.md
│       ├── main.py
│       ├── meta.py
│       ├── __pycache__
│       │   ├── flow_controller.cpython-311.pyc
│       │   ├── __init__.cpython-311.pyc
│       │   ├── __init__.cpython-312.pyc
│       │   ├── main.cpython-311.pyc
│       │   └── meta.cpython-311.pyc
│       ├── tools
│       │   ├── advertise_social_share.py
│       │   ├── animation_audio.py
│       │   ├── animation_bar_merge.py
│       │   ├── animation_bar_race_audio.py
│       │   ├── animation_bar_race_video.py
│       │   ├── animation_intro_clip.py
│       │   ├── animation_merge.py
│       │   ├── animation_smart_video.py
│       │   ├── classroom_audio_builder.py
│       │   ├── classroom_pipeline.py
│       │   ├── classroom_roles_generator.py
│       │   ├── classroom_script_generator.py
│       │   ├── classroom_script_parser.py
│       │   ├── classroom_subtitle_builder.py
│       │   ├── classroom_video_renderer.py
│       │   ├── custom.py
│       │   ├── data_csv.py
│       │   ├── data_definition.py
│       │   ├── data_skip_utils.py
│       │   ├── debate_clip_resolver.txt
│       │   ├── debate_definition.py
│       │   ├── debate_dynamic_scoreboard.py
│       │   ├── debate_intro_clip.py
│       │   ├── debate_merge.py
│       │   ├── debate_pipeline.py
│       │   ├── debate_scoreboard_enhancer.py
│       │   ├── debate_score_extractor.py
│       │   ├── debate_score_renderer.py
│       │   ├── debate_subtitle_overlay.py
│       │   ├── debate_timeline_builder.py
│       │   ├── debate_topic_overlay.py
│       │   ├── debate_video3d.py
│       │   ├── debate_video.py
│       │   ├── debate_video_renderer.py
│       │   ├── definition_video.py
│       │   ├── __init__.py
│       │   ├── leaddata_collect.py
│       │   ├── leaddata_enrich_osint.py
│       │   ├── leaddata_export.py
│       │   ├── leaddata_normalize.py
│       │   ├── leaddata_reddit.py
│       │   ├── leaddata_score.py
│       │   ├── leaddata_travel_intent.py
│       │   ├── packaging_yt_metadata.py
│       │   ├── packaging_yt_narration.py
│       │   ├── packaging_yt_thumbnail.py
│       │   ├── prodcast_pipeline.py
│       │   ├── prodcast_publish_helper.py
│       │   ├── prodcast_script_generator.py
│       │   ├── prodcast_timeline_builder.py
│       │   ├── prodcast_video_generator.py
│       │   ├── prodcast_voice_generator.py
│       │   ├── publisher_fb_upload.py
│       │   ├── publisher_yt_shared.py
│       │   ├── publisher_yt_upload.py
│       │   ├── __pycache__
│       │   │   ├── advertise_social_share.cpython-311.pyc
│       │   │   ├── animation_audio.cpython-311.pyc
│       │   │   ├── animation_bar_merge.cpython-311.pyc
│       │   │   ├── animation_bar_race_audio.cpython-311.pyc
│       │   │   ├── animation_bar_race_video.cpython-311.pyc
│       │   │   ├── animation_intro_clip.cpython-311.pyc
│       │   │   ├── animation_merge.cpython-311.pyc
│       │   │   ├── animation_smart_video.cpython-311.pyc
│       │   │   ├── classroom_audio_builder.cpython-311.pyc
│       │   │   ├── classroom_script_generator.cpython-311.pyc
│       │   │   ├── classroom_subtitle_builder.cpython-311.pyc
│       │   │   ├── classroom_video_renderer.cpython-311.pyc
│       │   │   ├── custom.cpython-311.pyc
│       │   │   ├── data_csv.cpython-311.pyc
│       │   │   ├── data_definition.cpython-311.pyc
│       │   │   ├── data_skip_utils.cpython-311.pyc
│       │   │   ├── debate_definition.cpython-311.pyc
│       │   │   ├── debate_merge.cpython-311.pyc
│       │   │   ├── debate_subtitle_overlay.cpython-311.pyc
│       │   │   ├── debate_timeline_builder.cpython-311.pyc
│       │   │   ├── debate_topic_overlay.cpython-311.pyc
│       │   │   ├── debate_video.cpython-311.pyc
│       │   │   ├── debate_video_renderer.cpython-311.pyc
│       │   │   ├── definition_video.cpython-311.pyc
│       │   │   ├── __init__.cpython-311.pyc
│       │   │   ├── leaddata_collect.cpython-311.pyc
│       │   │   ├── leaddata_export.cpython-311.pyc
│       │   │   ├── leaddata_normalize.cpython-311.pyc
│       │   │   ├── leaddata_reddit.cpython-311.pyc
│       │   │   ├── leaddata_score.cpython-311.pyc
│       │   │   ├── packaging_yt_metadata.cpython-311.pyc
│       │   │   ├── packaging_yt_narration.cpython-311.pyc
│       │   │   ├── packaging_yt_thumbnail.cpython-311.pyc
│       │   │   ├── prodcast_pipeline.cpython-311.pyc
│       │   │   ├── prodcast_timeline_builder.cpython-311.pyc
│       │   │   ├── prodcast_video_generator.cpython-311.pyc
│       │   │   ├── prodcast_voice_generator.cpython-311.pyc
│       │   │   ├── publisher_fb_upload.cpython-311.pyc
│       │   │   ├── publisher_yt_shared.cpython-311.pyc
│       │   │   ├── publisher_yt_upload.cpython-311.pyc
│       │   │   └── scout_trend.cpython-311.pyc
│       │   ├── scout_queue_helper.py
│       │   └── scout_trend.py
│       └── units
│           ├── __init__.py
│           ├── __pycache__
│           │   ├── __init__.cpython-311.pyc
│           │   ├── unit_classroom.cpython-311.pyc
│           │   ├── unit_data.cpython-311.pyc
│           │   ├── unit_leaddata.cpython-311.pyc
│           │   └── unit_prodcast.cpython-311.pyc
│           ├── unit_advertise.py
│           ├── unit_animation.py
│           ├── unit_classroom.py
│           ├── unit_comparison.py
│           ├── unit_data.py
│           ├── unit_debate.py
│           ├── unit_definition.py
│           ├── unit_leaddata.py
│           ├── unit_packaging.py
│           ├── unit_prodcast.py
│           ├── unit_publisher.py
│           └── unit_scout.py
├── svaigCld.py
├── test_gtts.py
├── test_stealth.py
├── torch
├── torchaudio
└── uv.lock

149 directories, 632 files
matin@mhpz:/var/POAi/CrewAiFlow/cf2$


=================================================================================

{
  "_comment": "Video Factory configuration schema. Unit master switches (Unit-Scout, Unit-Data, etc.) gate entire pipelines. All nested *_config blocks are only read when the parent Unit-* switch is true.",
  "topic": {
    "type": "string",
    "description": "Topic for video (e.g., 'Programming Language', 'AI Frameworks'). Can be a debate motion when Unit-Debate=true. When packaging_config.video_style=[\"ytid\"], set this to a YouTube video ID (e.g. 'WnS4zE4wOtQ') — the metadata tool fetches title/description/tags from that existing video. Set to 'auto' to let the scout pipeline pick the next topic from the output queue automatically (requires Unit-Scout=true).",
    "example": "Programming Language",
    "example_ytid": "WnS4zE4wOtQ",
    "special_values": {
      "auto": "Pull next queued topic from scout output queue. Requires Unit-Scout=true and a populated queue. The scout writes candidate topics to a JSON queue file; 'auto' pops the top-ranked entry and uses it as the topic for this run."
    }
  },
  "start": {
    "type": "integer",
    "description": "Start year for data range",
    "example": 2015
  },
  "end": {
    "type": "integer",
    "description": "End year for data range",
    "example": 2026
  },
  "granularity": {
    "type": "string",
    "description": "Data granularity",
    "enum": [
      "yearly",
      "monthly",
      "daily"
    ],
    "example": "yearly"
  },
  "video_formats": {
    "type": "array",
    "description": "Video formats to generate. Applies to all tools: bar_race, intro, definition_video, debate_video.",
    "enum": [
      "HD",
      "2K",
      "4K",
      "8K",
      "Shorts",
      "ShortsHD",
      "Shorts4K"
    ],
    "example": [
      "Shorts",
      "HD"
    ]
  },
  "video_style": {
    "type": "array",
    "description": "Top-level video style tag(s) used by the packaging pipeline. Mirrors packaging_config.video_style and controls which branch the metadata tool takes. Valid values: 'debate', 'bar_race', 'animation', 'ytid'.",
    "enum": [
      "debate",
      "bar_race",
      "animation",
      "ytid"
    ],
    "example": [
      "debate"
    ]
  },
  "fps": {
    "type": "number",
    "description": "Seconds per period for bar_race videos. Controls animation pace — higher = slower/longer video.",
    "minimum": 0.1,
    "maximum": 30.0,
    "examples": {
      "0.5": "~6s total (12 periods × 0.5s)",
      "1.0": "~12s total",
      "2.0": "~24s total",
      "5.0": "~60s total",
      "10.0": "~120s total"
    }
  },
  "fps_hd_offset": {
    "type": "number",
    "description": "Extra seconds per period for HD only. Shorts uses fps; HD uses fps + fps_hd_offset.",
    "minimum": 0.0,
    "maximum": 10.0,
    "example": 1.37,
    "tip": "fps=4.9 + fps_hd_offset=1.37 → Shorts=4.9s/period, HD=6.27s/period"
  },
  "video_fps": {
    "type": "integer",
    "description": "Output frame rate for ALL video tools (intro, bar_race, definition_video, debate_video). Must be identical across all tools — mismatched fps causes A/V sync failure on merge.",
    "enum": [
      24,
      30,
      60
    ],
    "default": 30,
    "example": 30,
    "tip": "30fps recommended. Never mix fps values — all segment tools read this single field."
  },
  "audio_speed": {
    "type": "number",
    "description": "Speech speed for Shorts audio via ffmpeg atempo. 1.0=normal, <1.0=slower, >1.0=faster.",
    "minimum": 0.5,
    "maximum": 2.0,
    "example": 1.1,
    "tip": "1.1 = slightly faster. Good for Shorts where narration must be concise."
  },
  "audio_speed_hd": {
    "type": "number",
    "description": "Speech speed for HD audio only. Set 0.0 to fall back to audio_speed for all formats.",
    "minimum": 0.0,
    "maximum": 2.0,
    "examples": {
      "0.0": "No override — HD uses same speed as audio_speed",
      "0.9": "Slightly slower than Shorts — good for longer HD narration",
      "1.0": "Normal speed for HD"
    }
  },
  "tts_engine": {
    "type": "string",
    "description": "TTS engine used for ALL video audio generation (definition_video, debate_video, and future tools). Set once here — applies globally.",
    "enum": [
      "gtts",
      "edge-tts",
      "piper"
    ],
    "default": "gtts",
    "example": "edge-tts",
    "options": {
      "gtts": "Google Text-to-Speech. Free, offline-friendly. Install: pip install gTTS",
      "edge-tts": "Microsoft Edge Neural TTS. High-quality neural voices. Install: pip install edge-tts. Uses edge_tts_voices config. Falls back to gtts if not installed.",
      "piper": "Local offline neural TTS via ONNX models. Fastest, no internet needed. Install: pip install piper-tts. Uses piper_voices config. Falls back to gtts if not installed."
    }
  },
  "audio_lang": {
    "type": "string",
    "description": "Language code for gTTS narration (non-debate audio tools: bar_race, definition_video). Only applies when tts_engine=gtts.",
    "default": "en",
    "example": "en",
    "tip": "Use standard BCP-47 codes: 'en', 'fr', 'de', 'es', 'zh', etc."
  },
  "audio_tld": {
    "type": "string",
    "description": "Top-level domain for gTTS accent selection. Only applies when tts_engine=gtts and audio_lang=en.",
    "default": "com",
    "example": "com",
    "options": {
      "com": "US English (default)",
      "co.uk": "British English",
      "com.au": "Australian English",
      "co.in": "Indian English",
      "ca": "Canadian English"
    }
  },
  "use_label_mappings": {
    "type": "boolean",
    "description": "Apply label_mappings.json to shorten bar names (e.g. 'JavaScript' → 'JS').",
    "example": false
  },
  "channel": {
    "type": "string",
    "description": "Channel name used in audio narration, intro clip, agent backstory, and metadata. No @ prefix.",
    "example": "PlayOwnAi"
  },
  "channel_lower": {
    "type": "string",
    "description": "Lowercase channel slug used in LinkedIn and other platform URLs.",
    "example": "playownai"
  },
  "website": {
    "type": "string",
    "description": "Channel website or primary URL shown in YouTube metadata.",
    "example": "youtube.com/@PlayOwnAi"
  },
  "watermark_enabled": {
    "type": "boolean",
    "description": "Overlay semi-transparent watermark text on video frames.",
    "example": true
  },
  "watermark_text": {
    "type": "string",
    "description": "Watermark text displayed on video. Usually '@ChannelName'.",
    "example": "@PlayOwnAi"
  },
  "watermark_opacity": {
    "type": "integer",
    "description": "Watermark opacity: 0=invisible, 255=fully opaque. 60=subtle, 160=visible.",
    "minimum": 0,
    "maximum": 255,
    "example": 60
  },
  "_section_unit_switches": "════════════════════════════════════════",
  "_unit_switches_comment": "Master pipeline switches. Set false to hard-skip that unit — no lock, no meta check, no execution.",
  "Unit-Scout": {
    "type": "boolean",
    "description": "Master switch for Unit-Scout. When true, scans configured platforms and niches for viral/trending content and populates a topic queue. When topic='auto', the next queued topic is consumed automatically. When false, scout_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "Unit-Data": {
    "type": "boolean",
    "description": "Master switch for Unit-Data. Generates all base content: CSV data, debate scripts (.md), definition text. All other content units depend on its output. When false, unit is skipped entirely.",
    "default": true,
    "example": true
  },
  "Unit-LeadData": {
    "type": "boolean",
    "description": "Master switch for Unit-LeadData. Collects business leads from Google Maps (via SerpAPI) using the topic as keyword(s) — comma-separate for multiple keywords. Normalizes phone/email/URL, deduplicates, scores quality 0–100, segments hot/warm/cold, and exports CSV/JSON. When false, leaddata_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": true
  },
  "Unit-Debate": {
    "type": "boolean",
    "description": "Master switch for Unit-Debate. Renders debate video from propose.md + oppose.md + decide.md produced by Unit-Data. When false, debate_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": true
  },
  "Unit-Definition": {
    "type": "boolean",
    "description": "Master switch for Unit-Definition. Renders scrolling definition video from definition .md files produced by Unit-Data. When false, unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "Unit-Animation": {
    "type": "boolean",
    "description": "Master switch for Unit-Animation. Renders bar race and other animation videos from CSV produced by Unit-Data. When false, animation_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "Unit-Comparison": {
    "type": "boolean",
    "description": "Master switch for Unit-Comparison. Generates comparison content. When false, unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "Unit-Packaging": {
    "type": "boolean",
    "description": "Master switch for Unit-Packaging. Generates YouTube metadata (title, description, tags, translations), CC subtitles, and thumbnails — everything needed to package the video before upload. When false, packaging_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "Unit-Publisher": {
    "type": "boolean",
    "description": "Master switch for Unit-Publisher. Uploads final videos to YouTube and/or Facebook. Requires Unit-Packaging output to exist. When false, publisher_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "Unit-Advertise": {
    "type": "boolean",
    "description": "Master switch for Unit-Advertise. Creates promotional derivatives (Shorts cuts, social clips, TVC) from finished videos and posts to social platforms. When false, advertise_config is ignored and the unit is skipped entirely.",
    "default": false,
    "example": false
  },
  "leaddata_config_file": {
    "type": "string",
    "description": "Path to external Unit-LeadData config JSON. Auto-loaded by config_loader (Rule 37) and injected as inputs['leaddata_config']. The referenced file's content IS the leaddata_config block — no outer wrapper needed (same pattern as clips3d.json).",
    "example": "input/unit_leaddata_config.json"
  },
  "_section_scout": "════════════════════════════════════════",
  "scout_config": {
    "type": "object",
    "description": "Trend Scout pipeline settings. Only read when Unit-Scout=true.",
    "properties": {
      "force_scraping": {
        "type": "boolean",
        "description": "Force URL scraping even if cached results exist. Useful to refresh stale data.",
        "default": false,
        "example": false
      },
      "platforms": {
        "type": "array",
        "description": "Platforms to scout for trending topics. 'scraping_url' triggers scraping from URLs defined in scraping_url file.",
        "items": {
          "type": "string",
          "enum": [
            "scraping_url",
            "YouTube",
            "Facebook",
            "LinkedIn",
            "instagram"
          ]
        },
        "example": [
          "scraping_url",
          "YouTube",
          "Facebook",
          "LinkedIn",
          "instagram"
        ]
      },
      "niches": {
        "type": "array",
        "description": "Topic niches / keywords to filter trending content by. Only posts/videos matching these themes are considered.",
        "items": {
          "type": "string"
        },
        "example": [
          "Ai",
          "LLM",
          "GenAi"
        ]
      },
      "min_virality_score": {
        "type": "integer",
        "description": "Minimum virality score (0–100) a candidate topic must reach to be added to the queue. Higher = stricter filtering.",
        "minimum": 0,
        "maximum": 100,
        "default": 75,
        "example": 75
      },
      "output_queue_size": {
        "type": "integer",
        "description": "Maximum number of topics to keep in the output queue at once. Oldest entries are evicted when the queue is full.",
        "minimum": 1,
        "maximum": 100,
        "default": 10,
        "example": 10
      },
      "auto_consume": {
        "type": "boolean",
        "description": "When true and topic='auto', automatically pop the top-ranked topic from the queue and set it as the run topic without manual intervention.",
        "default": true,
        "example": true
      },
      "llm_scout": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for the trend scout agent used to score and rank candidate topics. null=project default.",
        "example": "deepseek/deepseek-chat"
      },
      "use_web_search": {
        "type": "boolean",
        "description": "Allow the scout agent to perform live web searches to validate and enrich candidate topics before scoring.",
        "default": true,
        "example": true
      },
      "scraping_url": {
        "type": "string",
        "description": "Path to a JSON file listing URLs to scrape for trending content. Used when 'scraping_url' is included in platforms.",
        "default": "data/scraping_url.json",
        "example": "data/scraping_url.json"
      },
      "social_credentials_file": {
        "type": "string",
        "description": "Path to social platform credentials JSON for reading platform feeds (LinkedIn, Instagram, etc.).",
        "default": "input/social_credentials.json",
        "example": "input/social_credentials.json"
      },
      "fb_credentials_file": {
        "type": "string",
        "description": "Path to Facebook credentials JSON for reading Facebook Page/Group feeds.",
        "default": "input/fb_credentials.json",
        "example": "input/fb_credentials.json"
      },
      "yt_client_secrets_file": {
        "type": "string",
        "description": "Path to YouTube OAuth2 client_secrets.json for reading YouTube trending data.",
        "default": "input/client_secrets.json",
        "example": "input/client_secrets.json"
      },
      "yt_token_file": {
        "type": "string",
        "description": "Path to saved YouTube OAuth2 token. Auto-created after first browser login.",
        "default": "input/token.json",
        "example": "input/token.json"
      }
    }
  },
  "_section_leaddata": "════════════════════════════════════════",
  "leaddata_config": {
    "type": "object",
    "description": "Lead data collection pipeline settings. Only read when Unit-LeadData=true. Topic field provides search keywords (comma-separated for multiple). Pipeline: collect → normalize → score → export.",
    "properties": {
      "enabled": {
        "type": "boolean",
        "description": "Inner enable flag. When false, the unit returns 'disabled' even if Unit-LeadData=true. Useful for keeping the config block intact while temporarily disabling.",
        "default": true,
        "example": true
      },
      "sources": {
        "type": "array",
        "description": "Lead data sources to query. 'maps' = Google Maps via SerpAPI (primary). 'csv' = local CSV at input/leads.csv (fallback for testing).",
        "items": {
          "type": "string",
          "enum": [
            "maps",
            "csv"
          ]
        },
        "default": [
          "maps"
        ],
        "example": [
          "maps"
        ]
      },
      "collect_config": {
        "type": "object",
        "description": "Lead collection settings. Controls how raw leads are fetched from external sources.",
        "properties": {
          "credentials_file": {
            "type": "string",
            "description": "Filename of SerpAPI credentials JSON. Resolved to .runtime/secrets/{filename}. File content: { \"api_key\": \"...\" }. Never commit.",
            "default": "serpapi_credentials.json",
            "example": "serpapi_credentials.json"
          },
          "api_endpoint": {
            "type": "string",
            "description": "SerpAPI search endpoint. Override only if using a regional/proxy mirror.",
            "default": "https://serpapi.com/search.json",
            "example": "https://serpapi.com/search.json"
          },
          "engine": {
            "type": "string",
            "description": "SerpAPI engine. 'google_maps' returns local_results with phone/address/website/coordinates.",
            "enum": [
              "google_maps"
            ],
            "default": "google_maps",
            "example": "google_maps"
          },
          "search_type": {
            "type": "string",
            "description": "Maps search subtype. 'search' = standard place search.",
            "enum": [
              "search"
            ],
            "default": "search",
            "example": "search"
          },
          "request_timeout": {
            "type": "integer",
            "description": "HTTP request timeout in seconds for each SerpAPI call.",
            "minimum": 5,
            "maximum": 120,
            "default": 30,
            "example": 30
          },
          "max_results_per_keyword": {
            "type": "integer",
            "description": "Maximum number of leads to extract per keyword. SerpAPI returns up to 20 local_results per call.",
            "minimum": 1,
            "maximum": 20,
            "default": 20,
            "example": 20
          },
          "skip_if_cached": {
            "type": "boolean",
            "description": "When true and raw/leads_raw.csv already exists in the workspace, skip the collect step and reuse the cached file. Set false to force a fresh fetch.",
            "default": true,
            "example": true
          }
        }
      },
      "normalize_config": {
        "type": "object",
        "description": "Normalization and deduplication settings. Standardizes phone/email/URL formatting and removes duplicate leads.",
        "properties": {
          "deduplicate_on": {
            "type": "array",
            "description": "Field(s) used to detect duplicate leads via hash key. Most reliable: ['phone']. Stricter: ['phone', 'email'].",
            "items": {
              "type": "string",
              "enum": [
                "phone",
                "email",
                "name",
                "website"
              ]
            },
            "default": [
              "phone"
            ],
            "example": [
              "phone"
            ]
          },
          "phone_country_default": {
            "type": "string",
            "description": "Country prefix to prepend to phones missing a '+'. Empty string = prepend '+' only. Format: '+971' for UAE, '+880' for BD, etc.",
            "default": "",
            "example": "+971"
          },
          "lowercase_email": {
            "type": "boolean",
            "description": "Force email addresses to lowercase before storing. Disable only if you need raw casing preserved.",
            "default": true,
            "example": true
          },
          "force_https": {
            "type": "boolean",
            "description": "Prepend 'https://' to website URLs missing a scheme. When false, prepends 'http://' instead.",
            "default": true,
            "example": true
          },
          "strip_unicode": {
            "type": "boolean",
            "description": "Apply NFD unicode normalization to text fields (name, address, location, category) for consistent searchability.",
            "default": true,
            "example": true
          },
          "min_name_length": {
            "type": "integer",
            "description": "Reject leads whose normalized name is shorter than this many characters. Filters out junk results.",
            "minimum": 0,
            "maximum": 50,
            "default": 2,
            "example": 2
          }
        }
      },
      "score_config": {
        "type": "object",
        "description": "Quality scoring and segmentation settings. Each lead gets a 0–100 score based on data completeness, then bucketed into hot/warm/cold.",
        "properties": {
          "score_enabled": {
            "type": "boolean",
            "description": "When false, all leads receive score=0 and segment='cold'. Useful for skipping scoring on already-scored datasets.",
            "default": true,
            "example": true
          },
          "scoring_rubric": {
            "type": "object",
            "description": "Point values awarded for each present field. Sum is capped at 100.",
            "properties": {
              "has_phone": {
                "type": "integer",
                "description": "Points awarded when phone is present.",
                "minimum": 0,
                "maximum": 100,
                "default": 20
              },
              "has_email": {
                "type": "integer",
                "description": "Points awarded when email is present.",
                "minimum": 0,
                "maximum": 100,
                "default": 20
              },
              "has_website": {
                "type": "integer",
                "description": "Points awarded when website is present.",
                "minimum": 0,
                "maximum": 100,
                "default": 20
              },
              "has_address": {
                "type": "integer",
                "description": "Points awarded when address is present (proxy for premium/verified location).",
                "minimum": 0,
                "maximum": 100,
                "default": 20
              },
              "active_business": {
                "type": "integer",
                "description": "Points awarded when last_verified timestamp exists (active record).",
                "minimum": 0,
                "maximum": 100,
                "default": 20
              }
            },
            "example": {
              "has_phone": 20,
              "has_email": 20,
              "has_website": 20,
              "has_address": 20,
              "active_business": 20
            }
          },
          "segment_thresholds": {
            "type": "object",
            "description": "Score boundaries for each segment. score >= hot → 'hot'; score >= warm → 'warm'; otherwise → 'cold'.",
            "properties": {
              "hot": {
                "type": "integer",
                "description": "Minimum score for hot segment (ready to contact).",
                "minimum": 0,
                "maximum": 100,
                "default": 70
              },
              "warm": {
                "type": "integer",
                "description": "Minimum score for warm segment (nurture).",
                "minimum": 0,
                "maximum": 100,
                "default": 40
              },
              "cold": {
                "type": "integer",
                "description": "Minimum score for cold segment. Always 0.",
                "minimum": 0,
                "maximum": 100,
                "default": 0
              }
            },
            "example": {
              "hot": 70,
              "warm": 40,
              "cold": 0
            }
          },
          "sort_by_score_desc": {
            "type": "boolean",
            "description": "Sort scored CSV/JSON output by quality_score descending (highest first). Disable to preserve collection order.",
            "default": true,
            "example": true
          }
        }
      },
      "export_config": {
        "type": "object",
        "description": "Output formatting and statistics settings.",
        "properties": {
          "formats": {
            "type": "array",
            "description": "Final export formats. CSV is always written; 'json' adds a parallel JSON file. Reserved: 'jsonl', 'parquet'.",
            "items": {
              "type": "string",
              "enum": [
                "csv",
                "json"
              ]
            },
            "default": [
              "csv",
              "json"
            ],
            "example": [
              "csv",
              "json"
            ]
          },
          "generate_stats": {
            "type": "boolean",
            "description": "Generate insights/lead_stats.json with totals, fill rates, and segment breakdown. Disable to skip the analytics step.",
            "default": true,
            "example": true
          },
          "stats_file": {
            "type": "string",
            "description": "Filename for the stats JSON written to insights/. Override only if multiple runs share an insights directory.",
            "default": "lead_stats.json",
            "example": "lead_stats.json"
          },
          "include_segments_breakdown": {
            "type": "boolean",
            "description": "When true, add a per-segment count map ({hot:N, warm:N, cold:N}) to the stats file.",
            "default": true,
            "example": true
          }
        }
      }
    }
  },
  "_section_animation": "════════════════════════════════════════",
  "animation_config": {
    "type": "object",
    "description": "Animation pipeline settings. Only read when Unit-Animation=true.",
    "properties": {
      "animation_styles": {
        "type": "array",
        "description": "Animation styles for standard video_producer.",
        "enum": [
          "bar",
          "line",
          "bubble",
          "pie",
          "stream",
          "map",
          "bar_race"
        ],
        "example": [
          "bar_race"
        ]
      },
      "use_existing_csv": {
        "type": "boolean",
        "description": "Skip research+CSV generation and use existing output/{filename}.csv. Auto-generates if CSV missing.",
        "example": false
      },
      "definition_enabled": {
        "type": "boolean",
        "description": "Generate plain-English topic definition saved to output/{filename}.txt.",
        "example": true
      },
      "use_existing_definition": {
        "type": "boolean",
        "description": "Use existing output/{filename}.txt instead of generating a new one.",
        "example": false
      },
      "definition_max_chars": {
        "type": "integer",
        "description": "Maximum characters for the topic definition text.",
        "minimum": 300,
        "maximum": 3000,
        "default": 1200,
        "example": 1500
      },
      "definition_video": {
        "type": "boolean",
        "description": "Create scrolling text video from definition .txt file. Output: definition_video_{fmt}_with_audio.mp4.",
        "example": true
      },
      "intro_enabled": {
        "type": "boolean",
        "description": "Generate branded intro clip for the animation pipeline. Output: intro_{fmt}_with_audio.mp4. Controlled independently per pipeline block — does not affect debate intro.",
        "example": true
      },
      "intro_duration": {
        "type": "integer",
        "description": "Intro clip duration in seconds for Shorts/portrait formats (animation pipeline).",
        "minimum": 1,
        "maximum": 60,
        "example": 7
      },
      "intro_duration_hd": {
        "type": "integer",
        "description": "Intro clip duration in seconds for HD/landscape formats (animation pipeline). Set 0 to use intro_duration for all.",
        "minimum": 0,
        "maximum": 60,
        "example": 10
      },
      "bar_race_video_enabled": {
        "type": "boolean",
        "description": "Generate bar race video. Output: bar_race_{fmt}_with_audio.mp4.",
        "example": true
      },
      "bar_race_audio_enabled": {
        "type": "boolean",
        "description": "Generate TTS audio narration specifically for bar race videos. Reads CSV data to create data-driven commentary synced to the animation. Output: bar_race_{fmt}_audio.mp3 and bar_race_cc_en.txt. Independent of audio_enabled.",
        "default": false,
        "example": true
      },
      "bar_merge_enabled": {
        "type": "boolean",
        "description": "Concatenate intro + bar_race + definition_video into final video per format. Output: {channel}_{topic_slug}_{fmt}.mp4.",
        "example": true,
        "note": "All 3 segment _with_audio.mp4 files must exist and have identical video_fps."
      },
      "video_enabled": {
        "type": "boolean",
        "description": "Enable standard video generation via smart_video_tool.",
        "example": false
      },
      "audio_enabled": {
        "type": "boolean",
        "description": "Enable audio narration for standard (non-bar-race) videos.",
        "example": false
      },
      "merge_audio_video": {
        "type": "boolean",
        "description": "Merge standard audio with standard video files.",
        "example": false
      },
      "llm_researcher": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for data_researcher agent. null=project default.",
        "example": "deepseek/deepseek-chat"
      },
      "llm_definition": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for definition_specialist agent. null=project default.",
        "example": "deepseek/deepseek-chat"
      },
      "llm_csv": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for csv_generator agent. null=project default.",
        "example": "deepseek/deepseek-chat"
      },
      "llm_video": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for video_producer and bar_race_video_producer agents. null=project default.",
        "example": "ollama/llama3.1:8b"
      },
      "llm_audio": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for audio_engineer agent. null=project default.",
        "example": "ollama/deepseek-r1:1.5b"
      },
      "intro_slug": {
        "type": "string",
        "description": "Custom subtitle line shown in the animation intro clip. Replaces the default second line of the intro.",
        "example": "Watch Race how the leaders change over time"
      }
    }
  },
  "_section_debate": "════════════════════════════════════════",
  "debate_config": {
    "type": "object",
    "description": "Debate pipeline settings. Only read when Unit-Debate=true.",
    "properties": {
      "use_label_mappings": {
        "type": "boolean",
        "description": "Apply label_mappings.json to shorten bar names in debate context (e.g. 'JavaScript' → 'JS'). Mirrors the top-level use_label_mappings but scoped to the debate pipeline only.",
        "default": false,
        "example": true
      },
      "debate_definition_enabled": {
        "type": "boolean",
        "description": "Generate debate text (propose.md, oppose.md, decide.md) via LLM agents. Smart skip: if all 3 .md files already exist, LLM generation is skipped automatically.",
        "example": true
      },
      "debate_video_enabled": {
        "type": "boolean",
        "description": "Render debate video from propose.md + oppose.md + decide.md. Output: debate_video_{fmt}_with_audio.mp4.",
        "example": true
      },
      "debate_3d_enabled": {
        "type": "boolean",
        "description": "Render the debate video using a 3D scene/effect instead of the standard 2D scrolling text layout. When true, the debate_video_tool switches to a 3D rendering mode. Requires additional dependencies.",
        "default": false,
        "example": false
      },
      "debate_merge_enabled": {
        "type": "boolean",
        "description": "Concatenate debate_video segments into final video per format. Output: {channel}_{topic_slug}_{fmt}.mp4.",
        "example": true,
        "note": "Requires debate_video_{fmt}_with_audio.mp4 to exist."
      },
      "intro_slug": {
        "type": "string",
        "description": "Custom subtitle line shown in the debate intro clip (if intro_enabled=true). Replaces the default second line.",
        "example": "One of the biggest debates in tech right now"
      },
      "intro_enabled": {
        "type": "boolean",
        "description": "Generate branded intro clip for the debate pipeline. Output: intro_{fmt}_with_audio.mp4. Controlled independently per pipeline block — does not affect animation intro.",
        "default": false,
        "example": true
      },
      "intro_duration": {
        "type": "integer",
        "description": "Intro clip duration in seconds for Shorts/portrait formats (debate pipeline).",
        "minimum": 1,
        "maximum": 60,
        "example": 7
      },
      "intro_duration_hd": {
        "type": "integer",
        "description": "Intro clip duration in seconds for HD/landscape formats (debate pipeline). Set 0 to use intro_duration for all.",
        "minimum": 0,
        "maximum": 60,
        "example": 10
      },
      "debate_secs_per_line": {
        "type": "number",
        "description": "Seconds each line is shown as active in the debate video.",
        "minimum": 0.5,
        "maximum": 10.0,
        "default": 3.5,
        "examples": {
          "2.0": "Fast pace",
          "3.5": "Default — comfortable reading speed",
          "5.0": "Slow — good for complex arguments"
        }
      },
      "debate_max_chars": {
        "type": "integer",
        "description": "Maximum characters for each debate section (propose, oppose, decide). Hard cap applied by DebateDefinitionTool.",
        "minimum": 500,
        "maximum": 50000,
        "default": 10000,
        "example": 1000
      },
      "llm_debate": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for debater and judge agents. null=project default.",
        "examples": {
          "null": "Use project default model",
          "deepseek/deepseek-chat": "Cost-effective, strong reasoning",
          "dashscope/qwen-plus": "Good for debate-style structured text",
          "openai/gpt-4o": "Best argument quality",
          "anthropic/claude-3-5-sonnet": "Excellent balanced reasoning"
        },
        "example": "dashscope/qwen-plus"
      },
      "piper_voices": {
        "type": "object",
        "description": "Per-role voice config for tts_engine=piper. Only read when tts_engine=piper. Install: pip install piper-tts. Download models from https://huggingface.co/rhasspy/piper-voices",
        "properties": {
          "propose": {
            "type": "object",
            "description": "Voice for PROPOSITION section.",
            "properties": {
              "model": {
                "type": "string",
                "example": "models/joe_medium.onnx"
              },
              "speed": {
                "type": "number",
                "default": 1.0,
                "example": 1.05
              },
              "pitch": {
                "type": "number",
                "default": 0,
                "example": 0.5
              }
            }
          },
          "oppose": {
            "type": "object",
            "description": "Voice for OPPOSITION section.",
            "properties": {
              "model": {
                "type": "string",
                "example": "models/alba_medium.onnx"
              },
              "speed": {
                "type": "number",
                "default": 1.0,
                "example": 1.05
              },
              "pitch": {
                "type": "number",
                "default": 0,
                "example": -0.5
              }
            }
          },
          "decide": {
            "type": "object",
            "description": "Voice for VERDICT section.",
            "properties": {
              "model": {
                "type": "string",
                "example": "models/en_GB-scott-medium.onnx"
              },
              "speed": {
                "type": "number",
                "default": 1.0,
                "example": 1.0
              },
              "pitch": {
                "type": "number",
                "default": 0,
                "example": 0
              }
            }
          }
        }
      },
      "edge_tts_voices": {
        "type": "object",
        "description": "Per-role neural voice config for tts_engine=edge-tts. 5 roles: propose, oppose, judge_f (Female Judge/SUMMARY), judge_m (Male Judge/ANALYSIS), decide (Chief Judge/DECISION).",
        "properties": {
          "propose": {
            "type": "object",
            "description": "Voice for PROPOSITION section.",
            "properties": {
              "edge_voice": {
                "type": "string",
                "example": "en-US-GuyNeural"
              }
            }
          },
          "oppose": {
            "type": "object",
            "description": "Voice for OPPOSITION section.",
            "properties": {
              "edge_voice": {
                "type": "string",
                "example": "en-US-AriaNeural"
              }
            }
          },
          "decide": {
            "type": "object",
            "description": "Voice for DECISION section — Chief Judge. Declares the winner. Used for mod_verdict block.",
            "properties": {
              "edge_voice": {
                "type": "string",
                "example": "en-GB-RyanNeural"
              }
            }
          },
          "judge_f": {
            "type": "object",
            "description": "Voice for SUMMARY section — Female Judge. Reads both sides summary. Recommended: en-CA-ClaraNeural (Canadian, ~35, neutral).",
            "properties": {
              "edge_voice": {
                "type": "string",
                "example": "en-CA-ClaraNeural"
              }
            }
          },
          "judge_m": {
            "type": "object",
            "description": "Voice for ANALYSIS section — Male Judge. Provides analytical commentary. Recommended: en-CA-LiamNeural (Canadian, ~35, neutral).",
            "properties": {
              "edge_voice": {
                "type": "string",
                "example": "en-CA-LiamNeural"
              }
            }
          }
        }
      },
      "debate_bg_opacity": {
        "type": "integer",
        "description": "Background image opacity for debate video overlay. 0=transparent, 255=opaque.",
        "minimum": 0,
        "maximum": 255,
        "default": 150,
        "example": 150
      },
      "debate_background_enabled": {
        "type": "boolean",
        "description": "Generate an AI-created background image and composite it behind the debate text. Requires image_gen_backend to be configured.",
        "default": false,
        "example": false
      },
      "debate_background_prompt": {
        "type": "string",
        "description": "Text prompt for AI background image generation. Keep cinematic and abstract — avoid text, people, and faces.",
        "example": "futuristic digital debate arena, dark navy deep purple, abstract geometric circuit patterns, soft volumetric light beams, blurred bokeh background, cinematic, no text, no people, no faces"
      },
      "_clips_folder_structure": {
        "type": "documentation",
        "description": "Debate video clips folder structure when _folder_prefix=true. Each segment has a numbered folder (00-18) containing HD and Shorts variants.",
        "base_path": "assets/clips/",
        "folders": {
          "00_intro": {
            "files": [
              "intro.mkv",
              "intro_s.mkv"
            ],
            "key": "intro",
            "desc": "Welcome/channel intro"
          },
          "01_ad1": {
            "files": [
              "Bji000.mkv",
              "Bji000_s.mkv"
            ],
            "key": "ad1/ads1",
            "desc": "Primary sponsor ad (pre-debate)"
          },
          "02_p0": {
            "files": [
              "360D.png",
              "360D_s.png",
              "p0fl.mkv",
              "p0fl_s.mkv"
            ],
            "key": "p0",
            "desc": "Opening - Proposition",
            "note": "PNG for static intro"
          },
          "03_c0": {
            "files": [
              "c0fl.mkv",
              "c0fl_s.mkv"
            ],
            "key": "c0",
            "desc": "Opening - Opposition"
          },
          "04_p1": {
            "files": [
              "p0fl.mkv",
              "p0fl_s.mkv"
            ],
            "key": "p1",
            "desc": "Arg 1 - Proposition"
          },
          "05_c1": {
            "files": [
              "c0fl.mkv",
              "c0fl_s.mkv"
            ],
            "key": "c1",
            "desc": "Counter-Arg 1 - Opposition"
          },
          "06_p2": {
            "files": [
              "p0fl.mkv",
              "p0fl_s.mkv"
            ],
            "key": "p2",
            "desc": "Arg 2 - Proposition"
          },
          "07_c2": {
            "files": [
              "c0fl.mkv",
              "c0fl_s.mkv"
            ],
            "key": "c2",
            "desc": "Counter-Arg 2 - Opposition"
          },
          "08_p3": {
            "files": [
              "p0fl.mkv",
              "p0fl_s.mkv"
            ],
            "key": "p3",
            "desc": "Arg 3 - Proposition (Shorts max)"
          },
          "09_c3": {
            "files": [
              "c0fl.mkv",
              "c0fl_s.mkv"
            ],
            "key": "c3",
            "desc": "Counter-Arg 3 - Opposition (Shorts max)"
          },
          "10_p4": {
            "files": [
              "p0fl.mkv",
              "p0fl_s.mkv"
            ],
            "key": "p4",
            "desc": "Arg 4 - Proposition (HD only)"
          },
          "11_c4": {
            "files": [
              "c0fl.mkv",
              "c0fl_s.mkv"
            ],
            "key": "c4",
            "desc": "Counter-Arg 4 - Opposition (HD only)"
          },
          "12_p5": {
            "files": [
              "p0fl.mkv",
              "p0fl_s.mkv"
            ],
            "key": "p5",
            "desc": "Arg 5 - Proposition (HD only)"
          },
          "13_c5": {
            "files": [
              "c0fl.mkv",
              "c0fl_s.mkv"
            ],
            "key": "c5",
            "desc": "Counter-Arg 5 - Opposition (HD only)"
          },
          "14_sum": {
            "files": [
              "jMfl.mkv",
              "jMfl_s.mkv"
            ],
            "key": "sum",
            "desc": "SUMMARY - Male Judge",
            "voice": "judge_m (en-CA-LiamNeural)"
          },
          "15_aly": {
            "files": [
              "jFfl.mkv",
              "jFfl_s.mkv"
            ],
            "key": "aly/anly",
            "desc": "ANALYSIS - Female Judge",
            "voice": "judge_f (en-CA-ClaraNeural)"
          },
          "16_ad2": {
            "files": [
              "Bji1.mkv",
              "Bji1_s.mkv"
            ],
            "key": "ad2/ads2",
            "desc": "Secondary sponsor ad (post-debate)"
          },
          "17_win": {
            "files": [
              "cwin.mkv",
              "cwin_s.mkv",
              "cwin2.mkv",
              "cwin2_s.mkv",
              "jCfl.mkv",
              "jCfl_s.mkv",
              "jCfl_sh.mp4",
              "pwin.mkv",
              "pwin_s.mkv"
            ],
            "key": "win",
            "desc": "DECISION - Chief Judge",
            "voice": "decide (en-US-ChristopherNeural)"
          },
          "18_sbs": {
            "files": [
              "sub.mkv",
              "sub_s.mkv"
            ],
            "key": "sbs/subscribe",
            "desc": "Subscribe/outro CTA"
          }
        },
        "naming": {
          "HD": "filename.mkv (e.g., intro.mkv, p0fl.mkv)",
          "Shorts": "filename_s.mkv (e.g., intro_s.mkv, p0fl_s.mkv)",
          "static": "filename.png (for intro frames)"
        },
        "lookup_mechanism": "When _folder_prefix=true, scans assets/clips/ for folders ending with _{key}. E.g., 'sum' finds '14_sum', 'intro' finds '00_intro'. Falls back to assets/clips/{key}/ if not found.",
        "pipeline_usage": {
          "Shorts": "Uses p0-p3, c0-c3 (max 4 args per side)",
          "HD": "Uses p0-p5, c0-c5 (max 6 args per side)"
        }
      },
      "image_gen_backend": {
        "type": "string",
        "description": "Backend for AI image generation when debate_background_enabled=true.",
        "enum": [
          "auto",
          "replicate",
          "stability",
          "openai",
          "local"
        ],
        "default": "auto",
        "example": "auto",
        "options": {
          "auto": "Tries backends in order: replicate → stability → openai → local",
          "replicate": "Replicate API (REPLICATE_API_TOKEN required)",
          "stability": "Stability AI API (STABILITY_API_KEY required)",
          "openai": "OpenAI DALL-E (OPENAI_API_KEY required)",
          "local": "Local diffusion model (requires local setup)"
        }
      },
      "debate_mini_enabled": {
        "type": "boolean",
        "description": "Generate short/mini debate version (-m.md files) for Shorts format. When true, debate_propose_m / debate_oppose_m / debate_decide_m tasks run to produce compressed debate scripts.",
        "default": false,
        "example": true
      },
      "debate_mini_max_chars": {
        "type": "integer",
        "description": "Maximum characters for each mini debate section (-m.md files used for Shorts). Should be significantly smaller than debate_max_chars.",
        "minimum": 200,
        "maximum": 10000,
        "default": 4000,
        "example": 4000
      },
      "debate_3d_clips": {
        "type": "object",
        "description": "Background clip configuration for the 3D debate renderer (debate_3d_enabled=true). Maps each pipeline segment key to one or more video/image sources. Supports multi-clip sequences with intro paths (played once) and loop clips (cycled indefinitely). Config is the single source of truth — no static fallback directories.",
        "format_note": "All path values are relative to PROJECT_ROOT. Missing files resolve to None — renderer shows placeholder frame.",
        "clip_entry_formats": {
          "plain_string": {
            "description": "Single clip, loops forever.",
            "example": "assets/clips/p0/clip.mkv"
          },
          "single_path_loop": {
            "description": "Intro clip plays once, then loop clip cycles.",
            "example": {
              "path": "intro.mkv",
              "loop": "loop.mkv"
            }
          },
          "multi_path_loop": {
            "description": "Multiple intro clips each played once in order, then loops cycled.",
            "example": {
              "paths": [
                "clip_a.mkv",
                "clip_b.mkv"
              ],
              "loops": [
                "loop_a.mkv",
                "loop_b.mkv"
              ]
            }
          },
          "image_with_frames": {
            "description": "Static image held for exactly N frames, then advances to next path entry.",
            "example": {
              "src": "assets/img/stage.png",
              "frames": 90
            }
          },
          "mixed_paths": {
            "description": "Image intro (held 90 frames) followed by video clip, then loop.",
            "example": {
              "paths": [
                {
                  "src": "assets/img/stage.png",
                  "frames": 90
                },
                "assets/clips/clip.mkv"
              ],
              "loops": [
                "assets/clips/clip.mkv"
              ]
            }
          }
        },
        "image_support": {
          "extensions": [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".bmp",
            ".tiff",
            ".tif"
          ],
          "frames_default": 90,
          "frames_note": "IMAGE_DEFAULT_HOLD=90 frames (~3s at 30fps). Override per entry with frames key."
        },
        "special_keys": {
          "intro": {
            "description": "Intro clip with optional subtext subtitle. Plays when intro_enabled=true or when clip config path exists. Must include subtext for subtitle overlay.",
            "format": {
              "path": "string",
              "subtext": "string (optional)"
            }
          },
          "ads_primary": {
            "description": "Ad clip played after intro. Set null to disable. Must include subtext.",
            "format": {
              "path": "string",
              "subtext": "string (optional)"
            }
          },
          "ads_secondary": {
            "description": "Ad clip played before mod_verdict. Must include subtext.",
            "format": {
              "path": "string",
              "subtext": "string (optional)"
            }
          },
          "subscribe": {
            "description": "Subscribe CTA clip played last. Must include subtext.",
            "format": {
              "path": "string",
              "subtext": "string (optional)"
            }
          },
          "p0_to_p5": {
            "description": "Proposition argument background clips. p0=opening, p1-p5=arguments. Shorts uses p0-p3; HD uses p0-p5. Missing keys render placeholder frame."
          },
          "c0_to_c5": {
            "description": "Opposition argument background clips. c0=opening, c1-c5=arguments."
          },
          "mod_summary": {
            "description": "Background for Female Judge SUMMARY section (## SUMMARY in decide.md). Voice: judge_f (en-CA-ClaraNeural)."
          },
          "mod_analysis": {
            "description": "Background for Male Judge ANALYSIS section (## ANALYSIS in decide.md). Voice: judge_m (en-CA-LiamNeural)."
          },
          "mod_verdict": {
            "description": "Background for Chief Judge DECISION section (## DECISION in decide.md). Voice: decide (en-US-ChristopherNeural)."
          }
        },
        "pipeline_order": {
          "Shorts": [
            "intro",
            "ads_primary",
            "p0",
            "c0",
            "p1",
            "c1",
            "p2",
            "c2",
            "p3",
            "c3",
            "mod_summary",
            "mod_analysis",
            "ads_secondary",
            "mod_verdict",
            "subscribe"
          ],
          "HD": [
            "intro",
            "ads_primary",
            "p0",
            "c0",
            "p1",
            "c1",
            "p2",
            "c2",
            "p3",
            "c3",
            "p4",
            "c4",
            "p5",
            "c5",
            "mod_summary",
            "mod_analysis",
            "ads_secondary",
            "mod_verdict",
            "subscribe"
          ]
        },
        "properties": {
          "Shorts": {
            "type": "object",
            "description": "Clip map for Shorts format (1080x1920 portrait). All block clips use TTS audio — no subtext needed. Only intro, ads, subscribe use subtext.",
            "example": {
              "intro": {
                "path": "assets/clips/intro/intro_Shorts01_En.mkv",
                "subtext": "Welcome 360Debate! See Every Side, Decide Smarter."
              },
              "ads_primary": null,
              "p0": {
                "paths": [
                  {
                    "src": "assets/img/360D_Stage1080x1920.png",
                    "frames": 90
                  },
                  "assets/clips/pro/pro1_fl_short.mkv"
                ],
                "loops": [
                  "assets/clips/pro/pro1_fl_short.mkv"
                ]
              },
              "c0": {
                "paths": [
                  {
                    "src": "assets/img/360D_Stage1080x1920.png",
                    "frames": 90
                  },
                  "assets/clips/op/op1_fl_short.mkv"
                ],
                "loops": [
                  "assets/clips/op/op1_fl_short.mkv"
                ]
              },
              "p1": {
                "paths": [
                  "assets/clips/pro/pro1_fl_short.mkv"
                ],
                "loops": [
                  "assets/clips/pro/pro1_fl_short.mkv"
                ]
              },
              "c1": {
                "paths": [
                  "assets/clips/op/op1_fl_short.mkv"
                ],
                "loops": [
                  "assets/clips/op/op1_fl_short.mkv"
                ]
              },
              "mod_summary": {
                "paths": [
                  "assets/clips/jf/jf1_fl_short.mkv"
                ],
                "loops": [
                  "assets/clips/jf/jf1_fl_short.mkv"
                ]
              },
              "mod_analysis": {
                "paths": [
                  "assets/clips/jm/jm1_fl_short.mkv"
                ],
                "loops": [
                  "assets/clips/jm/jm1_fl_short.mkv"
                ]
              },
              "ads_secondary": {
                "path": "assets/clips/adsp/Ads_short.mkv",
                "subtext": "Sponsored message here."
              },
              "mod_verdict": {
                "paths": [
                  "assets/clips/mv/short_judge_verdict_opp.mkv"
                ],
                "loops": [
                  "assets/clips/mv/short_judge_verdict_opp.mkv"
                ]
              },
              "subscribe": {
                "path": "assets/clips/sbc/subscribe_shorts.mkv",
                "subtext": "Subscribe for more!"
              }
            }
          },
          "HD": {
            "type": "object",
            "description": "Clip map for HD format (1920x1080 landscape). Same structure as Shorts with additional p4/c4/p5/c5 keys.",
            "example": {
              "intro": {
                "path": "assets/clips/intro/intro_HD01_En.mkv",
                "subtext": "Welcome 360Debate! Full-Length Debate!"
              },
              "ads_primary": {
                "path": "assets/clips/adsp/Ads_hd.mkv",
                "subtext": "Brought to you by sponsor."
              },
              "p0": {
                "paths": [
                  {
                    "src": "assets/img/360D_Stage1920x1080.png",
                    "frames": 90
                  },
                  "assets/clips/pro/pro1_fl.mkv"
                ],
                "loops": [
                  "assets/clips/pro/pro1_fl.mkv"
                ]
              },
              "c0": {
                "paths": [
                  {
                    "src": "assets/img/360D_Stage1920x1080.png",
                    "frames": 90
                  },
                  "assets/clips/op/op1_fl.mkv"
                ],
                "loops": [
                  "assets/clips/op/op1_fl.mkv"
                ]
              },
              "p1": {
                "paths": [
                  "assets/clips/pro/pro1_fl.mkv"
                ],
                "loops": [
                  "assets/clips/pro/pro1_fl.mkv"
                ]
              },
              "c1": {
                "paths": [
                  "assets/clips/op/op1_fl.mkv"
                ],
                "loops": [
                  "assets/clips/op/op1_fl.mkv"
                ]
              },
              "mod_summary": {
                "paths": [
                  "assets/clips/jf/jf1_fl.mkv"
                ],
                "loops": [
                  "assets/clips/jf/jf1_fl.mkv"
                ]
              },
              "mod_analysis": {
                "paths": [
                  "assets/clips/jm/jm1_fl.mkv"
                ],
                "loops": [
                  "assets/clips/jm/jm1_fl.mkv"
                ]
              },
              "ads_secondary": {
                "path": "assets/clips/adsp/Ads_hd2.mkv",
                "subtext": "Sponsored message here."
              },
              "mod_verdict": {
                "paths": [
                  "assets/clips/mv/hd_judge_verdict_opp.mkv"
                ],
                "loops": [
                  "assets/clips/mv/hd_judge_verdict_opp.mkv"
                ]
              },
              "subscribe": {
                "path": "assets/clips/sbc/subscribe_hd.mkv",
                "subtext": "Subscribe for more HD content!"
              }
            }
          }
        }
      }
    }
  },
  "_section_lang": "════════════════════════════════════════",
  "lang_suffix": {
    "type": "string",
    "description": "Auto-injected at runtime from CLI flag (e.g. -bn → 'Bn'). Do NOT set this manually in data.json — it is always derived from the CLI flag. Defaults to 'En' when no flag is given.",
    "example": "En",
    "runtime_values": {
      "crewai run": "En  (default)",
      "crewai run -bn": "Bn",
      "crewai run -fr": "Fr",
      "crewai run -ar": "Ar",
      "crewai run -de": "De",
      "crewai run -es": "Es",
      "crewai run -zh": "Zh"
    },
    "affects": [
      "propose_{lang}.md / oppose_{lang}.md / decide_{lang}.md",
      "intro_{fmt}_{lang}.mp4 / intro_{fmt}_{lang}_with_audio.mp4 / intro_{fmt}_{lang}_cc.txt",
      "debate_video_{fmt}_{lang}.mp4 / debate_video_{fmt}_{lang}_with_audio.mp4 / debate_video_{fmt}_{lang}_cc.txt",
      "{channel}_Debate_{topic_slug}_{fmt}_{lang}.mp4",
      "{channel}_Debate_{topic_slug}_{fmt}_{lang}_cc.txt"
    ]
  },
  "_lang_override_files": {
    "description": "To run in a different language, create input/dataXx.json (where Xx = capitalized ISO code). Only fields that differ from data.json need to be included — the override is deep-merged on top of data.json.",
    "convention": "input/data{Lang}.json — e.g. dataBn.json, dataFr.json, dataAr.json",
    "cli": "crewai run -{xx}  — e.g.  crewai run -bn  |  crewai run -fr  |  crewai run -ar",
    "minimal_override_example": {
      "_comment": "Bengali override — only fields that differ from data.json",
      "tts_engine": "edge-tts",
      "debate_config": {
        "edge_tts_voices": {
          "propose": {
            "edge_voice": "bn-BD-NabanitaNeural"
          },
          "oppose": {
            "edge_voice": "bn-BD-PradeepNeural"
          },
          "decide": {
            "edge_voice": "bn-IN-TanishaaNeural"
          }
        }
      }
    },
    "supported_edge_tts_voices_by_lang": {
      "Bengali (bn)": [
        "bn-BD-NabanitaNeural",
        "bn-BD-PradeepNeural",
        "bn-IN-TanishaaNeural",
        "bn-IN-BashkarNeural"
      ],
      "French (fr)": [
        "fr-FR-DeniseNeural",
        "fr-FR-HenriNeural",
        "fr-CA-SylvieNeural",
        "fr-CA-JeanNeural"
      ],
      "Arabic (ar)": [
        "ar-SA-ZariyahNeural",
        "ar-SA-HamedNeural",
        "ar-EG-SalmaNeural",
        "ar-EG-ShakirNeural"
      ],
      "German (de)": [
        "de-DE-KatjaNeural",
        "de-DE-ConradNeural",
        "de-AT-IngridNeural"
      ],
      "Spanish (es)": [
        "es-ES-ElviraNeural",
        "es-ES-AlvaroNeural",
        "es-MX-DaliaNeural",
        "es-MX-JorgeNeural"
      ],
      "Chinese (zh)": [
        "zh-CN-XiaoxiaoNeural",
        "zh-CN-YunxiNeural",
        "zh-TW-HsiaoChenNeural"
      ],
      "Hindi (hi)": [
        "hi-IN-SwaraNeural",
        "hi-IN-MadhurNeural"
      ],
      "Japanese (ja)": [
        "ja-JP-NanamiNeural",
        "ja-JP-KeitaNeural"
      ],
      "Korean (ko)": [
        "ko-KR-SunHiNeural",
        "ko-KR-InJoonNeural"
      ],
      "Portuguese (pt)": [
        "pt-BR-FranciscaNeural",
        "pt-BR-AntonioNeural",
        "pt-PT-RaquelNeural"
      ]
    }
  },
  "_section_packaging": "════════════════════════════════════════",
  "packaging_config": {
    "type": "object",
    "description": "Metadata & thumbnail preparation settings. Only read when Unit-Packaging=true. Generates YouTube metadata (title, description, tags, CC subtitles, translations) and AI thumbnail — everything needed to package the video before upload.",
    "properties": {
      "video_style": {
        "type": "array",
        "description": "Pipeline type to generate metadata for. Controls which branch the metadata tool takes.",
        "enum": [
          "debate",
          "bar_race",
          "animation",
          "ytid"
        ],
        "example": [
          "debate"
        ],
        "enum_notes": {
          "debate": "Generates metadata from debate pipeline output files",
          "bar_race": "Generates metadata from bar race animation output",
          "animation": "Generates metadata from standard animation pipeline",
          "ytid": "Fetches metadata from an existing YouTube video — set topic to the video ID (e.g. 'WnS4zE4wOtQ')"
        }
      },
      "generate_youtube_metadata": {
        "type": "boolean",
        "description": "Generate YouTube metadata (title, description, tags, chapters) and translate to 31 languages. Output: YT/{fmt}/MD/ and YT/{fmt}/CC/.",
        "example": true
      },
      "generate_thumbnail": {
        "type": "boolean",
        "description": "Generate AI thumbnail image for YouTube. Output: {topic_slug}.jpg and {topic_slug}.png in output/{slug}/YT/{fmt}/Th/. Alias: generate_yt_thumbnail also accepted.",
        "example": true
      },
      "generate_yt_thumbnail": {
        "type": "boolean",
        "description": "Alias for generate_thumbnail. Use generate_thumbnail instead.",
        "example": true
      },
      "yt_metadata_lang": {
        "type": "string",
        "description": "Number of languages to generate YouTube metadata translations (title, description) for. String-encoded integer.",
        "default": "35",
        "example": "50"
      },
      "yt_cc_lang": {
        "type": "string",
        "description": "Number of languages to generate CC subtitle translations for. String-encoded integer.",
        "default": "20",
        "example": "50"
      },
      "video_formats": {
        "type": "array",
        "description": "Video format subdirectory names to generate metadata for. Use 'debate' for debate pipeline output.",
        "example": [
          "debate"
        ],
        "note": "Use ['HD','Shorts'] for animation pipeline, ['debate'] for debate pipeline."
      },
      "llm_youtube": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for youtube_metadata_specialist agent. null=project default.",
        "example": "ollama/qwen2.5:latest"
      }
    }
  },
  "_section_publisher": "════════════════════════════════════════",
  "publisher_config": {
    "type": "object",
    "description": "Upload destination settings. Only read when Unit-Publisher=true. Sub-blocks (yt_upload_config, fb_upload_config) controlled by their own yt_upload / fb_upload switches.",
    "properties": {
      "llm_upload": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for youtube_upload_specialist agent. null=project default.",
        "example": "ollama/qwen2.5-coder:3b"
      },
      "llm_embed": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for embedding tasks (semantic search). null=project default.",
        "example": "ollama/nomic-embed-text:latest"
      },
      "yt_upload": {
        "type": "boolean",
        "description": "Enable YouTube upload sub-block.",
        "default": false,
        "example": false
      },
      "yt_upload_config": {
        "type": "object",
        "description": "YouTube upload settings. Only active when yt_upload=true.",
        "properties": {
          "upload_youtube_video": {
            "type": "boolean",
            "description": "Upload final merged videos to YouTube via Data API v3. Smart skip: if upload_log.json already contains video_id, re-upload is skipped.",
            "example": true,
            "note": "Requires client_secrets.json from Google Cloud Console. First run opens browser for OAuth2 login."
          },
          "upload_dry_run": {
            "type": "boolean",
            "description": "Dry run mode — validates that video files, metadata, and CC files exist without uploading anything to YouTube. No API calls made. Useful for testing before real upload.",
            "default": false,
            "example": true
          },
          "upload_privacy": {
            "type": "string",
            "description": "YouTube video privacy on upload.",
            "enum": [
              "private",
              "unlisted",
              "public"
            ],
            "default": "private",
            "example": "private",
            "tip": "Use 'private' to review before publishing."
          },
          "upload_category_id": {
            "type": "string",
            "description": "YouTube category ID.",
            "default": "28",
            "example": "28",
            "enum_reference": {
              "22": "People & Blogs",
              "27": "Education",
              "28": "Science & Technology",
              "24": "Entertainment",
              "25": "News & Politics"
            }
          },
          "upload_cc": {
            "type": "boolean",
            "description": "Upload CC subtitle files from YT/{fmt}/CC/ to YouTube after video upload. Covers all 31 languages.",
            "default": true,
            "example": true
          },
          "upload_cc_lang": {
            "type": "string",
            "description": "Max number of CC subtitle languages to upload to YouTube (0 or omit = upload all). String-encoded integer. Independent from yt_cc_lang (generation count).",
            "default": "0",
            "example": "5"
          },
          "upload_md_lang": {
            "type": "string",
            "description": "Max number of MD localization languages to upload to YouTube (0 or omit = upload all). String-encoded integer. Independent from yt_metadata_lang (generation count).",
            "default": "0",
            "example": "35"
          },
          "upload_notify_subscribers": {
            "type": "boolean",
            "description": "Notify channel subscribers when video is uploaded. Recommended false for private/unlisted.",
            "default": false,
            "example": false
          },
          "upload_client_secrets_file": {
            "type": "string",
            "description": "Path to OAuth2 client_secrets.json from Google Cloud Console.",
            "default": "input/client_secrets.json",
            "example": "input/client_secrets.json",
            "setup": "https://console.cloud.google.com → APIs & Services → Credentials → Create OAuth 2.0 Client ID → Desktop App → Download JSON"
          },
          "upload_token_file": {
            "type": "string",
            "description": "Path to saved OAuth2 token. Auto-created after first browser login. Reused on subsequent runs.",
            "default": "input/token.json",
            "example": "input/token.json"
          },
          "yt_pin_comment_gen": {
            "type": "boolean",
            "description": "Auto-generate and pin a comment on the video after upload using LLM.",
            "default": false,
            "example": true
          }
        }
      },
      "fb_upload": {
        "type": "boolean",
        "description": "Enable Facebook upload sub-block.",
        "default": false,
        "example": true
      },
      "fb_upload_config": {
        "type": "object",
        "description": "Facebook upload settings. Only active when fb_upload=true. Shorts → Facebook Reel. HD → Facebook Video. Smart skip: if fb_upload_log.json already contains video_id, re-upload is skipped.",
        "properties": {
          "upload_facebook_video": {
            "type": "boolean",
            "description": "Upload video directly to Facebook Page via Graph API.",
            "example": true,
            "note": "Requires input/fb_credentials.json with page_id and access_token."
          },
          "privacy_status": {
            "type": "string",
            "description": "Facebook video privacy level.",
            "enum": [
              "SELF",
              "FRIENDS",
              "EVERYONE"
            ],
            "default": "SELF",
            "example": "SELF",
            "tip": "Use SELF (only me) for testing before setting EVERYONE for public."
          },
          "credentials_file": {
            "type": "string",
            "description": "Path to Facebook credentials JSON. Must contain page_id and access_token.",
            "default": "input/fb_credentials.json",
            "example": "input/fb_credentials.json"
          }
        }
      }
    }
  },
  "_section_advertise": "════════════════════════════════════════",
  "advertise_config": {
    "type": "object",
    "description": "Social sharing and promotional derivative settings. Only read when Unit-Advertise=true. Posts the YouTube video URL as a link post to configured platforms — completely independent of publisher/fb_upload. Reads upload_log.json directly.",
    "properties": {
      "social_share_enabled": {
        "type": "boolean",
        "description": "Post uploaded YouTube video URL + thumbnail to configured social platforms.",
        "example": true
      },
      "social_share_dry_run": {
        "type": "boolean",
        "description": "Simulate social posts without actually posting. Logs what would be posted.",
        "default": false,
        "example": false
      },
      "social_platforms": {
        "type": "array",
        "description": "Platforms to post to. Credentials read from input/social_credentials.json.",
        "enum": [
          "Facebook",
          "LinkedIn",
          "X",
          "YouTube",
          "Instagram"
        ],
        "example": [
          "LinkedIn",
          "Instagram",
          "Facebook"
        ],
        "tip": "Facebook here = link post to FB Page (not a video upload). YouTube posts a Community post. Instagram requires a publicly accessible image URL."
      },
      "schedule_post": {
        "type": "boolean",
        "description": "Wait until schedule_datetime before posting to social platforms. The crew sleeps in 60-second chunks with countdown logs until the target time is reached. If the scheduled time has already passed, posts immediately.",
        "default": false,
        "example": true
      },
      "schedule_datetime": {
        "type": "string",
        "description": "Target date and time to post. Interpreted in schedule_timezone.",
        "format": "YYYY-MM-DD HH:MM:SS",
        "example": "2026-03-15 18:00:00"
      },
      "schedule_timezone": {
        "type": "string",
        "description": "IANA timezone string for schedule_datetime. Used with Python's zoneinfo module (Python 3.9+).",
        "default": "UTC",
        "example": "Asia/Dhaka",
        "common_values": {
          "UTC": "Coordinated Universal Time",
          "Asia/Dhaka": "Bangladesh Standard Time (UTC+6)",
          "Asia/Kolkata": "India Standard Time (UTC+5:30)",
          "Asia/Dubai": "Gulf Standard Time (UTC+4)",
          "Europe/London": "GMT / BST (UTC+0 / UTC+1)",
          "Europe/Berlin": "CET / CEST (UTC+1 / UTC+2)",
          "America/New_York": "Eastern Time (UTC-5 / UTC-4)",
          "America/Los_Angeles": "Pacific Time (UTC-8 / UTC-7)",
          "Asia/Tokyo": "Japan Standard Time (UTC+9)",
          "Australia/Sydney": "Australian Eastern Time (UTC+10 / UTC+11)"
        }
      },
      "llm_social": {
        "type": [
          "string",
          "null"
        ],
        "description": "LLM for social_share_specialist agent. null=project default.",
        "example": "ollama/nomic-embed-text:latest"
      }
    }
  },
  "_section_llm_reference": "════════════════════════════════════════",
  "_llm_examples": {
    "description": "LLM string format reference for all llm_* fields",
    "format": "provider/model-name",
    "examples": {
      "null": "Use project default (from .env or agents.yaml)",
      "openai/gpt-4o": "OpenAI GPT-4o — best quality",
      "openai/gpt-4o-mini": "OpenAI GPT-4o Mini — fast and cheap",
      "anthropic/claude-3-5-sonnet": "Claude 3.5 Sonnet — excellent reasoning",
      "deepseek/deepseek-chat": "DeepSeek — cost-effective, strong instruction following",
      "dashscope/qwen-plus": "Alibaba Qwen Plus — good for structured text",
      "ollama/llama3.1:8b": "Local Ollama — llama3.1 8B",
      "ollama/qwen2.5:latest": "Local Ollama — Qwen 2.5",
      "ollama/deepseek-r1:1.5b": "Local Ollama — DeepSeek R1 1.5B (very fast)"
    }
  },
  "intro_enabled": {
    "type": "boolean",
    "description": "DEPRECATED at top level. Set inside animation_config and/or debate_config instead. Each pipeline block controls its own intro independently — intro_enabled=true in an active block triggers the intro clip for that pipeline only. OR logic: if any active block has intro_enabled=true, the intro runs.",
    "example": false
  },
  "intro_duration": {
    "type": "integer",
    "description": "DEPRECATED at top level. Set inside animation_config and/or debate_config instead.",
    "minimum": 0,
    "maximum": 60,
    "example": 7
  },
  "intro_duration_hd": {
    "type": "integer",
    "description": "DEPRECATED at top level. Set inside animation_config and/or debate_config instead. Set 0 to use intro_duration for all formats.",
    "minimum": 0,
    "maximum": 60,
    "example": 10
  }
}
=================================================================================
# 🎬 CF2 (CrewAI Factory Flow) — Complete Engineering Rules

> **Each token counts. No fluff. Every rule is enforceable.**

---

## 📑 INDEX

- **Section 1 — Flow Rules**
  - Rule 1 · `main.py` → Router Only · `flow_controller.py` → Brain of System
  - Rule 2 · One Unit Per Execution
- **Section 2 — Unit Rules**
  - Rule 3 · `Unit-*` → Execution Blocks · `subUnit-*` → Micro Tasks (camelCase)
  - Rule 4 · `subUnit-*` → Pure Functions (Reusable Micro-Tasks)
- **Section 3 — Unit-Data Rules (Critical)**
  - Rule 5 · Unit-Data is a Provider, Never a Consumer · Unit-Data Never Calls Itself
  - Rule 6 · Unit-Data is Never Called Directly · Task Selection Controlled by Unit Switches Only
  - Rule 7 · Core Tasks Always Run · Consumer-Specific Tasks Only Run for Enabled Units · Output Files Are the Contract
- **Section 4 — Consumer Unit Rules**
  - Rule 8 · Consumer Units → Read-Only
  - Rule 9 · `Unit-Publisher` → Distribution Layer Only
  - Rule 10 · `Unit-Advertise` → Promotion Layer Only
- **Section 5 —  Core `Service` ,LLM & others Rules**
  - Rule 11 · Core Services → tts, ffmpeg, audio, video, 3d, hologram, clips
  - Rule 12 · Core Others / Utility Elements
  - Rule 13 · Centralized LLM Config
- **Section 6 — Crew / Agent Rules**
  - Rule 14 · Crew → Execution Tool Only
  - Rule 15 · Factory Pattern Only
  - Rule 16 · Task = Single Output
- **Section 7 — File System Rules**
  - Rule 17 · File System → Single Source of Truth
  - Rule 18 · Folder Structure → Topic-Based Workspace
  - Rule 19 · No Hardcoded Paths
  - Rule 20 · Idempotent Writes
  - Rule 39 · `.runtime/` → System-Only Directory
- **Section 8 — Meta / Control Rules**
  - Rule 21 · Slug Rule → Predictable PascalCase Naming
  - Rule 22 · Collision Rule → `__01` Suffix System
  - Rule 23 · `meta.json` → Unit State Brain
  - Rule 24 · Smart Skip → Zero Waste Execution
  - Rule 25 · Lock System → Crash Safety
  - Rule 26 · `flow_controller.py` is the ONLY Entry Into Units
- **Section 9 —All Config Rules**
  - Rule 27 · Topics , Focus , profile → One File Per Channel
  - Rule 28 · `unit_config.json` is units config
  - Rule 29 · except Config ,No Hardcoded Values in py code  
  - Rule 30 · Config = Control, Not Logic (Schema-Enforced)
- **Section 10 — Code Quality Rules**
  - Rule 31 · Function Design → 50–80 Lines Max
  - Rule 32 · Smart Skip is Mandatory in Every Tool
  - Rule 33 · Output Naming Convention → Predictable File Names
- **Section 11 — System Config  Rules (`config.py`)**
  - Rule 34 · `config.py` is a Re-Export Layer — No Logic Allowed
  - Rule 35 · `PATHS` Dict → Canonical Key Names Only
  - Rule 36 · `slugify()` Stop-Word List is Canonical
  - Rule 37 · `resolve_config_paths()` → Routing Logic is Fixed
  - Rule 38 · `read_meta()` Must Not Use Collision Slug for Existing Topics
- **Section 12 — Anti-Patterns (Enforce Zero Tolerance)**
  - Rule 39 · Banned Anti-Patterns — Zero Exceptions
  - Rule 40 · Final Mental Model

---

## 🧠 CORE PROBLEM (Why We Rebuilt)

The old CrewAI system failed because:
- ❌ Too many agents + tasks crammed into one place
- ❌ Manual chaining → impossible to control at scale
- ❌ Repeated execution → wasted time & API cost
- ❌ 1000+ line files → unmaintainable
- ❌ Tight coupling → everything depends on everything
- ❌ Units → one unit fails Entire system failures
- ❌ Units → already 12+ units not insist new unit
- ❌ subUnits → no limits add/remove

---

## 🎯 CORE GOAL

Build a **Flow-based Modular Pipeline** that is simple, modular, skippable, debuggable, scalable & multi-channel.

---

## 🔥 GOLDEN PRINCIPLE

> **Flow controls logic — Units do work — Files store truth — Config defines identity**

---

## 🏗️ Final Structure Reference

```
src/cf2/
  main.py                  ← Router only (dumb)
  flow_controller.py       ← All logic lives here
  meta.py                  ← meta.json read/write helpers
  dependency_resolver.py   ← Auto-triggers Unit-Data if inputs missing
  units/
    unit_data.py
    unit_debate.py
    unit_definition.py
    unit_animation.py
    unit_comparison.py
    unit_publisher.py
    unit_advertise.py
  crews/
    crew.py                ← Tool registry + agent/task factory
    config/
      agents.yaml
      tasks.yaml
  tools/
    *.py                   ← One tool per file, smart skip mandatory

.runtime/             ← machine-managed, never committed to git
  logs/
  secrets/
  cache/
  output/             ← all topic workspaces live here
    {TopicSlug}/
      debate/
      definition/
      animation/
      comparison/
      YT/
      .lock
      meta.json
```

---

# 🧩 SECTION 1 — FLOW RULES

## Rule 1 · Universal main,FlowController , Topic & units  responsibilities

**Principle:** `main.py` routes → `flow_controller` decides → Topic is normalized once → Units execute consistently
- no redundancy, no structure break

---

## Rule 1.a · `main.py` → Router Only (Dumb & Simple)

`main.py` must be **dumb & simple**. The single test: delete everything except `from cf2.flow_controller import run` — if the system still works, the router is clean.

**✅ Allowed:**
- Parse CLI arguments / profile flag
- Hand off to `flow_controller.run()`

**❌ Forbidden:**
- Business logic of any kind
- File / meta / state access (`load_meta`, `check_output_folder`, `read_csv`)
- Crew or agent calls
- Conditional flow decisions (`if unit == "debate": ...`)
- Multi-unit execution (`run("Unit-Data"); run("Unit-Debate")`)
- Error handling / retry logic (belongs in FlowController)
- Config or env loading (`load_dotenv`, `read_yaml`)
- Parameter transformation (`argv[1].lower().replace(...)`)
- Any import except the single flow entry point

```python
# ✅ Entire main.py
from cf2.flow_controller import run

def kickoff():
    run()

# ❌ Wrong — infinite recursion (existing bug to fix)
def plot():
    plot()
```

**CLI usage:**
```bash
uv run crewai run --unit Unit-Debate --topic "AI vs Humans"
```

---

## Rule 1.b · `flow_controller.py` → Brain of System (All Logic Lives Here)

`flow_controller.py` is the **sole decision-making authority**. ALL logic lives here.

**Responsibilities:**
- Load config & resolve active profile (`data.json` / `data3d.json` / etc.)
- Validate config against schema (fail fast on structural errors)
- Resolve topic: manual string OR auto-pick from queue OR YouTube reference
- Normalize topic into standard structure (→ Rule 1.c)
- Generate topic slug (→ Rule 21)
- Create workspace folder (→ Rule 18, Rule 22)
- Load / update `meta.json` (→ Rule 23)
- Decide RUN vs SKIP for each unit (→ Rule 24)
- Dispatch the correct Unit (→ Rule 26)
- Handle errors, retries & lock management (→ Rule 25)

**❌ Forbidden:**
- Actual task execution or video generation
- Direct LLM calls
- Writing output files

---

## Rule 1.c · Topic is Normalized Once (Universal Topic Structure)

FlowController MUST normalize `topic` into a **standard structure** so ALL units behave consistently. Normalization happens **once** in FlowController — never repeated in units.

### ✅ Accepted Inputs

```json
"topic": "Cancun hotels, Punta Cana resorts"
```

```json
"topic": "auto"
```

```json
"topic": "yt:VIDEO_ID"
```

```json
"topic": {
  "primary": "Cancun hotels",
  "secondary": ["Punta Cana resorts"],
  "intent": "comparison"
}
```

### 🔄 Mandatory Normalization

All inputs MUST become:

```json
{
  "topic": {
    "primary": "string | null",
    "secondary": [],
    "intent": "general | auto | comparison | reference",
    "source": "manual | auto | youtube"
  }
}
```

### 🔧 Normalization Logic (FlowController Only)

```python
t = inputs.get("topic")

if t == "auto":
    topic = {
        "primary": None,
        "secondary": [],
        "intent": "auto",
        "source": "auto"
    }

elif isinstance(t, str) and t.startswith("yt:"):
    topic = {
        "primary": t.replace("yt:", ""),
        "secondary": [],
        "intent": "reference",
        "source": "youtube"
    }

elif isinstance(t, str):
    parts = [x.strip() for x in t.split(",") if x.strip()]
    topic = {
        "primary": parts[0],
        "secondary": parts[1:] if len(parts) > 1 else [],
        "intent": "comparison" if len(parts) > 1 else "general",
        "source": "manual"
    }

elif isinstance(t, dict):
    topic = {
        "primary": t.get("primary"),
        "secondary": t.get("secondary", []),
        "intent": t.get("intent", "general"),
        "source": t.get("source", "manual")
    }

else:
    raise ValueError(f"Invalid topic format: {t}")

# Inject normalized topic back into inputs
inputs["topic"] = topic
inputs["_topic"] = topic["primary"]  # backward compatibility
```

---

## Rule 1.d · Units Execute Consistently (Topic Contract)

All Units MUST use the normalized topic structure. No unit may parse or interpret topic independently.

### ✅ Correct Usage in Units

```python
# Primary topic (always use this)
topic = inputs["topic"]["primary"]

# Optional: secondary topics for comparison
secondary = inputs["topic"]["secondary"]
intent = inputs["topic"]["intent"]
source = inputs["topic"]["source"]
```

### ❌ Forbidden in Units

- Using raw string topic: `topic = inputs["topic"]` (when not normalized)
- Parsing topic differently per unit: `topic.split(",")` inside a unit
- Assuming topic format: `if "vs" in topic: ...`
- Re-normalizing topic inside a unit (already done in FlowController)

### 📌 Topic Contract Enforcement

```python
# ✅ Correct — Unit reads normalized topic
def run(inputs: dict) -> str:
    topic = inputs["topic"]["primary"]
    if not topic:
        return "skipped — no topic provided"

    # proceed with execution
    ...

# ❌ Wrong — Unit assumes raw string
def run(inputs: dict) -> str:
    topic = inputs["topic"]  # might be dict, might be string
    if "," in topic:         # assumes string format
        parts = topic.split(",")
```

---

## 🔥 Final Principle

> **main.py routes → FlowController decides → Topic is normalized once → Units execute consistently**

This ensures:
- ✅ Universal topic handling across ALL units
- ✅ No unit breaks due to input variation
- ✅ Clean separation of responsibilities
- ✅ Single source of truth for topic structure
- ✅ Fully aligned with CF2 architecture



## Rule 2 · One Unit Per Execution

Only ONE unit runs per command. FlowController never chains units automatically unless a dependency resolver triggers Unit-Data for missing inputs (→ Rule D-2).

```bash
uv run crewai run --unit Unit-Data
uv run crewai run --unit Unit-Debate
uv run crewai run --unit Unit-Publisher
```

**❌ Forbidden:**
- Running multiple units in a single `kickoff()` call
- Automatic cross-unit chaining in FlowController

---


# 🧱 SECTION 2 — UNIT & SUBUNIT RULES (Pure Engineering Rules)

> **Units are isolated execution blocks. SubUnits are reusable pure functions.**

---

## 📐 ARCHITECTURAL PRINCIPLES

### Golden Rule of Separation

```
Flow (Orchestrator)
  ↓ dispatches
Unit (Execution Block)
  ↓ orchestrates
SubUnit (Pure Function)
  ↓ performs
Atomic Task
```

**Never invert this hierarchy.**

---

## Rule 3 · `Unit-*` → Execution Blocks (Complete Isolation)

### 3.1 · Definition

A Unit is an **isolated execution block** that:
- Has exactly ONE responsibility
- Runs independently (can be removed without breaking others)
- Communicates ONLY via files
- Returns ONLY a status string
- Never crashes the pipeline

---

### 3.2 · Unit Responsibility Matrix

Each Unit owns exactly one stage:

| Unit | Single Responsibility | Input Contract | Output Contract |
|------|----------------------|----------------|-----------------|
| `Unit-Scout` | Discover trending topics | Config (platforms, niches) | `topic_queue.json` |
| `Unit-Data` | Generate base content via LLM | Topic string, config | `.md`, `.csv`, `.txt` files |
| `Unit-LeadData` | Generate lead generation data | Topic, target audience | Lead database files |
| `Unit-Debate` | Render debate video | `propose.md`, `oppose.md`, `decide.md` | `debate_video_*.mp4` |
| `Unit-Prodcast` | Create podcast audio/video | Debate scripts OR custom script | `prodcast_*.mp3`, `prodcast_*.mp4` |
| `Unit-Classroom` | Educational video for children | Topic definition text | `classroom_*.mp4` |
| `Unit-Animation` | Render animated bar-race charts | `data.csv` | `bar_race_*.mp4` |
| `Unit-Definition` | Scrolling definition video | `definition.txt` | `definition_video_*.mp4` |
| `Unit-Comparison` | Comparison visualization video | `comparison.md` | `comparison_*.mp4` |
| `Unit-Packaging` | Generate metadata & thumbnails | Final videos (any format) | YT metadata, CC files, thumbnails |
| `Unit-Publisher` | Upload to distribution platforms | Videos + metadata + thumbnails | YouTube/Facebook video IDs |
| `Unit-Advertise` | Create promotional derivatives | Final published videos | Social posts, Shorts cuts, TVC |

**Enforcement:** A Unit that does TWO items from this table must be split.

---

### 3.3 · Unit Signature (Mandatory)

Every Unit MUST follow this exact signature:

```python
def run(
    topic: str,      # ← The subject being processed
    workspace: Path, # ← Absolute path to .runtime/output/{slug}/
    inputs: dict,    # ← Complete merged config (validated)
    force: bool      # ← Override smart skip
) -> str:           # ← Returns: "done" | "failed" | "skipped"
```

**Violations:**
- ❌ Adding extra parameters
- ❌ Returning anything except status string
- ❌ Raising unhandled exceptions
- ❌ Side effects outside workspace

---

### 3.4 · Mandatory Unit Behaviors (The Contract)

Every Unit MUST implement these four behaviors:

#### **Behavior 1 — Input Validation**
- Check required input files exist BEFORE execution
- Return `"skipped"` if inputs missing (NOT crash)
- Log what was missing for debugging

#### **Behavior 2 — Output Isolation**
- Write ONLY to own subfolder: `.runtime/output/{slug}/{unit_name}/`
- NEVER write to another unit's folder
- NEVER write to workspace root
- NEVER write to shared config files

#### **Behavior 3 — Safe Failure**
- Catch ALL exceptions inside Unit
- Log error with full traceback
- Return `"failed"` (NOT raise)
- Pipeline must continue to next Unit

#### **Behavior 4 — Idempotent Execution (Smart Skip)**
- Check if final output already exists
- Skip heavy work if output valid
- Respect `force=True` flag to override
- Log skip reason clearly

---

### 3.5 · Forbidden Unit Behaviors (Zero Tolerance)

| Forbidden Action | Why Banned | Violation of |
|------------------|-----------|--------------|
| Import from another Unit | Creates hidden dependency chain | Rule 3 (Isolation) |
| Return data instead of status | Breaks file-based communication | Rule 3 (Communication) |
| Call another Unit's `run()` | Creates cascading execution | Rule 2 (One Unit Per Execution) |
| Generate topic slug | FlowController's responsibility | Rule 26 (Entry Point) |
| Create workspace folder | FlowController's responsibility | Rule 26 (Entry Point) |
| Modify `inputs` dict | Global state mutation | Rule 4 (No Side Effects) |
| Write to `input/` directory | Config is read-only | Rule 27 (Config Profile) |
| Read from `.runtime/cache/` | Cache is tool-internal only | Rule 39 (Runtime Structure) |
| Change working directory | Pollutes global process state | Rule 19 (No Hardcoded Paths) |
| Raise unhandled exception | Crashes entire pipeline | Rule 4 (Safe Failure) |
| Execute another Unit conditionally | Flow logic in wrong layer | Rule 2 (FlowController Authority) |
| Access environment variables directly | Config must be explicit | Rule 28 (No Hardcoded Values) |

---

### 3.6 · File-Based Communication (The ONLY Interface)

**The Contract:**
- Units NEVER call each other
- Units NEVER share memory
- Units NEVER pass Python objects
- Units communicate ONLY by reading/writing files

**Valid Communication Pattern:**
```
Unit-Data writes:     .runtime/output/{slug}/debate/propose.md
                                    ↓
Unit-Debate reads:    .runtime/output/{slug}/debate/propose.md
```

**Invalid Communication Patterns:**
```
❌ Unit-Debate imports Unit-Data
❌ Unit-Data returns text to Unit-Debate
❌ Unit-Debate calls Unit-Data.regenerate()
❌ Shared global variable between Units
```

---

### 3.7 · File Ownership Rules

Each Unit owns EXACTLY its own output folder:

```
.runtime/output/{slug}/
  ├── debate/        ← Unit-Debate ONLY
  ├── definition/    ← Unit-Definition ONLY
  ├── animation/     ← Unit-Animation ONLY
  ├── prodcast/      ← Unit-Prodcast ONLY
  ├── classroom/     ← Unit-Classroom ONLY
  ├── packaging/     ← Unit-Packaging ONLY (metadata, thumbnails)
  ├── uploads/       ← Unit-Publisher ONLY (upload logs)
  └── advertise/     ← Unit-Advertise ONLY (social derivatives)
```

**Forbidden Actions:**
- ❌ Unit-Debate writing to `animation/`
- ❌ Unit-Publisher modifying files in `debate/`
- ❌ Unit-Packaging deleting files from `prodcast/`
- ❌ Any Unit writing to workspace root (except FlowController)

---

### 3.8 · Unit Isolation Checklist (Pre-Merge Validation)

Before ANY Unit code is merged to main branch, verify:

- [ ] Signature matches: `run(topic, workspace, inputs, force) -> str`
- [ ] No imports from `cf2.units.*` (except in tests)
- [ ] No workspace creation logic
- [ ] No topic/slug generation
- [ ] No modification of `inputs` dict
- [ ] All exceptions caught and logged
- [ ] Returns only: `"done"` | `"failed"` | `"skipped"`
- [ ] Smart skip implemented (checks existing output)
- [ ] Writes ONLY to own subfolder
- [ ] No hardcoded paths (uses `workspace` parameter)
- [ ] No hardcoded config values (uses `inputs` parameter)
- [ ] No direct LLM calls (uses factory pattern)
- [ ] No cross-unit file reads (reads only from predecessor's output)

---

## Rule 4 · `subUnit-*` → Pure Functions (Reusable Micro-Tasks)

### 4.1 · Definition

A SubUnit is a **stateless pure function** that:
- Performs exactly ONE atomic task
- Takes explicit parameters (no globals)
- Returns a concrete result (not status string)
- Has NO side effects on parent Unit
- Can be called from MULTIPLE Units

---

### 4.2 · SubUnit vs Unit (Critical Distinction)

| Aspect | **Unit** | **SubUnit** |
|--------|---------|-------------|
| **Nature** | Execution block (state machine) | Pure function (stateless) |
| **Signature** | Fixed: `run(topic, workspace, inputs, force) -> str` | Custom: any params → any return type |
| **Called by** | FlowController ONLY | Multiple Units |
| **File I/O** | Reads/writes workspace directly | NO direct I/O (caller provides paths) |
| **State** | Owns workspace subfolder | Completely stateless |
| **Error handling** | MUST catch all exceptions | MAY raise exceptions (caller catches) |
| **Return value** | Status string only | Actual result (Path, dict, str, int, etc.) |
| **Reusability** | One-per-pipeline-stage | Many-per-pipeline |
| **Example** | `Unit-Publisher` orchestrates upload pipeline | `subUnitYtUpload` uploads ONE video |
| **Responsibility scope** | Full stage (orchestration) | Single task (atomic operation) |
| **Config access** | Reads from `inputs` dict | Receives values as parameters |
| **Can fail pipeline** | NO (returns `"failed"`) | NO (Unit catches its exceptions) |

---

### 4.3 · SubUnit Naming Convention (Strict)

**Function name:** `subUnit{TaskName}` (camelCase, always starts with `subUnit`)

**File location:** `src/cf2/tools/{category}_{task}.py`

**Examples:**
```
subUnitYtMetadata      → src/cf2/tools/packaging_yt_metadata.py
subUnitYtUpload        → src/cf2/tools/publisher_yt_upload.py
subUnitFbUpload        → src/cf2/tools/publisher_fb_upload.py
subUnitSocialShare     → src/cf2/tools/advertise_social_share.py
subUnitShorts          → src/cf2/tools/advertise_shorts.py
subUnitTvc             → src/cf2/tools/advertise_tvc.py
subUnitLinkedInPost    → src/cf2/tools/advertise_linkedin.py
```

**Violation:** A SubUnit in `units/` folder instead of `tools/`

---

### 4.4 · SubUnit Design Rules (The Contract)

#### **Rule 4.4.1 — Pure Function Signature**

**Required:**
- Explicit parameters (no hidden dependencies)
- Clear return type annotation
- No global variable access
- No environment variable reading

**Examples:**

✅ **CORRECT:**
```python
def subUnitYtMetadata(
    slug: str,
    workspace: Path,
    video_style: str,
    channel: str
) -> dict:
    """Returns: {"title": str, "description": str, "tags": list}"""
```

❌ **WRONG:**
```python
def subUnitYtMetadata():  # ← No parameters, reads globals
    from config import SLUG  # ← Hidden dependency
    return generate_metadata()
```

---

#### **Rule 4.4.2 — Single Responsibility**

One SubUnit = One Atomic Task

✅ **CORRECT:**
```python
subUnitYtUpload(video_path, metadata) -> video_id
subUnitFbUpload(video_path, description) -> fb_video_id
subUnitLinkedInPost(post_text, image_url) -> post_id
```

❌ **WRONG:**
```python
subUnitUploadEverywhere(video_path):  # ← Multiple tasks
    upload_to_youtube()
    upload_to_facebook()
    post_to_linkedin()
    send_email_notification()
```

**Split into:** 4 separate SubUnits

---

#### **Rule 4.4.3 — No Side Effects**

SubUnits must NOT:
- Write files directly (return data, caller writes)
- Modify input parameters (immutable contract)
- Change global state
- Access shared resources without parameters

✅ **CORRECT:**
```python
def subUnitShorts(
    source_video: Path,
    start_time: float,
    duration: float
) -> bytes:  # ← Returns video data, caller saves it
    return cut_video_bytes(source_video, start_time, duration)
```

❌ **WRONG:**
```python
def subUnitShorts(source_video: Path):
    output_path = Path("output/shorts.mp4")  # ← Hardcoded path
    output_path.write_bytes(cut_video())     # ← Direct file write
```

---

#### **Rule 4.4.4 — Reusable Across Units**

A SubUnit must work when called from ANY Unit without modification.

**Test:** Can this SubUnit be used in 3+ different Units?

✅ **CORRECT (Reusable):**
```python
# Can be called from Unit-Publisher, Unit-Advertise, Unit-Packaging
def subUnitYtMetadata(slug: str, style: str, lang: str) -> dict:
    return {"title": f"{slug} - {style}", ...}
```

❌ **WRONG (Tied to One Unit):**
```python
# Only works in Unit-Debate due to hidden dependency
def subUnitYtMetadata():
    from cf2.units.unit_debate import get_debate_context
    context = get_debate_context()  # ← Tight coupling
```

---

### 4.5 · SubUnit Categories (Organizational Principle)

Group SubUnits by the Unit family they primarily serve:

| Category | SubUnits | Serves Units |
|----------|----------|--------------|
| **Data Generation** | `subUnitCsvGenerate`, `subUnitMarkdownFormat` | Unit-Data, Unit-LeadData |
| **Packaging** | `subUnitYtMetadata`, `subUnitYtThumbnail`, `subUnitCcGenerate` | Unit-Packaging |
| **Publishing** | `subUnitYtUpload`, `subUnitFbUpload`, `subUnitYtCcUpload` | Unit-Publisher |
| **Social Media** | `subUnitSocialShare`, `subUnitLinkedInPost`, `subUnitTwitterPost` | Unit-Advertise |
| **Video Derivatives** | `subUnitShorts`, `subUnitTvc`, `subUnitClipExtract` | Unit-Advertise |
| **Audio Processing** | `subUnitTtsGenerate`, `subUnitAudioMerge`, `subUnitAudioNormalize` | Multiple (Debate, Prodcast, Classroom) |
| **Validation** | `subUnitFileValidate`, `subUnitMetaValidate`, `subUnitConfigValidate` | FlowController, Multiple Units |

**Rule:** A SubUnit in wrong category signals misplaced responsibility.

---

### 4.6 · How Units Compose SubUnits (Orchestration Pattern)

**The Pattern:**
- Unit = Orchestrator (decides what/when)
- SubUnit = Executor (does how)

**Example Structure:**

```
Unit-Publisher:
  ├── Validate inputs (Unit logic)
  ├── Call subUnitYtMetadata (SubUnit)
  ├── Call subUnitYtUpload (SubUnit)
  ├── Call subUnitFbUpload (SubUnit)
  ├── Call subUnitSocialShare (SubUnit)
  └── Return "done" (Unit logic)
```

**Key Points:**
- Unit decides execution order
- Unit handles errors from SubUnits
- Unit passes workspace-derived data to SubUnits
- Unit writes SubUnit results to files
- SubUnits remain unaware of pipeline context

---

### 4.7 · Forbidden SubUnit Patterns (Anti-Patterns)

| Anti-Pattern | Why Banned | Correct Alternative |
|--------------|-----------|---------------------|
| SubUnit calls another SubUnit | Creates hidden call chain | Unit orchestrates both |
| SubUnit reads `inputs` directly | Hidden dependency | Unit passes values as parameters |
| SubUnit writes files | Side effect | Return data, Unit writes |
| SubUnit imports from Unit | Circular dependency | Keep SubUnits in `tools/` |
| SubUnit accesses workspace | State dependency | Unit passes specific paths |
| SubUnit does 3+ tasks | Violates single responsibility | Split into 3 SubUnits |
| SubUnit has conditional logic for different Units | Knows too much | Split into specialized SubUnits |
| SubUnit uses `print()` | No structured logging | Unit logs SubUnit results |

---

### 4.8 · SubUnit Validation Checklist (Pre-Merge)

Before ANY SubUnit is merged:

- [ ] Function name starts with `subUnit` (camelCase)
- [ ] Located in `src/cf2/tools/` (not `units/`)
- [ ] All parameters explicitly typed
- [ ] Clear return type annotation
- [ ] No global variable access
- [ ] No direct file I/O (returns data instead)
- [ ] No hardcoded values (all via parameters)
- [ ] No imports from `cf2.units.*`
- [ ] Can be called from 2+ different Units
- [ ] Single atomic task only
- [ ] Raises exceptions (doesn't return status strings)
- [ ] Documented with docstring (params + return)

---

## 🎯 Decision Tree: Unit vs SubUnit

### **Create a Unit when:**
- ✅ It's a new pipeline stage with its own config block
- ✅ It needs its own workspace subfolder
- ✅ It's controlled by a `Unit-*` boolean switch
- ✅ It orchestrates multiple tasks
- ✅ Example: "Unit-Transcript" for video transcription

### **Create a SubUnit when:**
- ✅ It's a helper for existing Units
- ✅ It performs one specific atomic task
- ✅ Multiple Units need the same operation
- ✅ It's a pure function with no state
- ✅ Example: "subUnitTranscriptUpload" for uploading transcripts

### **DON'T create a Unit when:**
- ❌ Existing SubUnits can handle it
- ❌ It's a variation (use config parameter instead)
- ❌ It duplicates another Unit's responsibility
- ❌ It has no workspace output folder

### **DON'T create a SubUnit when:**
- ❌ It needs to orchestrate multiple steps (make it a Unit)
- ❌ It needs to own workspace state (make it a Unit)
- ❌ It's only used once (inline in Unit instead)

---

## 🔥 Production Stability Guarantees

Following these rules ensures:

| Failure Mode | Before Rules | After Rules |
|--------------|--------------|-------------|
| **Adding new Unit breaks old ones** | ❌ Happened frequently | ✅ Impossible (isolation) |
| **Failed Unit stops entire pipeline** | ❌ Entire system crashed | ✅ Returns `"failed"`, continues |
| **Missing input files crash system** | ❌ Unhandled exceptions everywhere | ✅ Graceful `"skipped"` with logs |
| **Hard to trace which Unit failed** | ❌ Cryptic stack traces | ✅ Clear status in `meta.json` |
| **Upgrading one Unit is risky** | ❌ Fear of breaking everything | ✅ Safe (no dependencies) |
| **Can't run Units independently** | ❌ Must run full pipeline | ✅ Single-Unit execution works |
| **SubUnits tied to specific Units** | ❌ Code duplication everywhere | ✅ Reused across pipeline |
| **SubUnit changes break multiple Units** | ❌ Cascading failures | ✅ Isolated to one Unit at a time |

---

## 📏 Enforcement Mechanism

### **Automated Checks (CI/CD):**
- Unit signature validator (fails build if signature wrong)
- Import scanner (fails if Unit imports another Unit)
- File write analyzer (fails if Unit writes outside its folder)
- Exception handler checker (fails if unhandled exceptions)

### **Manual Code Review Checklist:**
- Every Unit PR: Run isolation checklist (3.8)
- Every SubUnit PR: Run validation checklist (4.8)
- Any cross-Unit change: Rejected automatically
- Any hardcoded config: Rejected automatically

### **Runtime Enforcement:**
- FlowController validates Unit return values
- FlowController catches Unit exceptions
- FlowController logs all status transitions
- Meta.json tracks Unit-level state

---

**End of Section 2 — No code, pure rules.**




# 🔥 SECTION 3 — UNIT-DATA RULES (CRITICAL)
## Rule 5 · Unit-Data is a Provider, Never a Consumer · Unit-Data Never Calls Itself

    Unit-Data reads NOTHING from other units. It reads only `topic`, `inputs` (config) & `data.json`. It writes only to `.runtime/output/{slug}/` subfolders.

    ```
    ❌ unit_data.py reads any .md or .mp4 from workspace
    ✅ unit_data.py writes .md, .csv, .txt to .runtime/output/{slug}/
    ```

    No retry loop, no recursive fallback, no self-kickoff. If it fails, it marks `failed` in `meta.json` & stops. FlowController decides whether to re-run.

    ---

## Rule 6 · Unit-Data is Never Called Directly · Task Selection Controlled by Unit Switches Only

    Only two callers are legal:
    1. `FlowController` (full pipeline or `--unit Unit-Data`)
    2. `dependency_resolver` (when a consumer's input files are missing)

    ```python
    # ❌ Never — unit calling a unit
    from cf2.units.unit_data import run as run_data
    run_data(topic, inputs)

    # ✅ Always via FlowController or dependency_resolver
    flow_controller.run(unit="Unit-Data", topic="EVA Framework")
    ```

    Unit-Data reads `inputs["Unit-Debate"]`, `inputs["Unit-Definition"]` etc. It NEVER reads nested config keys like `debate_enabled` or `definition_video_enabled`.

    ```python
    # ✅ Correct
    debate_on = inputs.get("Unit-Debate", False)

    # ❌ Wrong — nested config sub-key
    debate_on = inputs.get("debate_enabled", False)
    ```

---

## Rule 7 · Core Tasks Always Run · Consumer-Specific Tasks Only Run for Enabled Units · Output Files Are the Contract

      `data_research` & `data_generate_csv` run on every execution regardless of any unit switch. They are the non-negotiable foundation.

      ```python
      # Always — no guard
      agents += [factory.data_researcher()]
      tasks  += [factory.data_research()]
      agents += [factory.data_csv_generator()]
      tasks  += [factory.data_generate_csv()]
      ```

      If a unit is disabled, its data is never generated. This prevents wasted LLM calls & partial file states.

      | Task group           | Guard                                            |
      |----------------------|--------------------------------------------------|
      | Definition text      | `Unit-Definition == true`                        |
      | Debate scripts       | `Unit-Debate == true`                            |
      | Debate short scripts | `Unit-Debate == true` & `debate_short == true` |
      | Comparison data      | `Unit-Comparison == true`                        |

      Unit-Data is only `done` when its required output files **physically exist**. `meta.json` status alone is not sufficient.

      **Minimum required output:**
      ```
      .runtime/output/{TopicSlug}/
        debate/propose.md   oppose.md   decide.md
        definition/def_*.md
        animation/data.csv
        comparison/comparison.md
      ```

      **❌ Forbidden:**
      - Video generation (any format)
      - Audio or TTS
      - Upload or social actions
      - Depending on any other unit

      > **Generate once — consumed everywhere. Never re-run if files exist.**

    ---






# 📺 SECTION 4 — CONSUMER UNIT RULES

## Rule 8 · Consumer Units → Read-Only

`Unit-Debate`, `Unit-Animation`, `Unit-Definition`, `Unit-Comparison` are **read-only consumers**.

**Responsibilities:**
- Read `.md` / `.csv` files written by Unit-Data
- Generate video output
- Save to their own subfolder inside `.runtime/output/{slug}/`

**❌ Forbidden:**
- Calling an LLM to regenerate content
- Writing new `.md` or `.csv` files
- Calling Unit-Data directly

> **Consume only — never regenerate.**

---

## Rule 9 · `Unit-Publisher` → Distribution Layer Only

Handles all publishing after video is confirmed final in `meta.json`. Never touches video creation.

**SubUnits:**
```
subUnitYtMetadata    subUnitYtThumbnail   subUnitYtUpload
subUnitFbUpload      subUnitSocialShare
```

**Rule:** Publishing only starts when content files are confirmed `done` in `meta.json`.

---

## Rule 10 · `Unit-Advertise` → Promotion Layer Only

Creates promotional derivatives from finished videos. Never recreates source content.

**SubUnits:**
```
subUnitShorts    subUnitSocial    subUnitTvc
```

**Rule:** Reuse existing `.mp4` files — never regenerate core content.



# 🤖 SECTION 5 — Core `Service`, Utility, LLM & Others Rules

## Rule 11 · Core Services → tts, ffmpeg, audio, video, 3d, hologram, clips

**Location:** `src/cf2/core/services/`

**Standard:**
- Services are **stateless wrappers only**. They do one technical job: generate TTS, run ffmpeg, merge audio/video, render 3D, build clips.
- No business logic, no prompt building, no unit-specific decisions inside a service.
- All methods must be **idempotent** with smart-skip: if output exists, return True immediately. Do not re-process.
- All methods must be **damage-contained**: catch exceptions internally, log, return False. Never raise to crash the pipeline. One failed task must not affect other tasks or units.
- Resource safety required: use timeouts, nice/ionice, process groups. Kill hung subprocesses cleanly.
- No hardcoded paths, voices, bitrates, or limits. Everything comes from caller inputs.
- Services receive a logger, they do not create global loggers.

**Current services:**
- `tts_service.py` — unified gTTS, Edge, Piper
- `ffmpeg_service.py` — safe ffprobe, concat, mix, shorts limit
- `audio_service.py` — merge, atempo, concatenate, duration

> All new core media services must follow this same contract.

---

## Rule 12 · Core Others / Utility Elements

**Location:** `src/cf2/core/` (outside services)

**Standard:**
- These are shared, optional helpers. They must never hold unit state.
- Includes: `config_loader.py`, `paths.py`, `utils.py`, `logging_setup.py`, `progress_tracker.py`, `dependency_resolver.py`, `clip_resolver.py`, `topic_resolver.py`, `weak_words.py`, `registry.py`, `executor.py`
- Sub-packages: `compress/`, `parser/`, `subtitle/`, `tts/providers/`

**Rules:**
- Single responsibility per file. No cross-imports that create circular dependencies.
- Config-driven only. No hardcoded defaults in code.
- Fail-safe by design: return safe defaults (0.0, {}, False) on error, log warning, continue pipeline.
- Must be import-safe and testable in isolation.

---

## Rule 10 · Core Service Isolation Rule

This is the damage-free principle for both Rule 11 and Rule 12:

1. **Task-level isolation:** If any core service or utility fails, only that task fails. The executor marks it failed, logs structured error, pipeline continues.
2. **No shared mutable state:** Services are instantiated per task, not as singletons holding data.
3. **Timeouts everywhere:** ffmpeg, TTS, network calls must have hard timeouts. No blocking calls.
4. **Smart skip is mandatory:** Check file existence first to make retries safe and SaaS-cost efficient.
5. **Observability:** Every service logs: start, skip, success, failure, duration, model/tool used. No silent failures.

> Protect other units at all costs. A failure in TTS must not break video merging. A failure in ffmpeg must not break LLM execution.

---

## Rule 13 · Centralized LLM Config

**LLM RULES — with fallback, reliability & production safety**

### A · Only ONE place holds LLM configuration

`input/llm_conf.json`

```json
"llm_config": {
  "default": "deepseek/deepseek-chat",
  "fallback": [
    "dashscope/qwen-plus",
    "openai/gpt-4o"
  ],
  "temperature": 0.7
}
```

**Runtime behavior:**
- Try `default` first
- On failure (API outage, rate limit, timeout, invalid response) → retry in order through `fallback` list
- Stop on first successful response
- Log which model succeeded and whether fallback was triggered

**Benefits:** Prevents pipeline failure from single-provider issues. Enables multi-provider resilience.

**❌ Forbidden:**
- `llm_*` keys duplicated inside unit-specific config blocks
- Hardcoded model strings anywhere in code
- Embedding fallback logic inside tools or units

> All model selection and fallback must be config-driven.

### B · Agent-Based LLM Mapping

```json
"agents": {
  "debater": "deepseek/deepseek-chat",
  "judge": "dashscope/qwen-plus",
  "data_researcher": "deepseek/deepseek-chat"
}
```

**Enhancements:**
- Mapping is per-agent role, NOT per-task, NOT per-unit
- Each agent inherits `default` and `fallback` chain from `llm_config` automatically
- Optional override supported:

```json
"agents": {
  "debater": {
    "primary": "deepseek/deepseek-chat",
    "fallback": ["dashscope/qwen-plus"]
  }
}
```

**Runtime:** Resolve agent → model → apply fallback chain → maintain consistent output style per agent.

**Benefits:** Stable behavior, controlled variability, agent-level tracing for debugging.

### C · No Direct LLM Calls

All LLM calls must go through the factory agent pattern.

```python
# ❌ Forbidden
openai.chat(...)
anthropic.messages.create(...)

# ✅ Correct
factory.agent()
```

**Execution layer must provide:**
- Retry mechanism (2 to 3 attempts for transient failures)
- Automatic fallback handling using `llm_config.fallback`
- Timeout control to prevent blocking pipeline
- Structured logging (model used, fallback triggered, latency, status)
- Deterministic input/output contract (validated prompt structure, validated response format)

**❌ Forbidden:**
- Direct SDK usage in Units, Tools, or FlowController
- Manual retry loops inside tools
- Custom fallback logic outside centralized LLM layer

---

### 🔥 Operational Principle

> **LLM access must be centralized, observable, retryable and replaceable. Services must be stateless, idempotent and damage-contained.**

This gives you a fault-tolerant pipeline, multi-provider resilience, clean separation of config vs execution, and a production-ready SaaS core where one failing task never kills the whole flow.








# 🏗️ SECTION 6 — CREW / AGENT RULES

## Rule 14 · Crew → Execution Tool Only

Crew is a dumb executor. Flow tells it exactly what to run. Never run the full crew blindly.

```python
# ✅ Correct — explicit selection
agents = [factory.debate_video_producer()]
tasks  = [factory.create_debate_video()]
factory.crew().kickoff(agents=agents, tasks=tasks, inputs=inputs)

# ❌ Wrong — blind execution
factory.crew().kickoff()
```

**❌ Forbidden:**
- Running the full crew without explicit agent/task selection
- Mixing unrelated tasks in one kickoff call

---

## Rule 15 · Factory Pattern Only

All agents & tasks must come from `CF2Crew()`. No inline agent or task definitions anywhere else.

```python
# ✅ Correct
factory.debater()
factory.data_researcher()

# ❌ Wrong — inline definition
Agent(role="debater", goal="...", backstory="...")
```

---

## Rule 16 · Task = Single Output

Each task produces exactly ONE file. Multi-output tasks & hidden outputs are forbidden.

---

# 📁 SECTION 7 — FILE SYSTEM RULES

## Rule 17 · File System → Single Source of Truth

Files are truth. Memory is not.

| File         | Truth it holds        |
|--------------|-----------------------|
| `propose.md` | Propose debate script |
| `data.csv`   | Animation source data |
| `video.mp4`  | Final output          |
| `meta.json`  | Unit run status       |

**❌ Forbidden:**
- Hidden state stored in Python variables between runs
- Recomputing something a file already holds
- Treating in-memory results as authoritative

---

## Rule 18 · Folder Structure → Topic-Based Workspace

All topic workspaces live under `.runtime/output/`. Because `.runtime/` is never committed to git, all generated content is automatically excluded from version control with a single `.gitignore` entry.

```
.runtime/output/
  EvaFrameworkNew/
    debate/
    definition/
    animation/
    comparison/
    YT/
    .lock
    meta.json
  EvaFrameworkNew__01/
    ...
```

> **One Topic = One Workspace. Never mix outputs across topics.**

---

## Rule 19 · No Hardcoded Paths

All paths must be resolved through config or a central `PATHS` constant, never as string literals scattered in code.

```python
# ✅ Correct
from config import PATHS
path = PATHS["output"] / slug / "debate" / "propose.md"

# ❌ Wrong — literal string, breaks when output root moves
path = f".runtime/output/{slug}/debate/propose.md"
```

---

## Rule 20 · Idempotent Writes

Running a unit twice must NOT break or corrupt output. Every write either overwrites safely or skips if the file already exists (→ Rule 24).

---

## Rule 39 · `.runtime/` → System-Only Directory

`.runtime/` is a machine-managed directory. Never committed to version control & never accessed by Units via hardcoded path strings. Only `cf2.core.paths` resolves paths into it & only the  layer (`config.py`) exposes them via `PATHS`.

```
.runtime/
  output/    ← all topic workspaces (was output/ at project root)
  logs/      ← execution logs (flow_controller, units)
  secrets/   ← OAuth tokens, API keys, client_secret*.json
  cache/     ← temporary intermediate data (never treated as final output)
```

Moving `output/` inside `.runtime/` means a single `.gitignore` entry (`/.runtime/`) excludes all generated content — logs, secrets, cache & every rendered video.

**Ownership rules:**

| Subdirectory        | Who writes                          | Who reads                          |
|---------------------|-------------------------------------|------------------------------------|
| `.runtime/output/`  | Units (via tool `_run()`)           | Consumer units + publisher         |
| `.runtime/logs/`    | FlowController + Units (via logger) | Operator / debug tooling only      |
| `.runtime/secrets/` | Operator (manual placement)         | `resolve_config_paths()` only      |
| `.runtime/cache/`   | Tools (intermediate work)           | Same tool on next run (skip logic) |

**❌ Forbidden:**
- Any Unit or tool importing a `.runtime/` path as a string literal
- Committing `.runtime/` contents to git
- Treating `.runtime/cache/` files as final deliverables or referencing them in `meta.json`
- Placing secret files anywhere outside `.runtime/secrets/`
- Using `OUTPUT_ROOT` pointing to the old project-root `output/`

```python
# ✅ Correct — always via PATHS
workspace   = PATHS["output"] / slug
secret_path = PATHS["secrets"] / "pai_token.json"

# ❌ Wrong — hardcoded, breaks on any path restructure
workspace = f"output/{slug}"
workspace = f".runtime/output/{slug}"
```

> **All generated content lives in `.runtime/`. Nothing in `.runtime/` is ever source-controlled.**

---

# 🔄 SECTION 8 — META / CONTROL RULES

## Rule 21 · Slug Rule → Predictable PascalCase Naming

Take the first 3 **meaningful** words of the topic. Skip stop words (`for`, `the`, `a`, `an`, `is`, `of`, `to`, `in`, `and`). Join in PascalCase with no spaces or dashes.

```
"EVA Framework for New Evaluating Voice Agents"  →  EvaFrameworkNew
"Is AI Actually Dangerous?"                       →  IsAiDangerous
"The Future of Work in 2026"                      →  FutureWork2026
```

---



## Rule 22 · Collision Rule → `__01` Suffix System

    **Purpose:**
    Prevent overwriting existing work **and avoid unnecessary API calls**

    ---

    ### Core Principle

    * Do **NOT** create `__01` automatically when a slug exists
    * Always **check existing workspace first**

    ---

    ### Correct Flow

    ```text
    User → topic
          ↓
    Generate slug (AiDangerous)
          ↓
    Check: does workspace exist?
    ```

    #### Case 1 — New Topic

    * Slug does NOT exist
      → Create new workspace
      → `AiDangerous/`

    #### Case 2 — Workspace Exists + All Files Present

    * All required files exist
      → Reuse workspace
      → **Smart Skip (NO API call)**

    #### Case 3 — Workspace Exists + Files Missing

    * Some required files missing
      → Reuse workspace
      → Generate only missing files (**partial run**)

    #### Case 4 — User Requests New Version

    * `--force` or explicit request
      → Create new version
      → `AiDangerous__01/`

    ---

    ### When to Create `__01`

    Create a new folder ONLY when:

    * User explicitly requests a new version
    * Force flag is enabled

    ```text
    AiDangerous/
    AiDangerous__01/
    AiDangerous__02/
    ```

    ---

    ### Required Files Check (Example)

    ```python
    required = [
        "debate/propose.md",
        "debate/oppose.md",
        "debate/decide.md",
    ]

    if all((workspace / f).exists() for f in required):
        return "skipped"   # ✅ No API call
    ```

    ---

    ### FlowController Logic (Mandatory)

    ```python
    if slug_exists:
        if required_files_exist:
            reuse_slug            # ✅ no API call
        else:
            generate_missing      # ✅ partial API
    else:
        create_slug              # new topic
    ```

    ---

    ### Key Rules

    * Reuse first, generate later
    * Never overwrite existing work
    * Never call LLM if files already exist
    * Only create `__01` for intentional regeneration

    ---

    ### 🔥 Final Principle

    > **Reuse > Partial Run > New Version**
    > *(Cost efficiency comes before duplication)*

    ---

    This version removes redundancy, keeps logic tight, and directly enforces **zero-waste API behavior**.


## Rule 23 · `meta.json` → Unit State Brain

Every unit's run state is tracked here. FlowController reads it before dispatching anything.

```json
{
  "topic": "EVA Framework for New Evaluating Voice Agents",
  "slug": "EvaFrameworkNew",
  "status": {
    "Unit-Data":      "done",
    "Unit-Debate":    "done",
    "Unit-Animation": "pending",
    "Unit-Publisher": "pending"
  },
  "uploads": {
    "youtube":  "done",
    "facebook": "pending"
  },
  "created_at": "2026-03-30T04:34:33Z",
  "updated_at": "2026-03-30T06:16:46Z"
}
```

**Valid statuses:** `pending` · `running` · `done` · `failed`

> **Always trust `meta.json` before running anything. But verify output files too (→ Rule D-7).**

---

## Rule 24 · Smart Skip → Zero Waste Execution

Before running any unit, FlowController checks in this order:

```
IF meta[unit] == "done"    → SKIP
IF output file exists      → SKIP
IF .lock file present      → WARN + prompt operator (possible crash)
ELSE                       → RUN
```

Smart Skip is also **mandatory inside every tool** (→ Rule 28). This enables automatic crash recovery — re-running the pipeline resumes from where it stopped.

> **Never repeat a heavy task that already completed successfully.**

---

## Rule 25 · Lock System → Crash Safety

A `.lock` file is created inside the topic folder at run start & deleted on clean exit.

**Purpose:**
- Prevents duplicate parallel runs of the same topic
- Lets FlowController detect a previous crash & warn the operator before proceeding

> **If `.lock` exists at startup, prompt the operator before proceeding.**

---

## Rule 26 · `flow_controller.py` is the ONLY Entry Into Units

No external script, test file, or manual call may invoke a Unit directly. All unit execution goes through FlowController. This preserves skip logic, lock management & meta tracking for every run.

```python
# ✅ Always via FlowController
flow_controller.run(unit="Unit-Debate", topic="EVA Framework")

# ❌ Never call a unit directly
from cf2.units.unit_debate import run
run(topic, inputs)
```

---

# ⚙️ SECTION 9 — All Config Rules inside INPUT_DIR {Topics , Focus , profile & units ..}

> **Config defines identity — Flow controls logic — Units execute work → Tools/Core**

-  All rules only For input/*.json file Rules
-  Topics is mediatory input configure field without this system not start_time , its can not empty
-  Focus is optional supporting for Topics right direction , its can empty
-

---

## Rule 27 · Topics , Focus & profile Rules

    data/data3d.json Config Profile → One File Per Channel
    * Keys defined in `data.schema.json` must **never be removed**
    * Disable features using **existing boolean switches only**
    * `data.json` = **base configuration (single source of truth)**
    * Profile configs override **only existing schema keys**
    * No structure drift allowed beyond `data.schema.json`

    **Files:**

    ```text
    input/
      data.json        ← base
      data3d.json      ← overrides (e.g. debate_3d_enabled)
      datasports.json  ← overrides
      dataBn.json      ← overrides (e.g. audio_lang)
    ```

    **Merge Logic (Schema-Safe):**

    ```python
    final_config = deep_merge(data.json, profile.json)
    ```

    **Constraints (Strict):**

    * Override only keys that already exist in schema
    * Preserve full schema shape after merge
    * Nested overrides must match exact structure

    **Valid override scope:**

    * Top-level: `video_fps`, `tts_engine`, `channel`
    * Nested: `scout_config`, `animation_config`, `debate_config`

    **❌ Forbidden:**

    * Adding new keys not defined in `data.schema.json`
    * Changing structure (e.g. object → list, object → null)

    > **Profiles customize values — never redefine structure**

    ---

## Rule 28 · `unit_config.json` is Append-Only main/default (Schema-Safe)

      * All  unit config will be inside here
      * no units data inside data/data3d.json except   "Unit-":true/ false,
      * if need unit can extendt another config must be include unit config

        **Correct:**
        ```json
        { "Unit-Debate": false }
        ```
        **❌ Wrong:**

        ```json
        { "debate_config": null }        
        ```

        ### Sub-rule · Config Stability

        * `_config` blocks ALWAYS exist
        * Units ignore config when master switch = false
        * No conditional deletion of config blocks

        > **Schema stability > config cleanliness**

        ---

## Rule 29 · Except Configure ,No Hard coded Values anywhere  py code

    * Config is authoritative: if key exists → use it exactly
    * Fallbacks are **safety-only**, never behavioral overrides
    * Every fallback must be **observable (loggable)**

    **All values must come from config (`inputs`)**

    **Schema-driven examples:**

    * `llm_debate`
    * `video_fps`
    * `tts_engine`
    * `audio_speed`, `audio_speed_hd`
    * `debate_config.debate_secs_per_line`
    * `animation_config.intro_duration`

    ```python
    # ✅ Correct
    fps = inputs.get("video_fps")
    debate_speed = inputs.get("debate_config", {}).get("debate_secs_per_line")

    # ❌ Wrong
    fps = 30
    ```

    ### Sub-rule · Fallback Behavior (Strict)

    Fallback is allowed ONLY when:

    * Key is missing
    * Asset is missing
    * External dependency fails

    Fallback must:

    1. Use schema-aligned default OR safe base resource
    2. Never introduce new logic branches
    3. Be logged for operator visibility

    > **Fallback prevents failure — never changes intent**

    ---



## Rule 30 · Config = Control, Not Logic (Schema-Enforced)

    Config maps **only to schema fields**

    **✅ Valid:**

    ```json
    {
      "Unit-Debate": true,
      "debate_config": {
        "debate_secs_per_line": 3.5,
        "debate_max_chars": 1000
      }
    }
    ```

    **❌ Invalid (logic):**

    ```json
    {
      "fast_mode_when_shorts": true
    }
    ```

    **❌ Invalid (derived behavior):**

    ```json
    {
      "debate_config": {
        "use_fast_speed_if_short": true
      }
    }
    ```

    ---

    ### 🔒 Schema Alignment Rules (Critical)

    1. Every key MUST exist in `data.schema.json`
    2. Structure must match exactly (no shape mutation)
    3. Unit execution controlled ONLY by:

       ```
       Unit-Debate
       Unit-Animation
       Unit-Definition
       Unit-Comparison
       Unit-Packaging
       Unit-Publisher
       Unit-Advertise
       ```
    4. `_config` blocks = parameters only (never execution control)



    > **Schema defines structure · Config fills values · Flow controls execution · Units consume config**

    ---

    ## Sub-section · Asset Fallback System (Critical Improvement)

    This part was good but scattered—now made **system-level & enforceable**.

    ### Sub-rule · Universal Clip Fallback

    All clip/image resolution MUST support automatic fallback:

    **Priority order:**

    ```
    1. Exact match (e.g. p3_s.mkv)
    2. Base clip   (e.g. p3.mkv)
    3. Default set (p0 / c0)
    ```


    """
    Universal clip fallback with 3-tier priority:
    1. Exact match (e.g. int7s_s.mkv)
    2. Base clip   (e.g. int7s.mkv)
    3. Default     (e.g. p0/c0 fallback)
    """

    ### Sub-rule · Minimal Key Guarantee

    If clip keys are missing:

    * System MUST fallback to:

      ```
      p0 for host/propose
      c0 for guest/oppose
      ```
    * Segment builder modulo logic guarantees reuse:

    ```python
    host_keys[h_idx % len(host_keys)]
    ```

    → Single fallback key = infinite safe loop

    ---

    ### Sub-rule · Zero Manual Intervention

    **Strict rule:**

    * NO manual copy commands (`cp`)
    * NO asset duplication hacks
    * NO runtime fixes by operator

    > If a file is missing → system resolves it automatically

    ---

    ### Sub-rule · Smart Suffix Fallback

    Inside `_ensure_clip_exists`:

    **Behavior:**

      1. Check suffixed file (`*_s.mkv`)
      2. If missing → strip suffix
      3. Check base file
      4. If exists → use base
      5. Else → fallback to p0/c0

    ---

    ### Sub-rule · Absolute Path Guarantee

    All resolved assets MUST:

    * Return absolute paths
    * Never depend on relative resolution
    * Prevent renderer “Clip Missing” errors

    ---

    ### Sub-rule · Intro Safety Guard

    * If intro clip fails resolution (even after fallback):
      → Skip intro segment entirely

    **Reason:**

    * Avoid black frames
    * Avoid broken timelines

    ---

    ### Sub-rule · System Responsibility Boundary

    | Responsibility          | Owner                |
    | ----------------------- | -------------------- |
    | Clip existence handling | Tool (clip resolver) |
    | Fallback logic          | Tool                 |
    | Execution decision      | Flow                 |
    | Config values           | Config               |

    > **Tools must be self-healing — not operator-dependent**

    ---

    ## Final Principle (Refined)

    > **Config defines what should happen
    > Fallback ensures it still runs
    > Flow decides when
    > Tools guarantee execution without failure**

    ---





# 🔧 SECTION 10 — CODE QUALITY RULES

## Rule 31 · Function Design → 50–80 Lines Max

- Single responsibility per function
- No nested conditional chaos
- Helper functions preferred over long methods
- If a function exceeds 100 lines, it must be split

**❌ Forbidden:** 1000-line god functions. Mixed responsibilities inside a single method.

---

## Rule 32 · Smart Skip is Mandatory in Every Tool

Every tool's `_run()` method must check for its own final output file **before** doing any work. Not optional — must run before any LLM call, TTS generation, or video render.

```python
if os.path.exists(final_output_path):
    return f"⏭️ Skipped — already exists: {final_output_path}"
```

---

## Rule 33 · Output Naming Convention → Predictable File Names

All final output files follow this strict pattern so downstream units & upload tools can locate them without scanning the folder:

```
{Channel}_{TopicSlug}_{Format}_{LangSuffix}.mp4

PlayOwnAi_EvaFrameworkNew_Shorts_En.mp4
PlayOwnAi_EvaFrameworkNew_HD_En.mp4
360Debate_IsAiDangerous_Shorts_Bn.mp4
```

Intermediate files use tool-internal prefixes (`debate_video_`, `bar_race_`, `intro_`) & are **never** treated as final deliverables.

---

# 🔌 SECTION 11 — CONFIG  RULES (`config.py`)

`config.py` is a **compatibility  only**. It exists so legacy imports like `from config import PATHS, slugify` keep working. It must never grow into a logic layer.

## Rule 34 · `config.py` is a Re-Export Layer — No Logic Allowed

All real implementations live in their canonical modules. `config.py` only re-exports them.

```
cf2.core.paths         → path constants + topic workspace helpers
cf2.core.config_loader → profile loading + deep-merge
cf2.meta               → meta.json read/write/lock
```

```python
# ✅ Correct — thin re-export
from cf2.core.paths import OUTPUT_ROOT, get_topic_dir

# ❌ Wrong — logic in the
def get_topic_dir(slug):
    if not slug:
        slug = "default"   #  is now making decisions
    return OUTPUT_ROOT / slug
```

---

## Rule 35 · `PATHS` Dict → Canonical Key Names Only

The `PATHS` dict exposes exactly these keys & no others. All code that needs a base directory imports from `PATHS` — never constructs the path itself.

```python
PATHS = {
    "root"   : PROJECT_ROOT,              # repo root
    "input"  : INPUT_DIR,                 # input files
    "output" : RUNTIME_PATHS["output"],   # .runtime/output/
    "logs"   : RUNTIME_PATHS["logs"],     # .runtime/logs/
    "secrets": RUNTIME_PATHS["secrets"],  # .runtime/secrets/
    "cache"  : RUNTIME_PATHS["cache"],    # .runtime/cache/
}
```

Adding undocumented keys to `PATHS` without updating this rule is a violation.

---

## Rule 36 · `slugify()` Stop-Word List is Canonical

The authoritative stop-word set lives in `cf2.core.topic_resolver`. The copy in `config.py` exists only for backward compatibility & must stay **identical**. If the stop-word list changes, both files must be updated together.

```python
# Canonical stop words — do not diverge between config.py & topic_resolver.py
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "is", "are", "was", "were", "be", "by", "from", "with", "as",
    "if", "can", "will", "should", "would", "could", "have", "has", "had",
}
```

Slug max length is capped at **60 characters**. This must be consistent across all callers.

---

## Rule 37 · `resolve_config_paths()` → Routing Logic is Fixed

`resolve_config_paths()` resolves `*_file` keys in the inputs dict to absolute paths. The routing priority is fixed & must not be changed without updating this rule:

```
1. Already absolute path        → leave untouched
2. Starts with "input/"         → PROJECT_ROOT / value
3. Matches a secret pattern     → .runtime/secrets/ basename
4. Anything else                → INPUT_DIR / basename
```

Secret patterns: `client_secret`, `client_secrets`, `token`, `credentials`, `api_key`, `secret`, `credential`. Only `*_file` keys are resolved — plain string keys are never touched.

```python
# ✅ Resolved — key ends with _file, value is relative
{ "token_file": "my_token.json" }  →  ".runtime/secrets/my_token.json"

# ✅ Not touched — key does not end with _file
{ "channel_name": "PlayOwnAi" }    →  unchanged
```

---

## Rule 38 · `read_meta()` Must Not Use Collision Slug for Existing Topics

`read_meta()` in `config.py` currently calls `_find_collision_free_slug()` before reading — this is **wrong for reads**. Collision-free slug generation is only for **workspace creation** (Rule 22). Reading meta must use the exact slug of the existing workspace.

```python
# ✅ Correct for reads
def read_meta(topic: str) -> dict:
    slug = slugify(topic)          # exact slug, no collision suffix
    f = RUNTIME_PATHS["output"] / slug / "meta.json"
    ...

# ❌ Wrong — appends __01 even when reading an existing workspace
def read_meta(topic: str) -> dict:
    slug = _find_collision_free_slug(slugify(topic))   # creates wrong path
    ...
```

This is an existing bug in `config.py` that must be fixed.

---

# 🚫 SECTION 12 — ANTI-PATTERNS (ENFORCE ZERO TOLERANCE)

## Rule 39 · These are banned. No exceptions.

| Anti-Pattern | Why Banned |
|---|---|
| Unit calling another unit | Breaks isolation |
| Unit reading another unit's config | Tight coupling |
| Direct LLM call outside factory | Bypasses config |
| Flow logic inside a unit | Violates Rule 2 |
| Returning data instead of saving files | Hidden state |
| Hardcoded model/path/voice in tool | Violates Rule 28 |
| Re-generating `.md` / `.csv` in consumer units | Violates Rule 8 |
| Running full crew blindly | Violates Rule 14 |
| `plot()` calling `plot()` (recursion) | Runtime crash |
| Multiple units in one `kickoff()` | Violates Rule 3 |
| Deleting keys from `data.json` | Violates Rule 29 |
| Writing output file without smart skip check | Violates Rule 32 |
| Adding logic to `config.py`  | Violates Rule 34 |
| `read_meta()` using collision-free slug | Violates Rule 38 |
| Diverging stop-word list between  & resolver | Violates Rule 36 |
| Constructing paths as string literals instead of `PATHS` | Violates Rule 19 |
| Hardcoded `.runtime/` or `output/` path string in any unit or tool | Violates Rule 39 |
| `OUTPUT_ROOT` still pointing to project-root `output/` (not migrated) | Violates Rule 39 |
| Placing secret files in `input/` instead of `.runtime/secrets/` | Violates Rule 39 |
| Referencing `.runtime/cache/` files in `meta.json` as outputs | Violates Rule 39 |

---

## Rule 40 · Final Mental Model

# 🧠 FINAL MENTAL MODEL

```
User Input
   ↓
main.py  (dumb router — 3 lines)
   ↓
flow_controller.py  (all logic — slug, skip, lock, meta)
   ↓
ONE unit runs
   ↓
Unit produces files  →  .runtime/output/{slug}/
   ↓
Next run reads those files
```

---

## 🎯 ONE-LINE SUMMARY

> **Flow controls execution — Units generate outputs — Files connect everything — LLM is centralized — Config defines identity.**

=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
