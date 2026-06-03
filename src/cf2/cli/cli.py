"""
cli/cli.py — CLI parsing + Ctrl+C handler
Completely isolated from execution logic.
flow_controller imports from here — nothing else does.
"""
import os
import argparse
import signal as _signal
import json
from pathlib import Path
from cf2.meta import VALID_UNITS

def parse_args():
    p = argparse.ArgumentParser(
        description="CF2 — CrewAI Flow Factory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Short profile name (resolves to input/data3d.json automatically)
    uv run python -m cf2.main --unit Unit-Debate --profile 3d
  Full path also works
    uv run python -m cf2.main --profile /abs/path/input/data3d.json --force
  List all available profiles
    uv run python -m cf2.main --list-profiles
  Dry run — show what WOULD execute, nothing runs
    uv run python -m cf2.main --unit Unit-Debate --profile 3d --dry-run
  Force re-run a unit
    uv run python -m cf2.main --unit Unit-Data --topic "AI vs Humans" --force
  Check pipeline status
    uv run python -m cf2.main --status --topic "AI vs Humans"
  Check LLM health
    uv run python -m cf2.main --llm-status
""",
    )
    p.add_argument("--unit", choices=VALID_UNITS, help="Run a specific unit")
    p.add_argument("--subtask", default=None, help="Run specific subtask within unit (transcribe, screen_ocr, merge_context, synthesize, sync, merge, hologram, crop)")
    p.add_argument("--topic", default=None, help="Topic string (overrides data.json queue)")
    p.add_argument("--profile", default=None,
                   help="Short name ('3d', 'Bn') OR full path to a json file")
    p.add_argument("--force", action="store_true", help="Re-run even if already marked done")
    p.add_argument("--dry-run", action="store_true", help="Show what would run — no execution")
    p.add_argument("--list-profiles", action="store_true", help="List available profiles and exit")
    p.add_argument("--yt-upload", action="store_true", help="Enable YouTube upload")
    p.add_argument("--fb-upload", action="store_true", help="Enable Facebook upload")
    p.add_argument("--status", action="store_true", help="Show pipeline status for topic")
    p.add_argument("--llm-status", action="store_true", help="Show LLM health dashboard and exit")
    return p.parse_args()

def apply_cli_overrides(inputs: dict, args) -> dict:
    """Merge CLI flags into the loaded config dict. Returns same dict."""
    if args.topic: inputs["topic"] = args.topic
    if args.yt_upload: inputs["yt_upload"] = True
    if args.fb_upload: inputs["fb_upload"] = True
    return inputs

def show_llm_status():
    """Display LLM health dashboard from runtime cache"""
    status_file = Path(".runtime/cache/llm_status.json")

    if not status_file.exists():
        print("\n📊 LLM STATUS")
        print("─" * 60)
        print("No LLM calls yet — run a pipeline first\n")
        return

    try:
        data = json.loads(status_file.read_text())
    except Exception as e:
        print(f"Error reading LLM status: {e}")
        return

    print("\n📊 LLM STATUS DASHBOARD")
    print("─" * 70)
    print(f"Models tracked: {len(data)}")
    print("─" * 70)

    if not data:
        print("No data available\n")
        return

    for model, info in sorted(data.items()):
        status = info.get("status", "unknown")
        icon = "✅" if status == "success" else "⚡" if status == "fallback" else "❌"

        print(f"\n{icon} {model}")
        last_call = info.get("last_call", "")[:19].replace("T", " ")
        print(f" Last : {last_call or '—'}")
        print(f" Success : {info.get('success_count', 0)} | Fail: {info.get('failure_count', 0)}")

        circuit = info.get("circuit", "CLOSED")
        if circuit == "OPEN":
            until = info.get("open_until", "")[:19].replace("T", " ")
            print(f" 🔒 Circuit: OPEN until {until}")

        error_type = info.get("error_type")
        if error_type:
            error_msg = info.get("last_error", "")[:70]
            print(f" ⚠️ {error_type.upper()}: {error_msg}")

def handle_early_exit(args) -> bool:
    """
    Handle flags that should exit before any pipeline runs.
    Returns True if the program should exit after this call.
    """
    if args.llm_status:
        show_llm_status()
        return True

    if args.list_profiles:
        try:
            from cf2.core.config_loader import list_profiles
            raw = list_profiles()
        except ImportError:
            raw = []

        # Normalize & deduplicate
        profiles, seen = [], set()
        for p in raw:
            name = p.replace(".json", "")
            if "/" in name or "\\" in name:
                name = name.split("/")[-1].split("\\")[-1]
            if "(" in name:
                name = name.split("(")[0].strip()
            if name.startswith("data"):
                name = name[4:]
            name = name or "default"
            if name not in seen:
                seen.add(name)
                profiles.append(name)

        # Ensure default is always first
        if "default" in profiles:
            profiles.remove("default")
            profiles.insert(0, "default")

        print("\n📂 Available Profiles & Usage:\n")
        for name in profiles:
            flag = "" if name == "default" else f" --profile {name}"

            # Debate & Packaging command mapping
            if name == "default":
                debate_cmd, pack_cmd = "make debate", "make pack"
            elif name == "3d":
                debate_cmd, pack_cmd = "make 3d", "make 3d-pack"
            elif name == "Bn":
                debate_cmd, pack_cmd = "make bn", "make bn-pack"
            else:
                debate_cmd = f"make debate p={name}"
                pack_cmd = f"make pack p={name}"

            print(f" {name}")
            print(f" uv run python -m cf2.main --unit Unit-Debate{flag}")
            print(f" {debate_cmd} | {pack_cmd}\n")
        return True

    if args.dry_run:
        print("🔍 DRY RUN — nothing will execute")
        print(f" unit : {args.unit or '(all)'}")
        print(f" subtask : {args.subtask or '—'}")
        print(f" topic : {args.topic or '(from queue)'}")
        print(f" profile : {args.profile or 'default (data.json)'}")
        print(f" force : {args.force}")
        return True

    return False

def install_sigint_handler():
    """
    1st Ctrl+C → graceful stop (KeyboardInterrupt to flow).
    2nd Ctrl+C → force kill (os._exit).
    Returns original handler so caller can restore it in finally block.
    """
    _count = [0]
    _orig = _signal.getsignal(_signal.SIGINT)
    def _handler(sig, frame):
        _count[0] += 1
        if _count[0] == 1:
            print("\n🛑 Ctrl+C — finishing current task then stopping...", flush=True)
            print(" Press Ctrl+C AGAIN to force quit immediately.", flush=True)
            raise KeyboardInterrupt
        else:
            print("\n💀 Force quit.", flush=True)
            os._exit(1)

    _signal.signal(_signal.SIGINT, _handler)
    return _orig
