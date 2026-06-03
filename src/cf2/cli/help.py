"""
cli/help.py — Auto-discovery help system
Zero hardcoding. Discovers units, profiles, targets from filesystem.
Future: extensible for any CLI introspection commands.
"""
import re
import json
from pathlib import Path


def _project_root() -> Path:
    """Walk up from this file to find project root (contains src/)."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src" / "cf2").is_dir():
            return parent
    return Path.cwd()


def discover_units() -> list:
    """
    Scan src/cf2/units/ for unit_*.py files.
    Returns list of dicts: {file, name, display, desc}
    """
    root = _project_root()
    units_dir = root / "src" / "cf2" / "units"
    if not units_dir.is_dir():
        return []

    units = []
    for f in sorted(units_dir.glob("unit_*.py")):
        name = f.stem.replace("unit_", "")
        display = f"Unit-{name.capitalize()}"

        desc = ""
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if m:
                first_line = m.group(1).strip().split("\n")[0].strip()
                if first_line and not first_line.startswith("unit_"):
                    desc = first_line[:60]
        except Exception:
            pass

        units.append({
            "file": f.name,
            "name": name,
            "display": display,
            "desc": desc or f.name,
        })

    return units


def discover_profiles() -> list:
    """
    Scan input/profile/ for *.json files.
    Returns list of dicts: {file, stem, topic, desc, units}
    """
    root = _project_root()
    profile_dir = root / "input" / "profile"
    if not profile_dir.is_dir():
        return []

    profiles = []
    for f in sorted(profile_dir.glob("*.json")):
        topic = ""
        desc = ""
        enabled_units = []

        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
            topic = data.get("topic", "")[:50]
            desc = data.get("description", "")[:50]

            for key, val in data.items():
                if key.startswith("Unit-") and val is True:
                    enabled_units.append(key.replace("Unit-", ""))
        except Exception:
            pass

        profiles.append({
            "file": f.name,
            "stem": f.stem,
            "topic": topic,
            "desc": desc,
            "units": enabled_units,
        })

    return profiles


def discover_make_targets() -> dict:
    """
    Extract make targets from Makefile, grouped by prefix.
    Returns dict: {prefix: [target, ...]}
    """
    root = _project_root()
    makefile = root / "Makefile"
    if not makefile.exists():
        return {}

    groups = {}
    try:
        content = makefile.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"^([a-zA-Z][\w-]*):", content, re.MULTILINE):
            target = m.group(1)
            if target in {"help", "all", "default", "PHONY"}:
                continue
            prefix = target.split("-")[0]
            groups.setdefault(prefix, []).append(target)
    except Exception:
        pass

    return groups


def discover_tools() -> list:
    """
    Scan src/cf2/tools/ for *.py files.
    Returns list of dicts: {file, name, desc}
    """
    root = _project_root()
    tools_dir = root / "src" / "cf2" / "tools"
    if not tools_dir.is_dir():
        return []

    tools = []
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue

        desc = ""
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if m:
                first_line = m.group(1).strip().split("\n")[0].strip()
                if first_line:
                    desc = first_line[:60]
        except Exception:
            pass

        tools.append({
            "file": f.name,
            "name": f.stem,
            "desc": desc or f.name,
        })

    return tools


def discover_services() -> list:
    """
    Scan src/cf2/core/services/ for *_service.py files.
    Returns list of dicts: {file, name, desc}
    """
    root = _project_root()
    services_dir = root / "src" / "cf2" / "core" / "services"
    if not services_dir.is_dir():
        return []

    services = []
    for f in sorted(services_dir.glob("*_service.py")):
        name = f.stem.replace("_service", "")

        desc = ""
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r'"""(.*?)"""', content, re.DOTALL)
            if m:
                first_line = m.group(1).strip().split("\n")[0].strip()
                if first_line:
                    desc = first_line[:60]
        except Exception:
            pass

        services.append({
            "file": f.name,
            "name": name,
            "desc": desc or f.name,
        })

    return services


def show_help():
    """Print full auto-discovered help."""
    units = discover_units()
    profiles = discover_profiles()
    targets = discover_make_targets()
    tools = discover_tools()
    services = discover_services()

    print()
    print("══════════════════════════════════════════════════════════════")
    print("  🎬  CF2 — CrewAI Flow Factory")
    print("══════════════════════════════════════════════════════════════")

    # ── Units ────────────────────────────────────────────────
    print()
    print(f"  UNITS ({len(units)})")
    print("  ─────────────────────────────────────────────────────────")
    if units:
        max_w = max(len(u["display"]) for u in units)
        for u in units:
            print(f"    {u['display']:<{max_w + 2}} {u['desc']}")
    else:
        print("    (none found)")

    # ── Profiles ─────────────────────────────────────────────
    print()
    print(f"  PROFILES ({len(profiles)})")
    print("  ─────────────────────────────────────────────────────────")
    if profiles:
        max_w = max(len(p["stem"]) for p in profiles)
        for p in profiles:
            label = p["topic"] or p["desc"] or "(no topic)"
            unit_str = f"  [{', '.join(p['units'])}]" if p["units"] else ""
            print(f"    {p['stem']:<{max_w + 2}} {label}{unit_str}")
    else:
        print("    (none found)")

    # ── Make Targets ─────────────────────────────────────────
    if targets:
        total = sum(len(v) for v in targets.values())
        print()
        print(f"  MAKE TARGETS ({total})")
        print("  ─────────────────────────────────────────────────────────")
        for prefix in sorted(targets.keys()):
            cmds = sorted(targets[prefix])
            if len(cmds) <= 4:
                print(f"    {', '.join(f'make {c}' for c in cmds)}")
            else:
                print(f"    make {prefix}*  ({len(cmds)} targets)")

    # ── Tools ────────────────────────────────────────────────
    if tools:
        print()
        print(f"  TOOLS ({len(tools)})")
        print("  ─────────────────────────────────────────────────────────")
        max_w = max(len(t["name"]) for t in tools)
        for t in tools:
            print(f"    {t['name']:<{max_w + 2}} {t['desc']}")

    # ── Services ─────────────────────────────────────────────
    if services:
        print()
        print(f"  SERVICES ({len(services)})")
        print("  ─────────────────────────────────────────────────────────")
        max_w = max(len(s["name"]) for s in services)
        for s in services:
            print(f"    {s['name']:<{max_w + 2}} {s['desc']}")

    # ── TTS Shortcuts ────────────────────────────────────────
    print()
    print("  TTS SHORTCUTS")
    print("  ─────────────────────────────────────────────────────────")
    print("    -ed = Edge    -xt = XTTS    -pi = Piper    -gt = gTTS")

    # ── Usage ────────────────────────────────────────────────
    print()
    print("  USAGE")
    print("  ─────────────────────────────────────────────────────────")
    print("    make <target>                 Run pipeline")
    print("    make <target>-force           Force regenerate")
    print("    uv run python -m cf2.main --profile <name> --unit <Unit>")
    print("    uv run python -m cf2.main --help-all")
    print("    uv run python -m cf2.main --list-profiles")
    print("    uv run python -m cf2.main --llm-status")

    print()
    print("══════════════════════════════════════════════════════════════")
    print()


def show_units():
    """Print units only."""
    units = discover_units()
    print(f"\n📦 UNITS ({len(units)})\n")
    if units:
        max_w = max(len(u["display"]) for u in units)
        for u in units:
            print(f"  {u['display']:<{max_w + 2}} {u['desc']}")
    print()


def show_profiles():
    """Print profiles only."""
    profiles = discover_profiles()
    print(f"\n📂 PROFILES ({len(profiles)})\n")
    if profiles:
        max_w = max(len(p["stem"]) for p in profiles)
        for p in profiles:
            label = p["topic"] or p["desc"] or "(no topic)"
            print(f"  {p['stem']:<{max_w + 2}} {label}")
    print()


def show_targets():
    """Print make targets only."""
    targets = discover_make_targets()
    total = sum(len(v) for v in targets.values())
    print(f"\n🎯 MAKE TARGETS ({total})\n")
    for prefix in sorted(targets.keys()):
        cmds = sorted(targets[prefix])
        print(f"  {prefix}: {', '.join(cmds)}")
    print()


# ── CLI entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        show_help()
    else:
        cmd = sys.argv[1].lower()
        if cmd in {"units", "unit", "-u"}:
            show_units()
        elif cmd in {"profiles", "profile", "-p"}:
            show_profiles()
        elif cmd in {"targets", "make", "-m"}:
            show_targets()
        elif cmd in {"help", "-h", "--help"}:
            show_help()
        else:
            print(f"Unknown command: {cmd}")
            print("Available: units, profiles, targets, help")
            sys.exit(1)
