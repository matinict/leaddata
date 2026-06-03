#cat > src/cf2/cli/launcher.py << 'ENDOFFILE'
"""
cli/launcher.py — Interactive numbered task selector
Auto-discovers profiles + make targets. Zero hardcoding.
Supports topic override: 8 Dentist Montreal
Supports schema help: 8? or ?8
Supports live dashboard: rich split-pane execution
"""
import re
import json
import sys
import shutil
import subprocess
from pathlib import Path


def _project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src" / "cf2").is_dir():
            return parent
    return Path.cwd()


def _discover_profiles() -> list:
    root = _project_root()
    profile_dir = root / "input" / "profile"
    if not profile_dir.is_dir():
        return []

    profiles = []
    for f in sorted(profile_dir.glob("*.json")):
        topic = ""
        enabled = []
        try:
            data = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
            topic = data.get("topic", "")  # Full topic, truncated at display
            for k, v in data.items():
                if k.startswith("Unit-") and v is True:
                    enabled.append(k)
        except Exception:
            pass

        unit_flag = ""
        if len(enabled) == 1:
            unit_flag = f" --unit {enabled[0]}"

        profiles.append({
            "name": f.stem,
            "topic": topic or "(no topic)",
            "units": enabled,
            "cmd": f"uv run python -m cf2.main --profile {f.stem}{unit_flag}",
            "section": "profile",
        })

    return profiles


def _discover_make_targets() -> list:
    root = _project_root()
    makefile = root / "Makefile"
    if not makefile.exists():
        return []

    targets = []
    try:
        content = makefile.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"#\s*make\s+([\w-]+)\s*→\s*(.+)", content):
            target = m.group(1).strip()
            desc = m.group(2).strip()
            if target and desc:
                targets.append({
                    "name": f"make {target}",
                    "desc": desc,
                    "target": target,
                    "section": "make",
                })
    except Exception:
        pass

    return sorted(targets, key=lambda x: x["name"])


def _extract_profile_from_makefile(target: str) -> str:
    root = _project_root()
    makefile = root / "Makefile"
    if not makefile.exists():
        return ""

    try:
        content = makefile.read_text(encoding="utf-8", errors="ignore")
        pattern = rf"^{re.escape(target)}:.*?\n\t(.+)"
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            cmd_line = m.group(1)
            pm = re.search(r"--profile\s+(\S+)", cmd_line)
            if pm:
                return pm.group(1)
    except Exception:
        pass

    return ""


# ── Schema Help Functions ────────────────────────────────────────────────────

def _find_schema_for_profile(profile_name: str):
    root = _project_root()
    schemas_dir = root / "input" / "schemas"
    candidates = [
        schemas_dir / f"{profile_name}.schema.json",
        schemas_dir / f"{profile_name}_schema.json",
        schemas_dir / f"{profile_name}.schemas.json",
        schemas_dir / f"{profile_name}_schemas.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _schema_summary(schema_path: Path) -> dict:
    try:
        data = json.loads(schema_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        return {"error": str(e)}

    props = data.get("properties", {})
    leaddata = props.get("leaddata_config", {}).get("properties", {})
    collect = leaddata.get("collect_config", {}).get("properties", {})
    normalize = leaddata.get("normalize_config", {}).get("properties", {})
    score = leaddata.get("score_config", {}).get("properties", {})
    dubbing = props.get("dubbing_config", {}).get("properties", {})

    return {
        "title": data.get("title", ""),
        "description": data.get("description", ""),
        "required": data.get("required", []),
        "topic_desc": props.get("topic", {}).get("description", ""),
        "sources_desc": leaddata.get("sources", {}).get("description", ""),
        "engine_enum": collect.get("engine", {}).get("enum", []),
        "dedup_enum": normalize.get("deduplicate_on", {}).get("items", {}).get("enum", []),
        "score_enabled_desc": score.get("score_enabled", {}).get("description", ""),
        "tts_engine_enum": dubbing.get("tts_engine", {}).get("enum", []),
        "whisper_model_enum": dubbing.get("whisper_model", {}).get("enum", []),
    }


def _show_profile_help(profile_name: str, profile_topic: str = ""):
    root = _project_root()
    schema = _find_schema_for_profile(profile_name)

    print()
    print("  ════════════════════════════════════════════════════════")
    print(f"  📋 PROFILE HELP: {profile_name}")
    print("  ════════════════════════════════════════════════════════")

    profile_path = root / "input" / "profile" / f"{profile_name}.json"
    if profile_path.exists():
        try:
            pdata = json.loads(profile_path.read_text(encoding="utf-8", errors="ignore"))
            print(f"  Profile : {profile_path.name}")
            if pdata.get("topic"):
                topic_str = pdata['topic']
                if len(topic_str) > 70:
                    topic_str = topic_str[:67] + "..."
                print(f"  Topic   : {topic_str}")
            if pdata.get("_version"):
                print(f"  Version : {pdata['_version']}")

            units_on = [k for k, v in pdata.items() if k.startswith("Unit-") and v is True]
            if units_on:
                print(f"  Enabled : {', '.join(u.replace('Unit-', '') for u in units_on)}")
        except Exception:
            pass

    if schema:
        print(f"  Schema  : {schema.name}")
        info = _schema_summary(schema)

        if "error" not in info:
            if info.get("title"):
                print(f"  Title   : {info['title']}")
            if info.get("description"):
                desc = info['description'][:80]
                print(f"  Desc    : {desc}")
            if info.get("required"):
                print(f"  Required: {', '.join(info['required'])}")

            print()
            print("  CONFIG OPTIONS:")
            if info.get("topic_desc"):
                print(f"    topic     : {info['topic_desc'][:60]}")
            if info.get("sources_desc"):
                print(f"    sources   : {info['sources_desc'][:60]}")
            if info.get("engine_enum"):
                print(f"    engine    : {', '.join(info['engine_enum'])}")
            if info.get("dedup_enum"):
                print(f"    dedup_on  : {', '.join(info['dedup_enum'])}")
            if info.get("tts_engine_enum"):
                print(f"    tts_engine: {', '.join(info['tts_engine_enum'])}")
            if info.get("whisper_model_enum"):
                print(f"    whisper   : {', '.join(info['whisper_model_enum'])}")
        else:
            print(f"  ⚠️ Schema parse error: {info['error']}")
    else:
        print(f"  Schema  : (not found)")

    print()
    print("  USAGE:")
    print(f"    Enter number        → Run with default topic")
    print(f"    Enter number TOPIC  → Override topic")
    print()
    print("  EXAMPLES:")
    print(f"    8")
    print(f"    8 Dentist Montreal")
    print(f"    8 Planning to visit Dentist Montreal")
    print("  ════════════════════════════════════════════════════════")
    print()


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    root = _project_root()
    profiles = _discover_profiles()
    targets = _discover_make_targets()

    menu = []

    for p in profiles:
        units_str = ", ".join(u.replace("Unit-", "") for u in p["units"])
        label = f"{p['name']:<12} {p['topic']}"
        if units_str:
            label += f"  [{units_str}]"
        menu.append({
            "label": label,
            "cmd": p["cmd"],
            "section": "profile",
            "name": p["name"],
            "topic": p["topic"],
        })

    for t in targets:
        menu.append({
            "label": f"{t['name']:<18} {t['desc']}",
            "cmd": f"make {t['target']}",
            "target": t["target"],
            "section": "make",
            "name": t["target"],
        })

    if not menu:
        print("❌ No profiles or targets found.")
        return

    while True:
        # ── Dynamic Terminal Width ──────────────────────────────────
        _term_w = max(80, shutil.get_terminal_size().columns)

        print()
        print("═" * _term_w)
        print("  🎬  CF2 — CrewAI Flow Factory")
        print("═" * _term_w)

        profile_items = [m for m in menu if m["section"] == "profile"]
        make_items = [m for m in menu if m["section"] == "make"]

        _margin = 2
        _gap = 2
        idx = 1

        if profile_items:
            print()
            print("  📂 PROFILES")
            print("  " + "─" * (_term_w - 2))

            # ── Responsive 2-column, 2-line layout ──────────────────
            _cols = 2
            _col_w = max(30, (_term_w - _margin - (_cols - 1) * _gap) // _cols)
            _indent = 7
            _topic_w = max(10, _col_w - _indent)

            def _trunc(s, n):
                return s if len(s) <= n else s[:n - 1] + "…"

            for i in range(0, len(profile_items), _cols):
                left = profile_items[i]
                right = profile_items[i + 1] if i + 1 < len(profile_items) else None

                left_num = idx + i
                right_num = idx + i + 1

                # ── name row ────────────────────────────────────────
                left_name = f"[{left_num:>2}]  {left['name']}"
                if right:
                    right_name = f"[{right_num:>2}]  {right['name']}"
                    print(f"  {left_name:<{_col_w}}  {right_name}")
                else:
                    print(f"  {left_name}")

                # ── topic row ───────────────────────────────────────
                left_topic = _trunc(left.get("topic", ""), _topic_w)
                if right:
                    right_topic = _trunc(right.get("topic", ""), _topic_w)
                    left_cell = " " * _indent + f"{left_topic:<{_col_w - _indent}}"
                    right_cell = " " * _indent + right_topic
                    print(f"  {left_cell}  {right_cell}")
                else:
                    print(f"  {' ' * _indent}{left_topic}")

            idx += len(profile_items)

        if make_items:
            print()
            print("  🎯 PIPELINES")
            print("  " + "─" * (_term_w - 2))
            _start = idx

            # ── Responsive multi-column layout ──────────────────────
            _max_tgt_len = max(len(f"[{_start + i}]{m['target']}") for i, m in enumerate(make_items))
            _min_cw = _max_tgt_len + 2  # +2 for gap between columns
            _pipe_cols = max(1, (_term_w - _margin) // _min_cw)
            _pipe_cw = max(_min_cw, (_term_w - _margin) // _pipe_cols)

            for i in range(0, len(make_items), _pipe_cols):
                _parts = []
                for j in range(_pipe_cols):
                    if i + j < len(make_items):
                        _num = _start + i + j
                        _tgt = make_items[i + j]["target"]
                        _parts.append(f"[{_num:>2}]{_tgt}")
                    else:
                        _parts.append("")
                _row = "".join(f"{p:<{_pipe_cw}}" for p in _parts)
                print(f"  {_row.rstrip()}")
            idx += len(make_items)

        print()
        print("  [q]  Quit")
        print()
        print("  💡 Override topic:  8 Dentist Montreal")
        print("  ❓ Show help:       8? or ?8")
        print()
        print("═" * _term_w)

        try:
            raw = input("  Enter number [topic]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if raw.lower() in {"q", "quit", "exit"}:
            print("👋 Goodbye!")
            break

        if not raw:
            continue

        # ── Help mode: 8? or ?8 ──────────────────────────────────────
        help_match = re.match(r"^\?(\d+)$|^(\d+)\?$", raw)
        if help_match:
            num_str = help_match.group(1) or help_match.group(2)
            idx = int(num_str) - 1
            all_items = profile_items + make_items

            if 0 <= idx < len(all_items):
                selected = all_items[idx]
                if selected["section"] == "profile":
                    _show_profile_help(
                        selected["name"],
                        selected.get("topic", ""),
                    )
                else:
                    print("\n  ⚠️ Schema help available for profiles only.")
                    print(f"  ℹ️  This is a make target: {selected['cmd']}\n")
            else:
                print("  ⚠️ Invalid number.")

            try:
                input("  Press ENTER to continue...")
            except (KeyboardInterrupt, EOFError):
                print("\n👋 Goodbye!")
                break
            continue

        # ── Normal mode: number [topic] ──────────────────────────────
        parts = raw.split(None, 1)
        if not parts:
            print("  ⚠️ Enter a number or 'q'.")
            continue

        try:
            num = int(parts[0]) - 1
        except ValueError:
            print("  ⚠️ Enter a number or 'q'.")
            continue

        topic_override = parts[1].strip() if len(parts) > 1 else ""

        all_items = profile_items + make_items

        if not (0 <= num < len(all_items)):
            print("  ⚠️ Invalid number.")
            continue

        selected = all_items[num]

        # Build final command
        if selected["section"] == "profile":
            cmd = selected["cmd"]
            if topic_override:
                cmd += f' --topic "{topic_override}"'
        else:
            if topic_override:
                target_name = selected.get("target", "")
                profile = _extract_profile_from_makefile(target_name)

                if profile:
                    cmd = (
                        f'uv run python -m cf2.main'
                        f' --profile {profile}'
                        f' --topic "{topic_override}"'
                    )
                else:
                    cmd = selected["cmd"]
                    print(
                        f"  ⚠️ Cannot override topic for "
                        f"'{target_name}' (no --profile found)"
                    )
            else:
                cmd = selected["cmd"]

        if topic_override:
            print(f"\n  📝 Topic: {topic_override}")

        print(f"  🚀 Running: {cmd}\n")

        # ── Try live dashboard, fallback to plain subprocess ────────
        try:
            from cf2.cli.live_runner import run_with_dashboard
            title = selected.get("name", "Pipeline")
            if topic_override:
                title += f" → {topic_override[:40]}"
            run_with_dashboard(cmd, title=title)
            result_code = 0
        except ImportError:
            result = subprocess.run(cmd, cwd=root, shell=True)
            result_code = result.returncode
        except Exception as e:
            print(f"  ⚠️ Dashboard failed: {e}")
            print(f"  ↩️  Falling back to plain output...")
            result = subprocess.run(cmd, cwd=root, shell=True)
            result_code = result.returncode

        if result_code != 0:
            print(f"  🔴 Failed: {cmd}")
        else:
            print(f"  ✅ Complete: {cmd}")


if __name__ == "__main__":
    main()
#ENDOFFILE
