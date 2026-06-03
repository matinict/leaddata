"""
🎛 flow_controller.py — Orchestrator ONLY
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
)
from cf2.core.executor import (
    cleanup_stale_locks, force_cleanup_all_locks,
)
from cf2.core.topic_resolver import resolve_topic, generate_slug, resolve_workspace, pick_from_queue
from cf2.core.executor import run_unit
from cf2.core.registry import (
    get_pipeline_order,
    build_unit_flags,
    get_available_units,
    is_unit_available,
    get_unit_config_key,
    get_unit_config_file,
)
from cf2.cli.cli import parse_args, apply_cli_overrides, install_sigint_handler
from config import load_profile, resolve_config_paths

# Suppress noisy warnings
warnings.filterwarnings("ignore", message=".*skip_file_prefixes.*")
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic.*")
logging.getLogger("LiteLLM").setLevel(logging.CRITICAL)
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

_AUTO = "auto"
_logger = logging.getLogger(__name__)

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
            print("⚠  run_pipeline() already running in another thread — IGNORING")
            return

        if _pipeline_ran:
            print("⚠  run_pipeline() already completed — IGNORING duplicate")
            _pipeline_lock.release()
            return

        try:
            _pipeline_ran = True

            inputs = self.state.get("inputs", {})
            unit   = inputs.get("_unit")
            force  = inputs.get("_force", False)

            # ── Dynamic unit flags (Rule 28/29) ────────────────────────
            explicit_flags = {k: v for k, v in inputs.items() if k.startswith("Unit-")}
            merged_flags = build_unit_flags(explicit_flags)
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
                # Single unit mode — validate availability (Rule 28)
                if not is_unit_available(unit):
                    available = get_available_units()
                    print(f"❌  {unit} not available (no config file in input/unit/)")
                    print(f"    Available: {', '.join(sorted(available))}")
                    return
                run_unit(unit, topic, workspace, inputs, force)
            else:
                # Full pipeline — dynamic order from registry (Rule 28)
                pipeline_order = get_pipeline_order()
                print(f"🔄  Full pipeline — {workspace.name}")
                print(f"📦  Available units: {len(pipeline_order)}")

                skip_scout = inputs.get("_scout_done", False)
                for u in pipeline_order:
                    if not inputs.get(u, False):
                        print(f"⏭  SKIP: {u} (not enabled in profile)")
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
    print(f"🏷   Slug      : {slug}")
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

    # Rule 29: Safety fallbacks — all logged for observability
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
    }

    # Rule 29: Log every fallback for observability
    for k, v in D.items():
        if k not in inputs:
            _logger.warning(f"CONFIG FALLBACK: {k}={v} (Rule 29 — safety only)")
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

    # Rule 29: Auto-inject config file paths from registry (no hardcodes)
    for unit in get_available_units():
        cfg_key = get_unit_config_key(unit)
        if cfg_key:
            file_key = f"{cfg_key}_file"
            if file_key not in inputs:
                cfg_path = get_unit_config_file(unit)
                if cfg_path:
                    inputs[file_key] = str(cfg_path)
                    _logger.debug(f"CONFIG INJECT: {file_key}={cfg_path}")

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
        print(f"🗂   Profile   : {profile_name}")
    else:
        slug = generate_slug(topic)
        workspace = resolve_workspace(topic, slug)
        _init_meta(workspace, topic, slug)

        if args.force:
            force_cleanup_all_locks(workspace)
        else:
            cleanup_stale_locks(workspace)

        print(f"\n📁  Workspace : {workspace}")
        print(f"🏷   Slug      : {slug}")
        print(f"📝  Topic     : {topic}")
        print(f"🗂   Profile   : {profile_name}")

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
