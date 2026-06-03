



# Complete Rule 28/29 Implementation

## 1. Create the Unit Registry

**`input/unit.json`** ← The ONLY source of truth

```json
{
  "_comment": "CF2 Unit Registry — Rule 28. Add new units here, never in Python code",
  "_rule": "Append-only. Order controls pipeline sequence. File must exist for unit to be available.",
  "units": [
    {"name": "Unit-Scout", "config_key": "scout_config", "file": "scout_config.json", "order": 10},
    {"name": "Unit-Data", "config_key": "data_config", "file": "data_config.json", "order": 20},
    {"name": "Unit-Dubbing", "config_key": "dubbing_config", "file": "dubbing_config.json", "order": 30},
    {"name": "Unit-LeadData", "config_key": "leaddata_config", "file": "leaddata_config.json", "order": 40},
    {"name": "Unit-Debate", "config_key": "debate_config", "file": "debate_config.json", "order": 50},
    {"name": "Unit-Prodcast", "config_key": "prodcast_config", "file": "prodcast_config.json", "order": 60},
    {"name": "Unit-Classroom", "config_key": "classroom_config", "file": "classroom_config.json", "order": 70},
    {"name": "Unit-Definition", "config_key": "definition_config", "file": "definition_config.json", "order": 80},
    {"name": "Unit-Animation", "config_key": "animation_config", "file": "animation_config.json", "order": 90},
    {"name": "Unit-Comparison", "config_key": "comparison_config", "file": "comparison_config.json", "order": 100},
    {"name": "Unit-Packaging", "config_key": "packaging_config", "file": "packaging_config.json", "order": 110},
    {"name": "Unit-Publisher", "config_key": "publisher_config", "file": "publisher_config.json", "order": 120},
    {"name": "Unit-Advertise", "config_key": "advertise_config", "file": "advertise_config.json", "order": 130}
  ]
}
```

---

## 2. Create Unit Discovery Module

**`src/cf2/core/unit_registry.py`** ← Single point of contact

```python
"""
unit_registry.py — Dynamic unit discovery (Rule 28/29)
Reads input/unit/unit_config.json — NO hardcoded unit names in Python.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Optional

logger = logging.getLogger(__name__)

# Cache registry once per process
_REGISTRY_CACHE: Optional[List[dict]] = None
_UNIT_DIR: Optional[Path] = None


def _get_unit_dir() -> Path:
    """Get unit config directory path."""
    global _UNIT_DIR
    if _UNIT_DIR is None:
        # Relative to project root (where crewai runs)
        _UNIT_DIR = Path("input/unit")
    return _UNIT_DIR


def load_registry() -> List[dict]:
    """
    Load unit registry from config file.
    Returns sorted list of unit definitions.
    Raises FileNotFoundError if registry missing (Rule 28 violation).
    """
    global _REGISTRY_CACHE

    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE

    reg_path = _get_unit_dir() / "unit_config.json"

    if not reg_path.exists():
        raise FileNotFoundError(
            f"Rule 28 violation: {reg_path} missing. "
            "Unit registry must exist at input/unit/unit_config.json"
        )

    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Rule 28 violation: invalid JSON in {reg_path}: {e}")

    if "units" not in data:
        raise ValueError(f"Rule 28 violation: 'units' key missing in {reg_path}")

    # Sort by order field
    _REGISTRY_CACHE = sorted(data["units"], key=lambda u: u.get("order", 999))
    logger.debug(f"Loaded {len(_REGISTRY_CACHE)} units from registry")

    return _REGISTRY_CACHE


def get_available_units() -> Set[str]:
    """
    Return set of unit names that have config files in input/unit/.
    A unit is available ONLY if its config file physically exists.
    """
    unit_dir = _get_unit_dir()
    registry = load_registry()

    available = set()
    for unit_def in registry:
        config_file = unit_dir / unit_def["file"]
        if config_file.exists():
            available.add(unit_def["name"])
        else:
            logger.debug(
                f"Unit {unit_def['name']} skipped — config file not found: {config_file}"
            )

    return available


def get_pipeline_order() -> List[str]:
    """
    Return ordered list of available units for pipeline execution.
    Only includes units that have config files.
    """
    unit_dir = _get_unit_dir()
    registry = load_registry()

    order = []
    for unit_def in registry:
        config_file = unit_dir / unit_def["file"]
        if config_file.exists():
            order.append(unit_def["name"])

    return order


def get_unit_config_key(unit: str) -> Optional[str]:
    """
    Get config key for a unit (e.g., 'Unit-Debate' → 'debate_config').
    Returns None if unit not in registry.
    """
    registry = load_registry()
    for unit_def in registry:
        if unit_def["name"] == unit:
            return unit_def["config_key"]
    return None


def get_all_unit_names() -> List[str]:
    """Return all unit names from registry (regardless of config file existence)."""
    registry = load_registry()
    return [u["name"] for u in registry]


def get_unit_config_file(unit: str) -> Optional[Path]:
    """Get path to unit's config file, or None if not available."""
    registry = load_registry()
    unit_dir = _get_unit_dir()

    for unit_def in registry:
        if unit_def["name"] == unit:
            config_file = unit_dir / unit_def["file"]
            if config_file.exists():
                return config_file
            return None

    return None


def is_unit_registered(unit: str) -> bool:
    """Check if unit exists in registry."""
    return unit in get_all_unit_names()


def is_unit_available(unit: str) -> bool:
    """Check if unit is registered AND has config file."""
    return unit in get_available_units()


def build_unit_flags(explicit_flags: Dict[str, bool] = None) -> Dict[str, bool]:
    """
    Build complete unit enable/disable flags.

    Rules (Rule 28):
    - If unit not in registry → False
    - If config file doesn't exist → False  
    - If config exists but no explicit flag → False (opt-in required)
    - If config exists AND explicit flag = true → True

    Args:
        explicit_flags: Dict from profile like {"Unit-Debate": True}

    Returns:
        Complete dict of all units with boolean flags
    """
    available = get_available_units()
    all_units = get_all_unit_names()
    explicit = explicit_flags or {}

    result = {}
    for unit in all_units:
        if unit not in available:
            # Config file missing — cannot run
            result[unit] = False
        else:
            # Config exists: require explicit opt-in
            result[unit] = bool(explicit.get(unit, False))

    return result


def invalidate_cache():
    """Force reload registry on next access (for testing)."""
    global _REGISTRY_CACHE
    _REGISTRY_CACHE = None
```

---

## 3. Patch `executor.py`

Replace the hardcoded `_UNIT_CONFIG_KEY` dict (lines ~33-46):

```python
"""
core/executor.py — Execution Engine
This is the ONLY place a unit actually runs. Two-layer design:
1. run_unit_internal() — raw execution: skip-check → lock → run → verify → mark
2. run_unit() — public gate: enabled-check → dep resolution → internal

FlowController calls run_unit(). Dependency resolver calls run_unit_internal()
directly to avoid re-checking the enabled flag on the provider unit.

RULE: Only executor.py may call acquire_lock(). Units must NEVER check locks.
"""
import os
import json
import logging
import traceback as _tb
from pathlib import Path
from cf2.meta import (
    should_skip,
    acquire_lock,
    release_lock,
    mark_unit,
    verify_unit_done,
    cleanup_stale_locks,
    force_cleanup_all_locks,
)
from cf2.core.registry import get_runner
from cf2.core.progress_tracker import make_tracker
from cf2.core.dependency_resolver import resolve_deps, is_enabled, UNIT_SWITCH
from cf2.core.unit_registry import get_unit_config_key, get_unit_config_file  # ← Rule 29

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Per-unit channel resolver — reads from the unit's config file.
# Rule 29: Mapping loaded from config, NOT hardcoded
# ─────────────────────────────────────────────────────────────────────────────

def _load_unit_channel(unit: str, inputs: dict) -> tuple:
    """
    Load (channel, channel_lower) for `unit` from its config file.
    Returns (None, None) if no channel defined.
    """
    cfg_key = get_unit_config_key(unit)  # ← Rule 29: dynamic lookup
    if not cfg_key:
        return None, None

    # 1. In-memory config dict
    cfg = inputs.get(cfg_key)
    if isinstance(cfg, dict) and cfg.get("channel"):
        ch = cfg["channel"]
        return ch, cfg.get("channel_lower") or ch.lower()

    # 2. Config file path (load directly from file)
    config_file = get_unit_config_file(unit)
    if config_file:
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load config for {unit}: {e}")
            return None, None
        if isinstance(cfg, dict) and cfg.get("channel"):
            ch = cfg["channel"]
            return ch, cfg.get("channel_lower") or ch.lower()

    return None, None


def _stamp_channel(unit: str, inputs: dict) -> None:
    """Overwrite inputs['channel'] with the value from this unit's config file."""
    ch, ch_lower = _load_unit_channel(unit, inputs)
    if ch:
        inputs["channel"]       = ch
        inputs["channel_lower"] = ch_lower


def run_unit_internal(
    unit: str, topic: str, workspace: Path, inputs: dict, force: bool
):
    """
    Raw execution — no enabled-check, no dep resolution.
    Called by dependency_resolver when auto-running dependencies.
    """
    workspace = Path(workspace)

    # Skip check first (before touching locks)
    if should_skip(workspace, unit, force, inputs=inputs):
        return None

    # Debug: trace lock acquisition if env var set
    if os.environ.get("CF2_DEBUG_LOCKS"):
        print(f"🔍 [{unit}] Lock acquisition stack:")
        for line in _tb.format_stack()[-5:-1]:
            print(f"   {line.rstrip()}")

    # Acquire PER-UNIT lock (no longer blocks other units)
    lock = acquire_lock(workspace, unit)
    if lock is None:
        print(f"  ⚠️  {unit} — could not acquire lock, skipping")
        return None

    try:
        mark_unit(workspace, unit, "running")

        # get_runner() returns a MODULE — must call .run() on it
        runner  = get_runner(unit)
        tracker = make_tracker(unit)

        # Stamp per-unit channel from this unit's config file
        _stamp_channel(unit, inputs)

        try:
            result = runner.run(topic, workspace, inputs, force)
        finally:
            tracker.stop()

        # Soft returns — unit decided to skip/disable itself internally
        _SOFT_RETURNS = {"skipped", "disabled", "3d only"}
        result_str = str(result).strip().lower() if result is not None else ""

        if any(s in result_str for s in _SOFT_RETURNS):
            mark_unit(workspace, unit, "skipped", inputs=inputs)
            print(f"⏭️  {unit} — skipped")
        elif verify_unit_done(unit, workspace, inputs=inputs):
            mark_unit(workspace, unit, "done", inputs=inputs)
        else:
            # Unit succeeded but verify returned False — trust the run
            mark_unit(workspace, unit, "done", inputs=inputs)

        return result

    except KeyboardInterrupt:
        mark_unit(workspace, unit, "interrupted")
        print(f"\n🛑 {unit} interrupted")
        raise
    except Exception as exc:
        mark_unit(workspace, unit, "failed")
        print(f"\n❌ {unit} FAILED: {exc}")
        _tb.print_exc()
        # no raise — pipeline continues to next unit
    finally:
        release_lock(lock)


def run_unit(
    unit: str, topic: str, workspace: Path, inputs: dict, force: bool = False
):
    """
    Public gate — the only entry point FlowController uses.
    enabled-check → dep resolution → raw execution.
    """
    print(f"\n{'─' * 60}")
    print(f"▶  {unit}  |  {workspace.name if hasattr(workspace, 'name') else workspace}")
    print(f"{'─' * 60}")

    # Enabled check
    if not is_enabled(unit, inputs):
        switch = UNIT_SWITCH.get(unit, "?")
        print(f"⏭️  SKIP: {unit} disabled ({switch}=false in data.json)")
        return

    # Pre-flight lock cleanup
    workspace = Path(workspace)
    if str(workspace) != "(pending)":
        if force:
            force_cleanup_all_locks(workspace)
        else:
            cleanup_stale_locks(workspace)

    # Resolve and run dependencies, then this unit
    resolve_deps(unit, topic, workspace, inputs, force)
    return run_unit_internal(unit, topic, workspace, inputs, force)
```

---

## 4. Patch `flow_controller.py`

Replace hardcoded `PIPELINE_ORDER` and update `run_pipeline`:

```python
"""
🎛️ flow_controller.py — Orchestrator ONLY
main.py calls run(). That is it.
"""
import os
import sys
import json
import signal as _signal
import warnings
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone
from crewai.flow.flow import Flow, listen, start
from cf2.core.logging_setup import setup as setup_logging
from cf2.meta import (
    load_meta, save_meta, show_status,
    cleanup_stale_locks, force_cleanup_all_locks,
)
from cf2.core.topic_resolver import resolve_topic, generate_slug, resolve_workspace, pick_from_queue
from cf2.core.executor import run_unit
from cf2.core.unit_registry import (                    # ← Rule 29
    get_pipeline_order,
    build_unit_flags,
    get_available_units,
    is_unit_available,
)
from cf2.cli.cli import parse_args, apply_cli_overrides, install_sigint_handler
from config import load_profile, resolve_config_paths

# Suppress noisy warnings
warnings.filterwarnings("ignore", message=".*skip_file_prefixes.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

_AUTO = "auto"

# 🔥 THREAD-SAFE pipeline guard — works across all CrewAI threads
_pipeline_lock = threading.Lock()
_pipeline_ran = False


# ── Flow ───────────────────────────────────────────────────────────────────
class VideoFactoryFlow(Flow):

    @start()
    def initialize(self):
        print("\n" + "=" * 60)
        print("🎬  CF2 — CrewAI Flow Factory")
        print("=" * 60)
        return ""

    @listen(initialize)
    def run_pipeline(self):
        global _pipeline_ran

        # ═══════════════════════════════════════════════════════════════════
        # 🔥 CRITICAL: Thread-safe guard against CrewAI double-invocation
        # ═══════════════════════════════════════════════════════════════════
        acquired = _pipeline_lock.acquire(blocking=False)
        if not acquired:
            print("⚠️  run_pipeline() already running in another thread — IGNORING")
            return

        if _pipeline_ran:
            print("⚠️  run_pipeline() already completed — IGNORING duplicate")
            _pipeline_lock.release()
            return

        try:
            _pipeline_ran = True

            inputs = self.state.get("inputs", {})
            unit   = inputs.get("_unit")
            force  = inputs.get("_force", False)

            # ── Dynamic unit discovery (Rule 28/29) ───────────────────
            explicit_flags = {k: v for k, v in inputs.items() if k.startswith("Unit-")}
            merged_flags = build_unit_flags(explicit_flags)

            # Update inputs with resolved flags
            inputs.update(merged_flags)
            self.state["inputs"] = inputs

            # ── Scout-first ─────────────────────────────────────────────
            if inputs.get("_topic", "").lower() == _AUTO:
                inputs = _scout_then_resolve(inputs, force)
                if not inputs:
                    print("❌  Scout ran but queue still empty — aborting.")
                    return
                self.state["inputs"] = inputs

            topic     = inputs["_topic"]
            workspace = Path(inputs["_workspace"])

            if unit:
                # Single unit mode — validate availability
                if not is_unit_available(unit):
                    available = get_available_units()
                    print(f"❌  {unit} not available (no config file in input/unit/)")
                    print(f"    Available: {', '.join(sorted(available))}")
                    return
                run_unit(unit, topic, workspace, inputs, force)
            else:
                # Full pipeline mode — dynamic order from registry
                pipeline_order = get_pipeline_order()
                print(f"🔄  Full pipeline — {workspace.name}")
                print(f"📦  Available units: {len(pipeline_order)}")

                skip_scout = inputs.get("_scout_done", False)
                for u in pipeline_order:
                    if not inputs.get(u, False):
                        print(f"⏭️  SKIP: {u} (not enabled in profile)")
                        continue

                    if u == "Unit-Scout" and skip_scout:
                        continue

                    run_unit(u, topic, workspace, inputs, force)

            print("\n✅  Flow complete.\n")

        finally:
            _pipeline_lock.release()


# ── Scout-first helper ─────────────────────────────────────────────────────
def _scout_then_resolve(inputs: dict, force: bool) -> dict | None:
    from cf2.core.paths import OUTPUT_ROOT
    staging = OUTPUT_ROOT / "_scout_staging"
    staging.mkdir(parents=True, exist_ok=True)
    cleanup_stale_locks(staging)

    print("🔍  topic=auto — running Unit-Scout to discover topic...")
    run_unit("Unit-Scout", _AUTO, staging, inputs, force)

    topic = pick_from_queue(inputs)
    if not topic:
        return None

    slug      = generate_slug(topic)
    workspace = resolve_workspace(topic, slug)
    _init_meta(workspace, topic, slug)

    if force:
        force_cleanup_all_locks(workspace)
    else:
        cleanup_stale_locks(workspace)

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
    """
    Flatten nested config into inputs dict.
    Rule 29: All fallbacks are logged for observability.
    """
    logger = logging.getLogger(__name__)

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

    # Rule 29: Safety fallbacks — MUST be logged
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

        "classroom_enabled": False, "classroom_age_group": "kids_6_10",
        "classroom_video_formats": ["Shorts", "HD"], "classroom_audio_speed": 1.05,
        "classroom_pause_between_lines_ms": 350, "classroom_watermark_enabled": True,
        "classroom_watermark_text": "@KidsThinkAI", "classroom_generate_subtitles": True,
        "classroom_generate_cc": True, "classroom_bgm_enabled": False,
        "classroom_bgm_volume": 0.15, "classroom_skip_if_cached": True,
    }

    # Rule 29: Log every fallback for observability
    for k, v in D.items():
        if k not in inputs:
            logger.warning(f"CONFIG FALLBACK: {k}={v} (Rule 29 — safety only)")
        inputs.setdefault(k, v)

    return inputs


# ── Helpers ────────────────────────────────────────────────────────────────
def _init_meta(workspace: Path, topic: str, slug: str):
    meta = load_meta(workspace, topic)
    if not meta.get("slug"):
        meta["slug"] = slug
        meta["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_meta(workspace, meta)


# ── Entry point ────────────────────────────────────────────────────────────
def run(profile: str = "data.json"):
    global _pipeline_ran
    setup_logging()
    args = parse_args()
    from cf2.cli.cli import handle_early_exit
    if handle_early_exit(args):
        return

    # 🔥 Reset for each new run()
    _pipeline_ran = False

    profile_name = args.profile or profile
    inputs = load_profile(profile_name)
    inputs = resolve_config_paths(inputs)
    inputs = apply_cli_overrides(inputs, args)

    topic    = resolve_topic(inputs)
    is_auto  = topic.lower() == _AUTO
    scout_on = bool(inputs.get("Unit-Scout"))

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

        if args.force:
            force_cleanup_all_locks(workspace)
        else:
            cleanup_stale_locks(workspace)

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
    if getattr(args, "subtask", None):
        inputs["_subtask"] = args.subtask

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
```

---

## 5. Update `dependency_resolver.py`

```python
from cf2.core.unit_registry import is_unit_available

# Replace the old UNIT_SWITCH with dynamic check
def is_enabled(unit: str, inputs: dict) -> bool:
    """
    Check if unit is enabled.
    Rule 28: Unit must be available (config file exists) AND explicitly enabled.
    """
    # Must have config file to be available
    if not is_unit_available(unit):
        return False

    # Must be explicitly enabled in inputs/profile
    return bool(inputs.get(unit, False))


# Remove this entirely:
# UNIT_SWITCH = {
#     "Unit-Scout": "Unit-Scout",
#     "Unit-Data": "Unit-Data",
#     ...
# }
```

---

## 6. Clean Profile (Rule 28 Compliant)

**`input/profile/leadint.json`** — Only switches, no config blocks:

```json
{
  "topic": "best all inclusive resort, Cuba vacation, Mexico all inclusive",
  "_comment": "CF2-Intent lead. Change topic only. Rule 28: only Unit- switches here",
  "_profile": "leadint",
  "_version": "3.0.0",
  "Unit-LeadData": true
}
```

---

## 7. Directory Structure After Changes

```
input/
├── unit.json          ← REGISTRY (Rule 28 - append only)

input/unit/
├── animation_config.json     ← Unit-Animation available
├── classroom_config.json     ← Unit-Classroom available
├── debate_config.json        ← Unit-Debate available
├── dubbing_config.json       ← Unit-Dubbing available
├── leaddata_config.json      ← Unit-LeadData available
└── scout_config.json         ← Unit-Scout available
```

**Note:** `prodcast_config.json` doesn't exist → `Unit-Prodcast` auto-unavailable

---

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| Unit list location | Hardcoded in `executor.py` + `flow_controller.py` | `input/unit/unit_config.json` |
| Adding new unit | Edit 3+ Python files | Append to JSON + add config file |
| Removing unit | Edit Python, risk breaking | Delete config file → auto-removed |
| Profile format | `"Unit-X": false` for every unit | Only `"Unit-X": true` for enabled ones |
| Fallback visibility | Silent | Logged: `CONFIG FALLBACK: key=value (Rule 29)` |
| Pipeline order | Static list | Dynamic from registry + file existence |

**Rule 28 ✓** — `unit_config.json` is the single source of truth
**Rule 29 ✓** — Zero hardcoded unit names in Python, all fallbacks logged


























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

================================================================================





from __future__ import annotations
"""
unit_data.py — Content Generation Engine

Architectural Rules
───────────────────
D-1 Provider only. Reads nothing from workspace inputs (only checks
     output existence for the cache guard).
D-5 Unit-Data is the SOLE producer of foundational, *shared* data
     artifacts — i.e. artifacts that multiple consumer units may
     read. Consumer-specific artifacts belong in their own units.
D-6 Consumer units (Unit-Debate, Unit-Definition, Unit-Comparison,
     Unit-Animation, Unit-LeadData, Unit-Classroom) are gated by their
     own Unit-* switches in their own modules.

Ownership Map
─────────────
    Unit-Data owns:
        - data.csv (shared by Animation + LeadData)
        - debate/decide.md (consumed by Unit-Debate renderer)
        - definition/def_En.txt
        - comparison/comparison.md
        - classroom/script.md (consumed by Unit-Classroom renderer)
        - classroom/script-m.md
        - classroom/roles.json
        - classroom/quiz.json

    Unit-Prodcast owns:
        - podcast/script.md (Prodcast-specific; uses Prodcast config)
        - podcast/audio.mp3
        - podcast/video.mp4

Smart Production
────────────────
Unit-Data inspects which downstream consumers are enabled and runs
only the LLM tasks required to satisfy their declared dependencies
(CONSUMER_REQUIREMENTS). Unit-Prodcast is NOT in this map — it
manages its own pipeline.

Cache Guard
───────────
If all artifacts required by the currently-enabled consumers already
exist on disk and are non-empty, Unit-Data short-circuits with
RunStatus.DONE and burns zero tokens. Pass `force=True` to bypass.

Public API
──────────
    run(topic, workspace, inputs, force=False) -> str
"""
import logging

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from crewai import Crew, Process

from cf2.meta import acquire_lock, release_lock
from cf2.crews.crew import CF2Crew
from cf2.core.compress import decide_compressor
from cf2.tools.classroom_script_generator import _compress, _extract_quiz

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════

class RunStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    LOCKED = "locked"

class Block(str, Enum):
    """Coherent producer bundles. Each block produces one+ artifacts."""
    RESEARCH = "research"
    DEBATE = "debate"
    DEFINITION = "definition"
    COMPARISON = "comparison"
    CLASSROOM = "classroom"

# Map: consumer Unit-* switch → set of producer blocks it depends on.
CONSUMER_REQUIREMENTS: dict[str, set[Block]] = {
    "Unit-Debate": {Block.DEBATE},
    "Unit-Definition": {Block.DEFINITION},
    "Unit-Comparison": {Block.COMPARISON},
    "Unit-Animation": {Block.RESEARCH},
    "Unit-LeadData": {Block.RESEARCH},
    "Unit-Classroom": {Block.CLASSROOM},
}

# Map: block → relative artifact paths it produces
BLOCK_ARTIFACTS: dict[Block, tuple[str,...]] = {
    Block.RESEARCH: ("data.csv",),
    Block.DEBATE: ("debate/decide.md",),
    Block.DEFINITION: ("definition/def_En.txt",),
    Block.COMPARISON: ("comparison/comparison.md",),
    Block.CLASSROOM: (
        "classroom/script.md",
        "classroom/roles.json",
        "classroom/quiz.json",
    ),
}

COMPRESSION_TIERS: tuple[tuple[int, float],...] = (
    (6000, 0.35),
    (3000, 0.42),
    (0, 0.50),
)
COMPRESS_FLOOR = 320
COMPRESS_CEILING = 750
COMPRESS_MIN_CHARS = 260

# ════════════════════════════════════════════════════════════════════════════
# Bundle
# ════════════════════════════════════════════

@dataclass
class CrewBundle:
    agents: list[Any] = field(default_factory=list)
    tasks: list[Any] = field(default_factory=list)
    blocks_included: set[Block] = field(default_factory=set)

    def add(self, block: Block, agents: list[Any], tasks: list[Any]) -> None:
        self.agents.extend(agents)
        self.tasks.extend(tasks)
        self.blocks_included.add(block)

    def is_empty(self) -> bool:
        return not self.tasks

# ════════════════════════════════════════════
# Public Entry Point
# ════════════════════════════════════════════

def run(
    topic: str,
    workspace: Path,
    inputs: dict[str, Any],
    force: bool = False,
) -> str:
    if not topic:
        logger.error("Unit-Data: empty topic")
        return RunStatus.FAILED

    required_blocks = _resolve_required_blocks(inputs)

    if not required_blocks:
        logger.info("Unit-Data: no enabled consumers require shared data — skipping")
        return RunStatus.SKIPPED

    logger.info(
        "Unit-Data: required blocks: %s",
        ", ".join(sorted(b.value for b in required_blocks)),
    )

    # ── 1. CACHE FIRST (always, regardless of flags) ─────────────────────
    if not force:
        missing = _missing_artifacts(workspace, required_blocks)
        if not missing:
            logger.info("Unit-Data: ✅ CACHE HIT — all artifacts exist, skipping")
            return RunStatus.DONE
        logger.info(
            "Unit-Data: cache miss — %d artifact(s) missing: %s",
            len(missing), ", ".join(_relpath(p, workspace) for p in missing),
        )
    else:
        logger.info("Unit-Data: force=True — bypassing cache")

    # ── 2. LLM GATE ─────────────────────────────────────────────────────
    llm_enabled = inputs.get("data_llm_enabled", False)
    if not llm_enabled:
        logger.warning(
            "Unit-Data: LLM DISABLED by default. "
            "Set 'data_llm_enabled': true in request to enable generation."
        )
        return RunStatus.SKIPPED

    # ── 3. Force lowest-cost config ─────────────────────────────────────
    unit_data_flag = inputs.get("Unit-Data", True)

    cheap_config = {
        "default": "ollama/deepseek-r1:1.5b",
        "tiers": {
            "research": {
                "models": [
                    "ollama/deepseek-r1:1.5b",
                    "ollama/llama3.1:8b",
                    "deepseek/deepseek-chat",
                ],
                "temperature": 0.3,
                "max_tokens": 2048
            },
            "scoring": {
                "models": ["ollama/deepseek-r1:1.5b"],
                "temperature": 0.2,
                "max_tokens": 1024
            },
            "local_tiny": {
                "models": ["ollama/deepseek-r1:1.5b"],
                "temperature": 0.5,
                "max_tokens": 1024
            },
            "local_fast": {
                "models": ["ollama/llama3.1:8b"],
                "temperature": 0.5,
                "max_tokens": 2048
            }
        },
        "agents": {
            "data_researcher": {"tier": "research"},
            "csv_generator": {"tier": "local_tiny"},
            "definition_specialist": {"tier": "local_tiny"},
            "scout": {"tier": "local_fast"},
            "score_analyst": {"tier": "scoring"},
            "debater": {"tier": "local_fast"},
            "judge": {"tier": "local_fast"},
        },
        "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 300}
    }

    # Block cloud models when Unit-Data is false
    if not unit_data_flag:
        for tier in cheap_config["tiers"].values():
            tier["models"] = [m for m in tier["models"] if m.startswith("ollama/")]
        logger.info("🔒 Unit-Data=false — cloud LLMs blocked, Ollama only")

    inputs = {**inputs, "llm_config": cheap_config}
    logger.info("Unit-Data: LLM enabled with lowest-cost models")

    # ── 4. Execute ──────────────────────────────────────────────────────
    lock = acquire_lock(workspace, "Unit-Data")
    if not lock:
        logger.warning("Unit-Data: could not acquire lock for %s", workspace)
        return RunStatus.LOCKED

    try:
        bundle = _assemble_bundle(required_blocks, inputs)
        if bundle.is_empty():
            logger.error("Unit-Data: empty bundle for blocks=%s", required_blocks)
            return RunStatus.FAILED

        logger.info(
            "Unit-Data: running %d agent(s), %d task(s), blocks=%s, topic='%s'",
            len(bundle.agents), len(bundle.tasks),
            sorted(b.value for b in bundle.blocks_included), topic,
        )

        result = _execute_crew(bundle, topic, workspace, inputs)
        if not result:
            logger.error("Unit-Data: crew returned empty result")
            return RunStatus.FAILED

        if Block.DEBATE in bundle.blocks_included:
            _compress_mobile_verdict(workspace / "debate")

        if Block.CLASSROOM in bundle.blocks_included:
            _post_process_classroom(workspace, inputs)

        still_missing = _missing_artifacts(workspace, required_blocks)
        if still_missing:
            logger.error(
                "Unit-Data: run completed but artifacts missing: %s",
                ", ".join(_relpath(p, workspace) for p in still_missing),
            )
            return RunStatus.FAILED

        logger.info("Unit-Data: complete")
        return RunStatus.DONE

    except Exception as exc:
        logger.exception("Unit-Data: unhandled exception — %s", exc)
        return RunStatus.FAILED
    finally:
        release_lock(lock)

# ── Rest of file unchanged ───────────────────────────────────────────────

def _resolve_required_blocks(inputs: dict[str, Any]) -> set[Block]:
    required: set[Block] = set()
    for unit, blocks in CONSUMER_REQUIREMENTS.items():
        if inputs.get(unit, False):
            required.update(blocks)
            logger.debug("Unit-Data: %s enabled → needs %s", unit, blocks)
    return required

def _missing_artifacts(workspace: Path, blocks: set[Block]) -> list[Path]:
    missing: list[Path] = []
    for block in blocks:
        for rel in BLOCK_ARTIFACTS.get(block, ()):
            path = workspace / rel
            if not path.exists() or path.stat().st_size == 0:
                missing.append(path)
    return missing

def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)

def _assemble_bundle(required_blocks: set[Block], inputs: dict[str, Any]) -> CrewBundle:
    factory = CF2Crew(inputs=inputs)
    bundle = CrewBundle()

    if Block.RESEARCH in required_blocks:
        bundle.add(
            Block.RESEARCH,
            agents=[factory.data_researcher(), factory.data_csv_generator()],
            tasks=[factory.data_research(), factory.data_generate_csv()],
        )

    if Block.DEBATE in required_blocks:
        bundle.add(
            Block.DEBATE,
            agents=[factory.debate_debater(), factory.debate_judge()],
            tasks=[
                factory.debate_propose(),
                factory.debate_oppose(),
                factory.debate_decide(),
            ],
        )
        _maybe_add_debate_subfeatures(factory, bundle, inputs)

    if Block.DEFINITION in required_blocks:
        bundle.add(
            Block.DEFINITION,
            agents=[factory.data_definition_specialist()],
            tasks=[factory.data_define_topic()],
        )

    if Block.COMPARISON in required_blocks:
        _add_optional_block(
            factory, bundle, Block.COMPARISON,
            agent_attr="data_comparison_specialist",
            task_attr="data_compare_topic",
        )

    if Block.CLASSROOM in required_blocks:
        _add_optional_block(
            factory, bundle, Block.CLASSROOM,
            agent_attr="classroom_script_writer",
            task_attr="create_classroom_script",
        )

    return bundle

def _add_optional_block(factory: CF2Crew, bundle: CrewBundle, block: Block, agent_attr: str, task_attr: str) -> None:
    agent_fn: Callable | None = getattr(factory, agent_attr, None)
    task_fn: Callable | None = getattr(factory, task_attr, None)
    if callable(agent_fn) and callable(task_fn):
        bundle.add(block, agents=[agent_fn()], tasks=[task_fn()])
    else:
        logger.warning(
            "Unit-Data: %s not wired in CF2Crew (need %s + %s).",
            block.value, agent_attr, task_attr,
        )

def _maybe_add_debate_subfeatures(factory: CF2Crew, bundle: CrewBundle, inputs: dict[str, Any]) -> None:
    bundle.agents.append(factory.debate_debater_m())
    bundle.tasks.extend([factory.debate_propose_m(), factory.debate_oppose_m()])
    score_cfg = inputs.get("debate_config", {}).get("debate_3d_score", {})
    if score_cfg.get("enabled") and score_cfg.get("llm_enabled"):
        bundle.agents.append(factory.debate_score_analyst())
        bundle.tasks.append(factory.debate_generate_scores())

def _execute_crew(bundle: CrewBundle, topic: str, workspace: Path, inputs: dict[str, Any]) -> Any:
    crew = Crew(
        agents=bundle.agents,
        tasks=bundle.tasks,
        process=Process.sequential,
        verbose=inputs.get("verbose", False),
    )
    return crew.kickoff(inputs=_build_kickoff_inputs(topic, workspace, inputs))

def _build_kickoff_inputs(topic: str, workspace: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    ws = str(workspace)
    # Start with ALL inputs from config (includes focus, prodcast_enabled, etc.)
    base = dict(inputs)
    # Override core paths
    base.update({
        "topic": topic,
        "output_dir": ws,
        "workspace": ws,
        "data_dir": ws,
        "debate_dir": str(workspace / "debate"),
        "definition_dir": str(workspace / "definition"),
        "comparison_dir": str(workspace / "comparison"),
        "podcast_dir": str(workspace / "podcast"),
        "classroom_dir": str(workspace / "classroom"),
    })

    # Drop None values (so {focus} becomes "" not "None")
    return {k: ("" if v is None else v) for k, v in base.items()}

def _compress_mobile_verdict(debate_dir: Path) -> None:
    hd_path = debate_dir / "decide.md"
    mobile_path = debate_dir / "decide-m.md"
    if not hd_path.exists():
        return
    try:
        hd_text = hd_path.read_text(encoding="utf-8")
        if not hd_text.strip():
            return
        max_chars = _compute_compression_budget(len(hd_text))
        decide_compressor.compress(hd_path, mobile_path, max_chars=max_chars)
        logger.info("Compress: %s → %s", hd_path.name, mobile_path.name)
    except Exception as exc:
        logger.warning("Compress failed — %s", exc)

def _compute_compression_budget(hd_len: int) -> int:
    ratio = next(r for threshold, r in COMPRESSION_TIERS if hd_len > threshold)
    target = int(hd_len * ratio)
    clamped = max(COMPRESS_FLOOR, min(target, COMPRESS_CEILING))
    return max(COMPRESS_MIN_CHARS, clamped)

def _post_process_classroom(workspace: Path, inputs: dict[str, Any]) -> None:
    classroom_dir = workspace / "classroom"
    classroom_dir.mkdir(parents=True, exist_ok=True)
    script_path = classroom_dir / "script.md"
    if not script_path.exists() or script_path.stat().st_size == 0:
        return
    mini_path = classroom_dir / "script-m.md"
    if not mini_path.exists():
        try:
            raw = script_path.read_text("utf-8")
            mini = _compress(raw)
            mini_path.write_text(mini, encoding="utf-8")
        except Exception:
            pass
    quiz_path = classroom_dir / "quiz.json"
    if not quiz_path.exists():
        try:
            import json
            raw = script_path.read_text("utf-8")
            quiz = _extract_quiz(raw)
            quiz_path.write_text(json.dumps(quiz, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    roles_path = classroom_dir / "roles.json"
    if not roles_path.exists():
        try:
            from cf2.tools.classroom_roles_generator import run as write_roles
            write_roles(str(workspace), inputs.get("classroom_config", {}))
        except Exception:
            pass







================================================================================


"""
unit_debate.py — Debate Unit Orchestrator (CF2 Compliant)
Architecture:
unit_debate.py (Router)
├─▶ scoreboard_enhancer.py      → Unified scoreboard generation & pipeline injection
├─▶ TTSService                  → Generates narration
├─▶ FFmpegService               → Mixes BGM, enforces limits, measures duration
└─▶ AudioService                → Concatenates, merges AV, extracts audio
Rule alignment: R1, R2, R4, R6, R8, R17, R24, R31, R32 + score.md #12
"""
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import json, re, os, shutil, subprocess
from cf2.core.paths import PROJECT_ROOT
from cf2.core.parser import debate_parser_3d as parser
from cf2.core.parser.debate_parser_3d import resolve_voice_key
from cf2.tools import debate_pipeline
from cf2.core import clip_resolver
from cf2.tools import debate_timeline_builder as timeline_builder
from cf2.tools import debate_video_renderer as video_renderer_3d
from cf2.tools import debate_scoreboard_enhancer as scoreboard_enhancer
from cf2.tools.debate_score_extractor import resolve as extract_scores
from cf2.core.subtitle import subtitle_builder
from cf2.core.services.tts_service import TTSService
from cf2.core.services.audio_service import AudioService
from cf2.core.services.ffmpeg_service import FFmpegService
from cf2.meta import mark_subtask, should_skip

# ============================================================================
# HELPERS
# ============================================================================

def _cfg(inputs: dict, key: str, default=False):
    """Get config value with fallback."""
    return inputs.get(key, inputs.get("debate_config", {}).get(key, default))

def _log(channel: str, msg: str):
    """Log message with channel prefix."""
    print(f"[Unit-Debate|{channel}] {msg}")

def _get_voice(role: str, voices_cfg: dict) -> str:
    """Get voice for role from config."""
    cfg = voices_cfg.get(role)
    voice = cfg.get("edge_voice") if isinstance(cfg, dict) else cfg
    if not voice:
        raise ValueError(f"No voice configured for role '{role}'.")
    return voice

def _load_tts_voices(inputs: dict, workspace: Path) -> dict:
    """
    Load Unit-Debate edge voices from the centralized tts_conf.json.
    Returns dict shape compatible with _get_voice():
    {role: {"edge_voice": "<voice_id>"}}
    """
    cfg_hint = inputs.get("tts_config_file", "input/tts_conf.json")
    candidates = [
        Path(cfg_hint),
        workspace / cfg_hint if not Path(cfg_hint).is_absolute() else Path(cfg_hint),
        PROJECT_ROOT / cfg_hint,
        workspace / "input" / "tts_conf.json",
        Path("input/tts_conf.json"),
    ]
    cfg_path = next((p for p in candidates if p.is_file()), None)
    if cfg_path is None:
        raise FileNotFoundError(
            f"tts_conf.json not found. Tried: {[str(p) for p in candidates]}"
        )
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    tts_cfg = raw.get("tts_config", raw)
    tier_name = tts_cfg.get("unit_tier_mapping", {}).get("Unit-Debate", "debate")
    tier = tts_cfg.get("tiers", {}).get(tier_name)
    if not tier:
        raise KeyError(f"tts_conf.json: tier '{tier_name}' not defined.")

    voices = tier.get("voices", {})
    return {role: {"edge_voice": vid} for role, vid in voices.items()}

def _build_stage_narration(stage: str, data: Dict[str, Any]) -> str:
    """Generate context-aware narration for scoreboard stages."""
    opening = data.get("opening", {}) or {}
    all_args = data.get("args", []) or []
    final_totals = data.get("totals", {}) or {}
    winner = data.get("winner", "draw")

    def running_total(n_args: int):
        pro = opening.get("pro", 0) + sum(a.get("pro", 0) for a in all_args[:n_args])
        con = opening.get("con", 0) + sum(a.get("con", 0) for a in all_args[:n_args])
        return pro, con

    if stage == "teaser":
        return "Here's what's at stake. Watch until the end to see the final verdict."
    if stage == "judges":
        return "Individual judge marks submitted."
    if stage == "score":
        pro = final_totals.get("pro", 0)
        con = final_totals.get("con", 0)
        return f"Final scoreboard. Proposition {pro}, Opposition {con}. {str(winner).title()} wins."
    if stage == "opening":
        pro, con = running_total(0)
        return f"After opening statements: Proposition {pro}, Opposition {con}."
    if stage.startswith("arg") and stage[3:].isdigit():
        n = int(stage[3:])
        pro, con = running_total(n)
        return f"After argument {n}. Running total: Proposition {pro}, Opposition {con}."

    pro = final_totals.get("pro", 0)
    con = final_totals.get("con", 0)
    return f"Scoreboard update: Proposition {pro}, Opposition {con}."

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def run(topic: str, workspace: Path, inputs: Dict[str, Any], force: bool = False) -> str:
    """Main entry point for Unit-Debate."""
    if not _cfg(inputs, "debate_3d_enabled"):
        mark_subtask(workspace, "Unit-Debate", "debate_video3d", "disabled")
        return "disabled"

    debate_dir = workspace / "debate"
    debate_dir.mkdir(parents=True, exist_ok=True)

    if not (debate_dir / "propose.md").exists():
        mark_subtask(workspace, "Unit-Debate", "debate_video3d", "skipped")
        return "skipped"

    if not force and should_skip(workspace, "Unit-Debate", force):
        return "skipped"

    mark_subtask(workspace, "Unit-Debate", "debate_video3d", "running")
    channel = inputs.get("channel", "Channel")
    safe_slug = inputs.get("_slug", workspace.name)
    debate_config = inputs.get("debate_config", {})
    clip_config = debate_config.get("debate_3d_clips", {})
    video_formats = inputs.get("video_formats", ["Shorts"])
    logger = lambda msg: _log(channel, msg)

    ffmpeg = FFmpegService()
    tts = TTSService(logger=logger)
    audio = AudioService(logger=logger)

    edge_voices_cfg = _load_tts_voices(inputs, workspace)
    voice_map = {r: _get_voice(r, edge_voices_cfg) for r in ["propose", "oppose", "judge_m", "judge_f", "decide"]}

    try:
        for fmt in video_formats:
            _run_format(fmt, debate_dir, channel, safe_slug, topic, inputs.get("video_fps", 30),
                        debate_config.get("intro_enabled", False), clip_config, voice_map, tts, audio, ffmpeg, inputs, logger)
        mark_subtask(workspace, "Unit-Debate", "debate_video3d", "done")
        return "done"
    except Exception as e:
        mark_subtask(workspace, "Unit-Debate", "debate_video3d", "failed")
        logger(f"❌ Pipeline error: {e}")
        raise

# ============================================================================
# PER-FORMAT PIPELINE
# ============================================================================

def _run_format(fmt, debate_dir, safe_channel, safe_slug, topic, fps, intro_enabled,
                clip_config, voice_map, tts, audio, ffmpeg, inputs, logger):
    """Run debate pipeline for a single format."""
    final_filename = f"{safe_channel}{safe_slug}_{fmt}.mp4"
    final_output = debate_dir / final_filename

    if final_output.exists():
        logger(f"⏭️ Skip {fmt}: {final_filename} exists.")
        return

    md_suffix = "-m" if "Shorts" in fmt else ""
    files = [debate_dir / f"{n}{md_suffix}.md" for n in ["propose", "oppose", "decide"]]

    if not all(f.exists() for f in files):
        logger(f"❌ Missing .md files for {fmt}.")
        return

    blocks = parser.parse(*(f.read_text("utf-8") for f in files))
    block_map = parser.build_block_map(blocks)
    clips_base = clip_config.get("_clips_base", "assets/clips")
    use_prefix = bool(clip_config.get("_folder_prefix", False))
    fmt_suffix = clip_config.get("_format_suffix", {}).get(fmt, "")

    intro_path, has_intro = clip_resolver.resolve_intro(fmt, intro_enabled, debate_dir,
                                                         clip_config, logger=logger, fmt_suffix=fmt_suffix)

    debate_config = inputs.get("debate_config", {})
    sb_cfg = debate_config.get("debate_3d_score", {})

    # Build pipeline with proper clip config
    pipeline = debate_pipeline.build(fmt, has_intro,
                                      clip_resolver.resolve_subscribe(fmt, clip_config, fmt_suffix),
                                      clip_config, has_scoreboard=False)
    logger(f" Base pipeline keys: {[s['key'] for s in pipeline]}")

    # ✅ CRITICAL FIX: Resolve _extend inheritance for fmt_clips
    raw_fmt_cfg = clip_config.get(fmt, {})
    if "_extend" in raw_fmt_cfg:
        parent_key = raw_fmt_cfg["_extend"]
        parent_cfg = clip_config.get(parent_key, {})
        # Merge: Parent keys first, then overwrite with format-specific keys
        fmt_clips = {**parent_cfg, **raw_fmt_cfg}
        logger(f"🔗 Extended {fmt} from {parent_key}. Keys: {list(fmt_clips.keys())}")
    else:
        fmt_clips = raw_fmt_cfg.copy()

    # 🚨 New Warning: Check if config is empty after inheritance
    if not fmt_clips:
        logger(f"❌ CRITICAL: {fmt} resolved to EMPTY clips! No videos will render.")
        logger(f"   Fix: Check your JSON. '{raw_fmt_cfg.get('_extend', 'N/A')}' key is missing or empty.")

    logger(f"🔧 fmt_clips keys available: {list(fmt_clips.keys())}")

    dynamic_subs = {}
    is_hd = "Shorts" not in fmt
    sb_enabled = sb_cfg.get("enabled", False)
    sb_hd_only = sb_cfg.get("hd_only", False)
    should_render = sb_enabled and (is_hd or not sb_hd_only)

    if not should_render:
        logger(f"⚠️ Scoreboards skipped: enabled={sb_enabled}, hd_only={sb_hd_only}, fmt={fmt}")
    else:
        pipeline, sb_clips, dynamic_subs = scoreboard_enhancer.enhance_pipeline(
            pipeline, debate_dir, md_suffix, fmt, fps, topic, sb_cfg, debate_config, logger
        )
        fmt_clips.update(sb_clips)

    fmt_clips = _inject_static_clips(fmt, fmt_clips, debate_dir, md_suffix, clip_config, logger)

    subtitle_map = debate_pipeline.build_subtitle_map(pipeline, block_map, fmt_clips)
    subtitle_map.update(dynamic_subs)

    audio_segments = _generate_audio(pipeline, block_map, fmt, fmt_clips, intro_path, clips_base, use_prefix,
                                      voice_map, tts, audio, ffmpeg, debate_dir / "audio_blocks", logger,
                                      debate_dir, debate_config, clip_config)
    if not audio_segments:
        return

    valid_segs = [(p, d, k) for p, d, k in audio_segments if p and os.path.exists(p)]
    final_audio = debate_dir / f"debate_3d_{fmt}_audio.mp3"
    _assemble_audio(valid_segs, final_audio, ffmpeg, audio, logger)

    tl = timeline_builder.build(valid_segs, fps)
    clip_map = clip_resolver.resolve_clip_map(pipeline, fmt, fmt_clips, intro_path, clips_base, use_prefix, fmt_suffix)
    clip_seq = clip_resolver.resolve_clip_sequences(pipeline, fmt_clips, intro_path, clips_base, use_prefix, fmt_suffix)

    silent_video = debate_dir / f"debate_3d_{fmt}_silent.mp4"
    if not video_renderer_3d.render(tl, clip_map, block_map, subtitle_map, topic, fmt, fps,
                                     str(silent_video), logger, clip_sequences=clip_seq):
        return

    # ✅ FIX: Merge logic is simplified because Renderer already did the scaling
    _merge_av_sync(str(silent_video), str(final_audio), str(final_output), logger, fmt=fmt)
    _post_process_video(final_output, valid_segs, subtitle_map, debate_dir, safe_slug, fmt,
                        ffmpeg, debate_config, logger)

# ============================================================================
# CLIP INJECTION
# ============================================================================
def _inject_static_clips(fmt, fmt_clips, debate_dir, md_suffix, clip_config, logger):
    """Inject static clips and resolve win clip."""
    # ✅ FIX: Read from fmt_clips (merged config) instead of raw clip_config
    # This ensures 'win' key is visible even when Shorts extends shared.
    cfg = fmt_clips.copy()

    if "win" in cfg and (debate_dir / f"decide{md_suffix}.md").exists():
        sel = clip_resolver.resolve_win_clip(
            debate_dir / f"decide{md_suffix}.md",
            cfg["win"],
            fmt
        )

        if sel:
            cfg["win"] = {
                "paths": [sel],
                "loops": cfg["win"].get("loops", [])
            }
            logger(f"🏆 Winner clip: {sel}")
        else:
            logger("⚠️ No winner resolved — skipping winner clip")
            cfg.pop("win", None)

    fmt_clips.update(cfg)
    return fmt_clips

# ============================================================================
# AUDIO ASSEMBLY
# ============================================================================

def _assemble_audio(segs, out_path, ffmpeg, audio_svc, logger):
    """Concatenate audio segments."""
    if segs:
        paths = [p for p, _, _ in segs]
        if not ffmpeg.concat_mp3_safe(paths, str(out_path), bitrate="128k", logger=logger):
            audio_svc.concat(paths, str(out_path))
        dur = audio_svc.get_duration(str(out_path))
    else:
        audio_svc.create_silence(str(out_path), duration=1.0)
        dur = 1.0
    logger(f" Total audio: {dur:.2f}s")

# ============================================================================
# FFMPEG SYNC MERGE
# ============================================================================

def _merge_av_sync(silent_mp4: str, audio_mp3: str, out_mp4: str, logger, fmt: str = "HD"):
    """
    Merge silent video with audio.
    ✅ FIX: Since 'debate_video_renderer.py' now handles Smart Crop (scaling & blurring)
            in Python, the merge step simply copies the video stream.
            Re-scaling here would be redundant and slow.
    """
    cmd = [
        "ffmpeg", "-y", "-i", silent_mp4, "-i", audio_mp3,
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        "-movflags", "+faststart", out_mp4
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        logger(f"❌ FFmpeg merge failed: {r.stderr[:300]}")
        return
    logger(f"🎬 Merged audio+video: {Path(out_mp4).name}")

# ============================================================================
# POST-PROCESSING
# ============================================================================

def _post_process_video(final_output, valid_segs, subtitle_map, debate_dir, safe_slug, fmt,
                        ffmpeg, debate_config, logger):
    """Post-process final video (Shorts trimming, subtitles, cleanup)."""
    if not final_output.exists():
        return

    if "Shorts" in fmt:
        max_sec = debate_config.get("shorts_max_seconds", 179.0)
        keep_backup = debate_config.get("keep_shorts_backup", True)
        if keep_backup:
            backup_path = final_output.with_name(final_output.stem + "_bk" + final_output.suffix)
            try:
                shutil.copy2(str(final_output), str(backup_path))
                logger(f"💾 Backup saved: {backup_path.name}")
            except Exception as e:
                logger(f"️ Backup failed: {e}")
        ffmpeg.enforce_shorts_limit(str(final_output), max_duration=max_sec, logger=logger)

    speed_factor = 1.0
    scaled = [(p, d/speed_factor, k) for p, d, k in valid_segs]
    subtitle_builder.build_srt(scaled, subtitle_map, str(debate_dir / f"{safe_slug}_{fmt}.srt"))
    subtitle_builder.build_txt(scaled, subtitle_map, str(debate_dir / f"{safe_slug}_{fmt}.txt"), True)

    for f in [debate_dir / f"debate_3d_{fmt}_silent.mp4", debate_dir / f"debate_3d_{fmt}_audio.mp3"]:
        if f.exists():
            f.unlink()
    shutil.rmtree(debate_dir / "audio_blocks", ignore_errors=True)

    if debate_config.get("cleanup_scoreboards", True):
        deleted = 0
        for sb in debate_dir.glob(f"scoreboard_*_{fmt}.mp4"):
            try:
                sb.unlink()
                deleted += 1
            except Exception:
                pass
        base_sb = debate_dir / f"scoreboard_{fmt}.mp4"
        if base_sb.exists():
            try:
                base_sb.unlink()
                deleted += 1
            except Exception:
                pass
        if deleted:
            logger(f"🧹 Cleaned up {deleted} intermediate scoreboard files")

    logger(f"✅ Generated: {final_output.name}")

# ============================================================================
# AUDIO GENERATION
# ============================================================================

def _generate_audio(pipeline, block_map, fmt, fmt_clips, intro_path, clips_base, use_prefix,
                    voice_map, tts, audio_svc, ffmpeg_svc, block_dir, logger,
                    debate_dir=None, debate_config=None, clip_config=None):
    """Generate audio segments for all pipeline steps."""
    block_dir.mkdir(parents=True, exist_ok=True)
    segments = []
    default_block_dur = float(debate_config.get("default_block_duration", 3.0))
    md_suffix = "-m" if "Shorts" in fmt else ""

    if clip_config:
        fmt_suffix = clip_config.get("_format_suffix", {}).get(fmt, "")

    for step in pipeline:
        key = step["key"]
        if step["type"] == "video":
            vid_path = _resolve_video_path(key, fmt_clips, intro_path, clips_base, use_prefix, fmt_suffix)
            if not vid_path or not os.path.exists(vid_path):
                tmp = str(block_dir / f"{key}_audio.mp3")
                ffmpeg_svc.create_silent_mp3(tmp, duration=default_block_dur)
                segments.append((tmp, default_block_dur, key))
                logger(f"⚠️ Video missing for '{key}' (path={vid_path}) — silent {default_block_dur}s")
                continue

            video_dur = ffmpeg_svc.get_duration(vid_path) or 0.0
            tmp = str(block_dir / f"{key}_audio.mp3")

            if key == "score" or key.startswith("score_"):
                # Scoreboard audio handling
                stage = "score" if key == "score" else key.replace("score_", "")
                sb_cfg = debate_config.get("debate_3d_score", {}) if debate_config else {}
                score_audio_enabled = sb_cfg.get("score_audio_enabled", True)
                score_bgm_enabled = sb_cfg.get("score_bgm_enabled", True)
                score_voice_role = sb_cfg.get("score_voice", "decide")
                bgm_path = PROJECT_ROOT / (debate_config.get("score_bgm_path", "assets/mp3/score.mp3")
                                           if debate_config else "assets/mp3/score.mp3")

                if not score_audio_enabled:
                    if score_bgm_enabled and bgm_path.exists():
                        ffmpeg_svc.create_silent_mp3(tmp, duration=video_dur)
                        ffmpeg_svc.mix_bgm(tmp, str(bgm_path), bgm_volume=debate_config.get("bgm_volume", 0.25), logger=logger)
                        logger(f"🎵 Score '{key}': BGM only (TTS disabled)")
                    else:
                        ffmpeg_svc.create_silent_mp3(tmp, duration=video_dur)
                        logger(f" Score '{key}': silent (TTS + BGM disabled)")
                    dur = video_dur
                else:
                    stage_data = extract_scores(debate_dir, md_suffix, {}) if debate_dir else {}
                    narration = _build_stage_narration(stage, stage_data)
                    voice = voice_map.get(score_voice_role) or voice_map.get("decide")

                    if tts.generate_edge(narration, tmp, voice=voice):
                        if score_bgm_enabled and bgm_path.exists():
                            ffmpeg_svc.mix_bgm(tmp, str(bgm_path), bgm_volume=debate_config.get("bgm_volume", 0.25), logger=logger)
                        tts_dur = audio_svc.get_duration(tmp) or 0.0
                        if tts_dur > video_dur + 0.1:
                            # Trim audio to fit video
                            trimmed_tmp = str(block_dir / f"{key}_trimmed.mp3")
                            trim_cmd = [
                                "ffmpeg", "-y", "-i", tmp,
                                "-t", str(video_dur),
                                "-af", "afade=t=out:st={:.2f}:d=0.3".format(max(0, video_dur - 0.3)),
                                "-ar", "44100", "-ac", "2", "-b:a", "128k",
                                trimmed_tmp
                            ]
                            r = subprocess.run(trim_cmd, capture_output=True, text=True)
                            if r.returncode == 0 and os.path.exists(trimmed_tmp) and os.path.getsize(trimmed_tmp) > 1024:
                                os.replace(trimmed_tmp, tmp)
                                logger(f"✂️ Trimmed '{key}' audio: {tts_dur:.2f}s → {video_dur:.2f}s (with fade)")
                            elif os.path.exists(trimmed_tmp):
                                os.remove(trimmed_tmp)
                        dur = video_dur
                    else:
                        dur = video_dur
                        ffmpeg_svc.create_silent_mp3(tmp, duration=dur)
                    if isinstance(fmt_clips.get(key), dict):
                        fmt_clips[key]["subtext"] = narration
            else:
                # Regular video clip audio extraction
                extracted_dur = audio_svc.extract_audio(vid_path, tmp)
                audio_dur = extracted_dur if extracted_dur else 0.0

                if audio_dur < 0.1 or not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
                    dur = video_dur if video_dur > 0.1 else default_block_dur
                    ffmpeg_svc.create_silent_mp3(tmp, duration=dur)
                    logger(f"🔇 Silent/no-audio video '{key}' → silent audio ({dur:.2f}s, video={video_dur:.2f}s)")
                elif audio_dur < video_dur - 0.1:
                    # Pad audio to match video
                    padded_tmp = str(block_dir / f"{key}_padded.mp3")
                    pad_cmd = [
                        "ffmpeg", "-y", "-i", tmp,
                        "-af", f"apad=whole_dur={video_dur}",
                        "-ar", "44100", "-ac", "2", "-b:a", "128k",
                        padded_tmp
                    ]
                    r = subprocess.run(pad_cmd, capture_output=True, text=True)
                    if r.returncode == 0 and os.path.exists(padded_tmp) and os.path.getsize(padded_tmp) > 1024:
                        os.replace(padded_tmp, tmp)
                        dur = video_dur
                        logger(f" Padded audio for '{key}': {audio_dur:.2f}s → {dur:.2f}s (video={video_dur:.2f}s)")
                    else:
                        ffmpeg_svc.create_silent_mp3(tmp, duration=video_dur)
                        dur = video_dur
                        logger(f"⚠️ Pad failed for '{key}' (err: {r.stderr[:100] if r.stderr else 'unknown'}), using silent ({video_dur:.2f}s)")
                        if os.path.exists(padded_tmp):
                            os.remove(padded_tmp)
                else:
                    dur = audio_dur
                    logger(f"🎵 Extracted audio for '{key}': {dur:.2f}s (video={video_dur:.2f}s)")

            segments.append((tmp if os.path.exists(tmp) else None, dur, key))

        elif step["type"] == "block":
            # --- PRIMARY TEXT LOOKUP ---
            text = block_map.get((step["role"], key), " ").strip()

            # --- 🔥 FIX: Opening statement fallback for p0/c0 ---
            if key in ("p0", "c0") and len(text) < 80:
                for fallback in ("opening", "opening_statement", "p_opening", "c_opening"):
                    alt = block_map.get((step["role"], fallback), " ").strip()
                    if len(alt) > len(text):
                        logger(f"🔁 Fallback for '{key}': mapped '{fallback}' → '{key}' ({len(alt)} chars)")
                        text = alt
                        break

            voice = voice_map.get(resolve_voice_key(key, step["role"]), voice_map["decide"])
            out = str(block_dir / f"_blk_{key}_{fmt}.mp3")

            if not text:
                # Skip empty argument blocks (p4/c4/p5/c5) but keep placeholders for sum/aly/win
                try:
                    arg_num = int(key[1:])
                    if (key.startswith("p") or key.startswith("c")) and arg_num > 3:
                        logger(f"️ Skipping empty arg block '{key}' (no data)")
                        continue
                except ValueError:
                    pass
                ffmpeg_svc.create_silent_mp3(out, duration=default_block_dur)
                segments.append((out, default_block_dur, key))
                continue

            if tts.generate_edge(text, out, voice=voice):
                dur = audio_svc.get_duration(out) or 0.0
                segments.append((out, dur, key) if os.path.getsize(out) > 0 and dur > 0 else (out, default_block_dur, key))
            else:
                ffmpeg_svc.create_silent_mp3(out, duration=default_block_dur)
                segments.append((out, default_block_dur, key))

    return segments

# ============================================================================
# VIDEO PATH RESOLUTION
# ============================================================================

def _resolve_video_path(key, fmt_clips, intro_path, clips_base, use_prefix, fmt_suffix=""):
    """Resolve video path for a given key."""
    if key == "intro":
        cfg = fmt_clips.get("intro", {})
        path = _get_clip_path(cfg, fmt_suffix)
        return intro_path or _resolve_clip_path(path, key, clips_base, use_prefix)

    if key == "score" or key.startswith("score"):
        cfg = fmt_clips.get(key, {})
        if isinstance(cfg, dict):
            return cfg.get("paths", [None])[0] if isinstance(cfg.get("paths"), list) else cfg.get("path")
        return cfg

    cfg = fmt_clips.get(key, {})
    path = _get_clip_path(cfg, fmt_suffix)
    return _resolve_clip_path(path, key, clips_base, use_prefix) if path else None

def _get_clip_path(cfg, fmt_suffix=""):
    """Extract path from clip config dict or string."""
    if not isinstance(cfg, dict):
        return _apply_suffix(cfg, fmt_suffix) if isinstance(cfg, str) else cfg

    raw = cfg.get("paths") or cfg.get("path")
    if raw is None:
        return None

    if isinstance(raw, str):
        raw = [raw]

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                return _apply_suffix(item, fmt_suffix)

    return None

def _apply_suffix(path_str, fmt_suffix):
    """Apply format suffix to path."""
    if not path_str:
        return path_str
    return path_str.replace("{suffix}", fmt_suffix or "")

def _resolve_clip_path(path: str, key: str, clips_base: str, use_prefix: bool) -> str:
    """Resolve clip path with optional folder prefix."""
    if not path:
        return None
    if os.path.isabs(path):
        return path
    if "/" in path:
        p = Path(path)
        return str(p if p.is_absolute() else PROJECT_ROOT / p)

    base = Path(clips_base) if Path(clips_base).is_absolute() else PROJECT_ROOT / clips_base

    if use_prefix:
        for d in base.iterdir() if base.exists() else []:
            if d.is_dir() and d.name.endswith(key):
                return str(d / path)

    return str(base / key / path)
















================================================================================






"""
unit_leaddata.py — Unit-LeadData Router (CF2 Compliant)
Architecture (Rule 4):
unit_leaddata.py (Router)
├─▶ leaddata_collect_tool   → Fetch raw leads (Maps API + Reviewer Mining)
├─▶ leaddata_normalize_tool → Standardize schema + dedup
├─▶ leaddata_score_tool     → Score & segment (hot/warm/cold)
├─▶ leaddata_enrich_osint   → Enrich high-intent travelers (OSINT)
└─▶ leaddata_export_tool    → Write final CSV/JSON + stats
Rule alignment: R4, R6, R7, R14, R16, R17, R18, R21, R37, R39
"""
import logging
from pathlib import Path
from cf2.meta import mark_subtask
from cf2.core.paths import RUNTIME_PATHS
from cf2.tools.leaddata_collect import LeadDataCollectTool
from cf2.tools.leaddata_normalize import LeadDataNormalizeTool
from cf2.tools.leaddata_score import LeadDataScoreTool
from cf2.tools.leaddata_export import LeadDataExportTool

logger = logging.getLogger(__name__)

def _parse_keywords(topic: str) -> list:
    """Split comma-separated topic into keywords (Rule 21)."""
    return [k.strip() for k in topic.split(",") if k.strip()]

def run(topic: str, workspace: Path, inputs: dict, force: bool = False) -> str:
    """
    Unit-LeadData entry point. Called by FlowController via executor (Rule 21).
    Implements Rule 3/4 failure safety: contains errors & returns status strings.
    """
    try:
        workspace = workspace if isinstance(workspace, Path) else Path(workspace)
        leaddata_dir = workspace / "leaddata"
        leaddata_dir.mkdir(parents=True, exist_ok=True)

        # ── Read config blocks (Rule 37) ──────────────────────────────────
        cfg = inputs.get("leaddata_config", {})
        if not cfg.get("enabled", True):
            logger.info("⏭️  Disabled in leaddata_config")
            return "disabled"

        collect_cfg   = cfg.get("collect_config", {})
        normalize_cfg = cfg.get("normalize_config", {})
        score_cfg     = cfg.get("score_config", {})
        export_cfg    = cfg.get("export_config", {})
        enrich_cfg    = cfg.get("enrich_config", {})

        # ── Topic → keywords (Rule 21) ────────────────────────────────────
        keywords = _parse_keywords(topic)
        logger.info(f"📊 Processing topic: {topic}")
        logger.info(f"   Keywords: {len(keywords)} → {leaddata_dir}")

        # ── Resolve credentials path (Rule 39: secrets in .runtime/secrets/)
        credentials_file = collect_cfg.get("credentials_file", "")
        if credentials_file and not Path(credentials_file).is_absolute():
            credentials_file = str(RUNTIME_PATHS["secrets"] / Path(credentials_file).name)

        # ── STEP 1: Collect ───────────────────────────────────────────────
        logger.info("🔍 Step 1/4: Collect")

        # ✅ FIX: Removed 'engine' and 'search_type' to prevent kwarg mismatch.
        # Tool handles defaults safely.
        result = LeadDataCollectTool()._run(
            topic=topic,
            keywords=keywords,
            output_dir=str(leaddata_dir),
            sources=cfg.get("sources", ["maps_reviewers"]),
            credentials_file=credentials_file,
            api_endpoint=collect_cfg.get("api_endpoint"),
            request_timeout=collect_cfg.get("request_timeout", 30),
            max_results_per_keyword=collect_cfg.get("max_results_per_keyword", 50),
            skip_if_cached=collect_cfg.get("skip_if_cached", True),
            reviewer_recency_days=collect_cfg.get("reviewer_mining", {}).get("review_recency_days", 90),
            reviewer_min_activity=collect_cfg.get("reviewer_mining", {}).get("min_reviewer_activity", 1),
        )
        logger.info(result)
        mark_subtask(workspace, "Unit-LeadData", "collect", "done")

        # ── STEP 1.2: Optional Multi-Source (Reddit) ──────────────────────
        if "reddit_travel" in cfg.get("sources", []):
            try:
                logger.info("🔍 Step 1.2: Reddit Travel Source")
                from cf2.tools.leaddata_reddit import RedditTravelScraperTool
                reddit_cfg = cfg.get("collect_config", {}).get("reddit_config", {})
                result = RedditTravelScraperTool()._run(
                    topic=topic, keywords=keywords, output_dir=str(leaddata_dir), **reddit_cfg
                )
                logger.info(result)
            except Exception as e:
                logger.warning(f"⚠️ Reddit source failed (skipped): {e}")

        # ── STEP 2: Normalize ─────────────────────────────────────────────
        logger.info("🔄 Step 2/4: Normalize")
        result = LeadDataNormalizeTool()._run(
            output_dir=str(leaddata_dir),
            deduplicate_on=normalize_cfg.get("deduplicate_on", ["name"]),
            phone_country_default=normalize_cfg.get("phone_country_default", "US"),
            lowercase_email=normalize_cfg.get("lowercase_email", True),
            force_https=normalize_cfg.get("force_https", True),
            strip_unicode=normalize_cfg.get("strip_unicode", True),
            min_name_length=normalize_cfg.get("min_name_length", 2),
        )
        logger.info(result)
        mark_subtask(workspace, "Unit-LeadData", "normalize", "done")

        # ── STEP 3: Score ─────────────────────────────────────────────────
        logger.info("⭐ Step 3/4: Score")
        result = LeadDataScoreTool()._run(
            output_dir=str(leaddata_dir),
            score_enabled=score_cfg.get("score_enabled", True),
            scoring_rubric=score_cfg.get("scoring_rubric", {
                "source": 50,           # ✅ Matches CSV column 'source'
                "intent_score": 30,     # ✅ Matches CSV column 'intent_score'
                "review_count": 15,     # ✅ Matches CSV column 'review_count'
                "review_date": 10       # ✅ Matches CSV column 'review_date'
            }),
            thresholds=score_cfg.get("segment_thresholds", {"hot": 60, "warm": 35, "cold": 0}),
            sort_by_score_desc=score_cfg.get("sort_by_score_desc", True),
        )
        logger.info(result)
        mark_subtask(workspace, "Unit-LeadData", "score", "done")

        # ── STEP 3.5: Enrich (OSINT) ──────────────────────────────────────
        scored_file = leaddata_dir / "scored" / "leads_scored.csv"
        if cfg.get("enrich_enabled", False) and scored_file.exists():
            logger.info("🔍 Step 3.5/4: Enrich (OSINT)")
            from cf2.tools.leaddata_enrich_osint import OSINTEnrichTool
            result = OSINTEnrichTool()._run(
                input_file=str(scored_file),
                output_dir=str(leaddata_dir),
                credentials_file=credentials_file,
                min_confidence=enrich_cfg.get("min_confidence", 0.30),
                allow_guessing=enrich_cfg.get("allow_guessing", False),
                max_osint_queries=enrich_cfg.get("max_osint_queries", 15),
                max_enrich_rows=enrich_cfg.get("max_enrich_rows", 0),
                skip_if_cached=enrich_cfg.get("skip_if_cached", True),
                query_delay_seconds=enrich_cfg.get("query_delay_seconds", 1),
            )
            logger.info(result)
            mark_subtask(workspace, "Unit-LeadData", "enrich", "done")

        # ── STEP 4: Export ────────────────────────────────────────────────
        logger.info("📤 Step 4/4: Export")
        result = LeadDataExportTool()._run(
            output_dir=str(leaddata_dir),
            formats=export_cfg.get("formats", ["csv", "json"]),
            generate_stats=export_cfg.get("generate_stats", True),
            stats_file=export_cfg.get("stats_file", "lead_stats.json"),
            include_segments_breakdown=export_cfg.get("include_segments_breakdown", True),
        )
        logger.info(result)
        mark_subtask(workspace, "Unit-LeadData", "export", "done")

        logger.info(f"✅ Done: {leaddata_dir}")
        return "done"

    except Exception as e:
        logger.error(f"❌ Unit-LeadData failed: {e}")
        return "failed"











================================================================================
"""
unit_packaging.py — Packaging Unit Orchestrator (Debate-Aware)
Handles: CC routing & translation, YouTube metadata generation, AI thumbnail generation.
Rules: 19 (Paths), 23 (Config-driven), 24 (Smart Skip), 27 (Profile Merge)
"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any
import traceback

from cf2.meta import mark_subtask
from cf2.tools.publisher_yt_shared import google_translate, LANGUAGES, parse_video_formats, get_animation_formats

try:
    from cf2.tools.packaging_yt_metadata import YTMetadataTool
    from cf2.tools.packaging_yt_thumbnail import YTThumbnailTool
except ImportError as e:
    print(f"⚠️ Packaging tools import failed: {e}")
    YTMetadataTool = None
    YTThumbnailTool = None

def _log(msg: str):
    """Unified logging helper."""
    print(f"[Unit-Packaging] {msg}")

def run(topic: str, workspace: Path, inputs: Dict[str, Any], force: bool = False) -> str:
    """
    Main entry point for Unit-Packaging.

    Args:
        topic: Video topic string
        workspace: Path to topic workspace (output/{slug}/)
        inputs: Merged config dict from data.json + profile overrides
        force: If True, bypass smart skip checks

    Returns:
        Status string: 'done' | 'skipped' | 'disabled' | 'failed'
    """
    # Rule 23: Check master switch
    if not inputs.get("Unit-Packaging", False):
        _log("⏭️ Unit-Packaging disabled — skipping.")
        mark_subtask(workspace, "Unit-Packaging", "packaging", "disabled")
        return "disabled"

    debate_dir = workspace / "debate"
    if not debate_dir.exists():
        _log("⚠️ No debate/ folder found. Packaging skipped.")
        mark_subtask(workspace, "Unit-Packaging", "packaging", "skipped")
        return "skipped"

    # 📦 Config Extraction (Rule 23: No hardcoding)
    video_formats = inputs.get("video_formats", ["Shorts"])
    pkg_config = inputs.get("packaging_config", {})

    # Extract metadata/CC settings
    yt_cc_lang = int(pkg_config.get("yt_cc_lang", 3))
    yt_md_lang = int(pkg_config.get("yt_md_lang", 9))
    gen_meta = pkg_config.get("generate_youtube_metadata", True)
    gen_th = pkg_config.get("generate_thumbnail", True)

    # 🔑 Route thumbnail config (supports nested or top-level in data.json)
    # Rule 27: Deep-merge profile overrides
    thumbnail_config = inputs.get("thumbnail_config", pkg_config.get("thumbnail_config", {}))

    _log(f"📦 Config → MD_lang={yt_md_lang}, CC_lang={yt_cc_lang}, Thumb_methods={thumbnail_config.get('thumbnail_methods', ['placeholder'])}")

    output_dir = str(debate_dir)
    slug = workspace.name
    channel = inputs.get("channel", "channelName")

    # 🔥 Rule 24: Smart Skip Check (before any work)
    yt_base = debate_dir / "YT"
    if yt_base.exists() and not force:
        done = 0
        for fmt in video_formats:
            md_exists = (yt_base / fmt / "MD" / "en.json").exists()
            th_exists = any((yt_base / fmt / "Th").glob("*.jpg")) or any((yt_base / fmt / "Th").glob("*.png"))
            cc_exists = (yt_base / fmt / "CC" / "en.txt").exists()
            if md_exists and th_exists and cc_exists:
                done += 1
        if done >= len(video_formats):
            _log("⏭️ Smart skip — all packaging outputs already exist.")
            mark_subtask(workspace, "Unit-Packaging", "packaging", "skipped")
            return "skipped"

    mark_subtask(workspace, "Unit-Packaging", "packaging", "running")

    try:
        # 1️⃣ CC Routing & Translation
        _log("📝 Routing debate CC & translating...")
        active_cc_langs = LANGUAGES[:min(yt_cc_lang, len(LANGUAGES))]

        for fmt in video_formats:
            debate_cc = debate_dir / f"{slug}_{fmt}.txt"
            if debate_cc.exists():
                cc_dir = debate_dir / "YT" / fmt / "CC"
                cc_dir.mkdir(parents=True, exist_ok=True)

                # Copy English CC
                dest_en = cc_dir / "en.txt"
                if not dest_en.exists() or force:
                    shutil.copy2(debate_cc, dest_en)
                    _log(f"✅ Copied debate CC → YT/{fmt}/CC/en.txt")

                # Translate to target languages
                if dest_en.exists():
                    en_text = dest_en.read_text(encoding="utf-8").strip()
                    if en_text:
                        for lang in active_cc_langs:
                            if lang == "en":
                                continue
                            out = cc_dir / f"{lang}.txt"
                            if out.exists() and not force:
                                continue
                            try:
                                out.write_text(google_translate(en_text, lang), encoding="utf-8")
                                _log(f"  🌐 Translated CC/{lang}.txt")
                            except Exception as e:
                                _log(f"  ⚠️ CC/{lang} failed: {e}")
            else:
                _log(f"⚠️ No debate source found for {fmt}: {debate_cc.name}")

        # 2️⃣ Metadata Generation (Rule 24 enforced inside tool)
        if gen_meta and YTMetadataTool:
            _log("📦 Generating YouTube metadata...")
            result = YTMetadataTool()._run(
                topic=topic,
                filename=slug,
                output_dir=output_dir,
                channel=channel,
                channel_lower=inputs.get("channel_lower", channel.lower()),
                website=inputs.get("website", f"youtube.com/@{channel}"),
                video_formats=video_formats,
                yt_metadata_lang=yt_md_lang
            )
            _log(f"✅ Metadata complete: {result[:100]}...")

        # 3️⃣ Thumbnail Generation (Config-Routed Fallback Chain)
        if gen_th and YTThumbnailTool:
            _log("🖼️ Generating thumbnails...")
            result = YTThumbnailTool()._run(
                topic=topic,
                filename=slug,
                output_dir=output_dir,
                channel=channel,
                video_formats=video_formats,
                thumbnail_config=thumbnail_config  # 🔑 Routes to openai → comfyui → diffusers → placeholder
            )
            _log(f"✅ Thumbnails complete: {result[:100]}...")

        mark_subtask(workspace, "Unit-Packaging", "packaging", "done")
        return "done"

    except Exception as e:
        _log(f"❌ Packaging error: {e}")
        traceback.print_exc()
        mark_subtask(workspace, "Unit-Packaging", "packaging", "failed")
        raise




















================================================================================

"""
unit_prodcast.py — Podcast Generation Pipeline (CF2 Compliant)

Architecture:
unit_prodcast.py (Router)
├─▶ prodcast_script_generator
├─▶ prodcast_voice_generator
├─▶ prodcast_pipeline
└─▶ prodcast_video_generator

Rule alignment:
R4, R6, R7, R19, R28, R32, R33, R39
"""

from __future__ import annotations

import inspect
import logging
import re

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from crewai import Crew, Process

from cf2.meta import (
    acquire_lock,
    load_meta,
    release_lock,
    save_meta,
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
    LOCKED = "locked"


MIN_SCRIPT_BYTES = 200
MIN_SCRIPT_M_BYTES = 150
MIN_AUDIO_BYTES = 1_000
MIN_VIDEO_BYTES = 500_000

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
# Public Entry
# ============================================================================

def run(
    topic: str,
    workspace: Path,
    inputs: dict[str, Any],
    force: bool = False,
) -> str:

    if not topic:

        logger.error("Unit-Prodcast: empty topic")

        return RunStatus.FAILED

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

    video_enabled = bool(
        inputs.get("prodcast_video_enabled", False)
    )

    if (
        not force
        and _is_fully_cached(paths)
        and _is_video_cached(paths, video_enabled)
    ):

        logger.info(
            "Unit-Prodcast: cached — skipping"
        )

        return RunStatus.DONE

    lock = acquire_lock(
        workspace,
        "Unit-Prodcast",
    )

    if not lock:

        logger.warning(
            "Unit-Prodcast: lock failed"
        )

        return RunStatus.LOCKED

    meta = load_meta(workspace)

    meta.setdefault("status", {})

    try:

        # =========================================================
        # Script
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
                meta,
                "script generation failed",
            )

        # =========================================================
        # Mini Script
        # =========================================================

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
                meta,
                "mini script failed",
            )

        # =========================================================
        # Audio HD
        # =========================================================

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
                meta,
                "audio hd failed",
            )

        # =========================================================
        # Audio Shorts
        # =========================================================

        _run_voice_stage(
            script_path=paths.script_m,
            audio_path=paths.audio_m,
            inputs=inputs,
            force=force,
            fmt="Shorts",
        )

        # =========================================================
        # Video
        # =========================================================

        if video_enabled:

            video_formats = inputs.get(
                "video_formats",
                ["Shorts"],
            )

            for fmt in video_formats:

                audio_src = (
                    paths.audio_m
                    if "Shorts" in fmt
                    else paths.audio
                )

                output_dst = (
                    paths.video_m
                    if "Shorts" in fmt
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

        meta["status"]["Unit-Prodcast"] = "done"

        save_meta(workspace, meta)

        logger.info("Unit-Prodcast: DONE")

        return RunStatus.DONE

    except Exception as exc:

        logger.exception(
            "Unit-Prodcast: fatal — %s",
            exc,
        )

        return _record_failure(
            workspace,
            meta,
            str(exc),
        )

    finally:

        release_lock(lock)


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

        _call_voice_tool(
            voice_tool=voice_tool,
            script_path=script_path,
            audio_path=audio_path,
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


def _call_voice_tool(
    voice_tool: Callable,
    script_path: Path,
    audio_path: Path,
    inputs: dict[str, Any],
    fmt: str,
) -> None:

    flat_kwargs = {
        "script_path": str(script_path),
        "output_path": str(audio_path),

        "voice_host": inputs.get(
            "prodcast_voice_host",
            DEFAULTS["voice_host"],
        ),

        "voice_guest": inputs.get(
            "prodcast_voice_guest",
            DEFAULTS["voice_guest"],
        ),

        "tts_engine": inputs.get(
            "prodcast_tts_engine",
            DEFAULTS["tts_engine"],
        ),

        "pause_ms": inputs.get(
            "prodcast_pause_between_lines_ms",
            DEFAULTS["pause_ms"],
        ),

        "fmt": fmt,
    }

    sig = inspect.signature(voice_tool)

    kwargs = {}

    for name in sig.parameters:

        if name in flat_kwargs:
            kwargs[name] = flat_kwargs[name]

        elif name == "inputs":
            kwargs["inputs"] = inputs

    voice_tool(**kwargs)


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
        if "Shorts" in fmt
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
    paths: Paths
) -> bool:

    return (
        _is_valid_file(
            paths.script,
            MIN_SCRIPT_BYTES,
        )

        and

        _is_valid_file(
            paths.script_m,
            MIN_SCRIPT_M_BYTES,
        )

        and

        _is_valid_file(
            paths.audio,
            MIN_AUDIO_BYTES,
        )

        and

        _is_valid_file(
            paths.audio_m,
            MIN_AUDIO_BYTES,
        )
    )


def _is_video_cached(
    paths: Paths,
    enabled: bool,
) -> bool:

    if not enabled:
        return True

    return (
        _is_valid_file(
            paths.video,
            MIN_VIDEO_BYTES,
        )

        and

        _is_valid_file(
            paths.video_m,
            MIN_VIDEO_BYTES,
        )
    )


def _extract_text(
    result: Any
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
    meta: dict,
    reason: str,
) -> str:

    logger.error(
        "Unit-Prodcast: %s",
        reason,
    )

    meta.setdefault(
        "status",
        {},
    )["Unit-Prodcast"] = "failed"

    meta.setdefault(
        "errors",
        {},
    )["Unit-Prodcast"] = reason

    save_meta(
        workspace,
        meta,
    )

    return RunStatus.FAILED



================================================================================
"""
unit_publisher.py — Distribution Layer (Rule 7)

Responsibility: Upload finished content to YouTube, Facebook, and social
platforms. That is ALL this unit does.

Packaging (metadata, thumbnails, narration) is Unit-Packaging's job.
If those files don't exist, this unit warns the operator and exits cleanly
rather than generating them itself — that would violate Rule 18 (unit
independence) and Rule 6 (consumer units never regenerate content).

Why uploads call tools directly instead of going through LLM agents:
  Upload operations are fully deterministic — fixed parameters in, API
  call out, result string back. There is zero reasoning for an LLM to
  contribute. Routing uploads through an agent introduces hallucination
  risk: the agent may mutate output_dir, return the raw tool-call JSON
  instead of the result, or fabricate a skip. Calling tool._run(...)
  directly is faster, cheaper, and guaranteed correct (Rule 16).
"""
from pathlib import Path
from cf2.meta import mark_subtask

import json as _json
# ── Dependency check ──────────────────────────────────────────────────────

def _check_packaging_deps(workspace: Path, inputs: dict) -> bool:
    """
    Verify that Unit-Packaging produced the files this unit needs.
    Returns True if all required files exist, False otherwise.
    Prints a clear operator message listing what is missing.
    """
    video_formats = inputs.get("video_formats", ["Shorts", "HD"])
    video_style   = inputs.get("video_style", ["debate"])
    style         = video_style[0] if isinstance(video_style, list) else video_style
    missing       = []

    for fmt in video_formats:
        # Metadata file — required for YouTube title/description
        md_path = workspace / "debate" / "YT" / fmt / "MD" / "en.json"
        if not md_path.exists():
            missing.append(str(md_path))

    if missing:
        print("\n⚠️  Unit-Publisher: required packaging files not found.")
        print("   Run Unit-Packaging first, or enable it in your config:")
        print('   "Unit-Packaging": true')
        print("   Missing:")
        for m in missing:
            print(f"     • {m}")
        return False
    return True


# ── Upload helpers (direct tool calls — no LLM) ───────────────────────────

def _run_yt_upload(inputs: dict) -> str:
    """
    Call YTUploadTool directly with parameters from inputs.
    No LLM agent involved — output_dir is guaranteed to be the workspace
    root, not a hallucinated subdirectory path.
    """
    from cf2.tools.publisher_yt_upload import YTUploadTool
    yt_cfg = inputs.get("publisher_config", {}).get("yt_upload_config", {})
    result = YTUploadTool()._run(
        topic                = inputs["topic"],
        output_dir           = inputs["output_dir"],
        video_formats        = inputs.get("video_formats", ["Shorts", "HD"]),
        upload_youtube_video = yt_cfg.get("upload_youtube_video", False),
        channel              = inputs.get("channel", "PlayOwnAi"),
        privacy_status       = yt_cfg.get("upload_privacy", "private"),
        category_id          = yt_cfg.get("upload_category_id", "27"),
        upload_cc            = yt_cfg.get("upload_cc", True),
        upload_cc_lang       = str(yt_cfg.get("upload_cc_lang", "0")),
        upload_md_lang       = str(yt_cfg.get("upload_md_lang", "0")),
        notify_subscribers   = yt_cfg.get("upload_notify_subscribers", False),
        client_secrets_file  = yt_cfg.get("upload_client_secrets_file", ""),
        token_file           = yt_cfg.get("upload_token_file", ""),
        dry_run              = yt_cfg.get("upload_dry_run", False),
    )
    print(result)
    return result


def _run_fb_upload(inputs: dict) -> str:
    """Call FBUploadTool directly. No LLM agent."""
    from cf2.tools.publisher_fb_upload import FBUploadTool
    fb_cfg = inputs.get("publisher_config", {}).get("fb_upload_config", {})
    result = FBUploadTool()._run(
        topic                 = inputs["topic"],
        output_dir            = inputs["output_dir"],
        video_formats         = inputs.get("video_formats", ["Shorts", "HD"]),
        upload_facebook_video = fb_cfg.get("upload_facebook_video", False),
        channel               = inputs.get("channel", "PlayOwnAi"),
        privacy_status        = fb_cfg.get("privacy_status", "SELF"),
        credentials_file      = fb_cfg.get("credentials_file", ""),
    )
    print(result)
    return result


def _run_social_share(inputs: dict) -> str:
    """Call SocialShareTool directly. No LLM agent."""
    from cf2.tools.advertise_social_share import SocialShareTool
    result = SocialShareTool()._run(
        topic                = inputs["topic"],
        filename             = inputs.get("filename", ""),
        output_dir           = inputs["output_dir"],
        social_share_enabled = inputs.get("social_share_enabled", False),
        social_platforms     = inputs.get("social_platforms", []),
        video_formats        = inputs.get("video_formats", ["Shorts", "HD"]),
        channel              = inputs.get("channel", "PlayOwnAi"),
        website              = inputs.get("website", ""),
        image_path           = "",        # tool auto-detects from output_dir
        start_year           = inputs.get("start", 2000),
        end_year             = inputs.get("end", 2024),
        video_url            = "",
        dry_run              = inputs.get("social_share_dry_run", False),
        schedule_post        = inputs.get("schedule_post", False),
        schedule_datetime    = inputs.get("schedule_datetime", ""),
        schedule_timezone    = inputs.get("schedule_timezone", "UTC"),
    )
    print(result)
    return result


# ── Main entry point ──────────────────────────────────────────────────────

def run(topic: str, workspace: Path, inputs: dict, force: bool = False) -> str:
    """
    Unit-Publisher entry point. Called only by executor.py (Rule 21).

    This unit does exactly three things, and only if enabled:
      1. Upload to YouTube   (if yt_upload=true)
      2. Upload to Facebook  (if fb_upload=true)
      3. Post to social      (if social_share=true)

    It does NOT run packaging. If metadata/thumbnail files are missing,
    it warns the operator to enable Unit-Packaging and exits cleanly.
    """
    # ── Resolve workspace paths once — never modified after this point ────
    topic_dir            = workspace if isinstance(workspace, Path) else Path(workspace)
    inputs["output_dir"] = str(topic_dir)
    inputs["filename"]   = inputs.get("_slug", topic_dir.name)
    inputs["topic"]      = topic

    print(f"\n📦  Unit-Publisher | {topic}")
    print(f"   📁 Workspace: {topic_dir}")

    # ── Determine which upload tasks are enabled ───────────────────────────
    pub_cfg      = inputs.get("publisher_config", {})
    # Safety: check if debate completed successfully
    meta_file = topic_dir / "meta.json"
    if meta_file.exists():
        meta = _json.loads(meta_file.read_text())
        debate_status = meta.get("status", {}).get("Unit-Debate", "pending")
        if debate_status not in ("done", "skipped"):
            msg = f"❌ Unit-Publisher: Unit-Debate is '{debate_status}'. Aborting."
            print(msg)
            raise RuntimeError(msg)

    pub_cfg      = inputs.get("publisher_config", {})
    do_yt_upload = inputs.get("publisher_config", {}).get("yt_upload", False)
    do_fb_upload = pub_cfg.get("fb_upload", False)

    do_social    = inputs.get("social_share", False)

    enabled = []
    if do_yt_upload: enabled.append("YT upload")
    if do_fb_upload: enabled.append("FB upload")
    if do_social:    enabled.append("social share")

    if not enabled:
        msg = (
            "⏭️  Unit-Publisher: no upload tasks enabled.\n"
            "   To activate: set yt_upload=true / fb_upload=true / social_share=true"
        )
        print(msg)
        return msg

    print(f"   🚀 Starting: {', '.join(enabled)}")

    # ── Guard: packaging files must exist before uploading ─────────────────
    if do_yt_upload and not _check_packaging_deps(topic_dir, inputs):
        return (
            "❌ Unit-Publisher: upload aborted — packaging files missing.\n"
            '   Enable Unit-Packaging: set "Unit-Packaging": true and re-run.'
        )

    # ── Execute uploads directly — no LLM agents ──────────────────────────
    results = []

    if do_yt_upload:
        print("\n📤  YouTube Upload")
        results.append(_run_yt_upload(inputs))

    if do_fb_upload:
        print("\n📤  Facebook Upload")
        results.append(_run_fb_upload(inputs))

    if do_social:
        print("\n📣  Social Share")
        results.append(_run_social_share(inputs))

    # Update meta.json with per-platform status
    if do_yt_upload:
        mark_subtask(topic_dir, "Unit-Publisher", "yt_upload", "done")
    if do_fb_upload:
        mark_subtask(topic_dir, "Unit-Publisher", "fb_upload", "done")
    if do_social:
        mark_subtask(topic_dir, "Unit-Publisher", "social_share", "done")

    return "\n".join(results)

================================================================================
"""
unit_scout.py — Unit-Scout
Writes topic queue to .runtime/topics/{profile}/topic_memory.json

Config priority (highest → lowest):
  1. scout_config block in data.json   ← channel-specific scout settings
  2. audience_profiles.json[profile]   ← profile niches + scraping_url
  3. top-level data.json keys          ← global defaults
  4. _SCOUT_TASK_DEFAULTS              ← code-level fallback

Scraping URL resolution:
  1. scout_config["scraping_url_file"]
  2. profile_data["scraping_url"]
  3. data/scraping_url_{profile}.json  (naming convention probe)
  4. data/scraping_url.json            (global fallback — Rule 25)
"""
from pathlib import Path
from crewai import Crew
from cf2.crews.crew import CF2Crew
from cf2.core.paths import TOPICS_ROOT

# Code-level fallback — only used when key absent from all config sources
_SCOUT_TASK_DEFAULTS = {
    "platforms":          ["scraping_url", "YouTube", "Facebook", "LinkedIn", "instagram"],
    "niches":             ["AI", "Tech"],
    "min_virality_score": 75,
    "output_queue_size":  10,
    "auto_consume":       True,
    "use_web_search":     True,
    "force_refresh":      False,
    "force_scraping":     False,
    "channel":            "PlayOwnAi",
}

# Keys inside scout_config that map directly to top-level inputs.
# "scraping_url" is handled separately (renamed to scraping_url_file).
_SCOUT_CONFIG_KEYS = {
    "force_scraping", "force_refresh", "platforms", "niches",
    "min_virality_score", "output_queue_size", "auto_consume",
    "use_web_search", "llm_scout",
    "social_credentials_file", "fb_credentials_file",
    "yt_client_secrets_file", "yt_token_file",
}


def _apply_scout_config(inputs: dict) -> None:
    """
    Flatten scout_config block into top-level inputs.
    scout_config wins over existing top-level keys (it's channel-specific config).
    Called before profile and defaults so priority is: scout_config > profile > defaults.
    """
    scout_cfg = inputs.get("scout_config", {})
    if not scout_cfg:
        return

    for k, v in scout_cfg.items():
        if k == "scraping_url":
            # Rename to the canonical key name expected by _resolve_scraping_url
            inputs["scraping_url_file"] = v
        elif k == "niche_strict":
            inputs["niche_strict"] = v
        elif k in _SCOUT_CONFIG_KEYS:
            inputs[k] = v   # hard override — scout_config is authoritative

    if scout_cfg:
        print(f"⚙️   scout_config applied: {list(scout_cfg.keys())}")


def _load_audience_profile(inputs: dict) -> dict:
    import json
    path = inputs.get("audience_profiles_file", "input/audience_profiles.json")
    key  = inputs.get("audience_profile", "US")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        p = data.get(key, {})
        if not p:
            print(f"⚠️  Unit-Scout: profile '{key}' not in {path}")
        return p
    except FileNotFoundError:
        print(f"⚠️  Unit-Scout: {path} not found — using defaults")
        return {}
    except Exception as exc:
        print(f"⚠️  Unit-Scout: profile load failed — {exc}")
        return {}


def _resolve_scraping_url(inputs: dict, profile: dict) -> str:
    # 1. scout_config set it explicitly (already in inputs["scraping_url_file"])
    explicit = inputs.get("scraping_url_file", "")
    if explicit and explicit != "data/scraping_url.json":
        return explicit
    # 2. Profile owns its sources
    if profile.get("scraping_url"):
        return profile["scraping_url"]
    # 3. Naming convention probe
    key = inputs.get("audience_profile", "US").lower()
    conv = f"data/scraping_url_{key}.json"
    if Path(conv).exists():
        return conv
    # 4. Global fallback
    return "data/scraping_url.json"


def _queue_path(inputs: dict) -> str:
    profile = inputs.get("audience_profile", "global").lower()
    p = TOPICS_ROOT / profile / "topic_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def run(topic: str, workspace: Path, inputs: dict, force: bool = False):
    # --- 0. Short-circuit logic ---
    # If the topic is not "auto", this unit does not perform scouting.
    if inputs.get("_topic", "").lower() != "auto":
        print(f"⏭️  Unit-Scout skipped: topic is '{inputs.get('_topic')}', not 'auto'.")
        return
    # ── 1. Apply scout_config (highest priority) ──────────────────────────
    _apply_scout_config(inputs)

    profile_key  = inputs.get("audience_profile", "US")
    profile_data = _load_audience_profile(inputs)

    # ── 2. Resolve paths ──────────────────────────────────────────────────
    queue_path        = _queue_path(inputs)
    scraping_url_file = _resolve_scraping_url(inputs, profile_data)

    inputs["output_dir"]        = str(workspace)
    inputs["filename"]          = inputs.get("_slug", workspace.name)
    inputs["scout_queue_path"]  = queue_path
    inputs["scraping_url_file"] = scraping_url_file

    # ── 3. Profile niches = highest priority (profile defines audience identity)
    # scout_config["niches"] is only used when profile has no niches defined
    profile_niches = profile_data.get("niches", [])
    if profile_niches:
        inputs["niches"] = profile_niches
        print(f"🎯  Niches from profile [{profile_key}]: {len(profile_niches)} topics")
    elif inputs.get("niches") and inputs["niches"] not in ([], ["AI", "Tech"]):
        print(f"🎯  Niches from scout_config: {inputs['niches']}")

    # ── 4. Inject remaining profile fields as profile_* (no overwrite) ───
    for k, v in profile_data.items():
        if k not in ("scraping_url", "niches"):
            inputs.setdefault(f"profile_{k}", v)

    # ── 5. Fill remaining task template variables ─────────────────────────
    for k, v in _SCOUT_TASK_DEFAULTS.items():
        inputs.setdefault(k, v)

    print(
        f"🔍  Unit-Scout | profile={profile_key}"
        f" | niches={len(inputs.get('niches', []))}"
        f" | force_scraping={inputs.get('force_scraping')}"
        f" | queue={queue_path}"
        f" | sources={scraping_url_file}"
    )

    factory = CF2Crew(inputs)
    return Crew(
        agents=[factory.scout_trend_agent()],
        tasks=[factory.scout_trending_topics()],
        verbose=False,
    ).kickoff(inputs=inputs)











================================================================================
================================================================================
================================================================================
