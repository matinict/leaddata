"""
core/config_loader.py — Config loading + profile deep-merge
with intelligent auto-correction and verbose error reporting
"""
import json
import copy
import os
import re
import unicodedata
from pathlib import Path

from cf2.core.paths import INPUT_DIR, PROJECT_ROOT

# ── Intelligent JSON loader with reporting ──────────────────────────────────

def _safe_json_load(path: Path) -> dict:
    """
    Load JSON with auto-correction. Reports every fix, only fails on unfixable errors.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Cannot read {path}: {e}")

    original = raw
    corrections = []

    # 1. Normalize unicode
    normalized = unicodedata.normalize("NFKC", raw)
    if normalized!= raw:
        corrections.append("Normalized unicode characters (NFKC)")
        raw = normalized

    # 2. Replace common typographic mistakes
    replacements = {
        "→": "->", "←": "<-", "—": "-", "–": "-", "‑": "-",
        "’": "'", "‘": "'", "´": "'", "“": '"', "”": '"', "„": '"',
        "\u00a0": " ", "\u200b": "", "\ufeff": "",
    }

    for bad, good in replacements.items():
        if bad in raw:
            count = raw.count(bad)
            raw = raw.replace(bad, good)
            corrections.append(f"Replaced '{bad}' → '{good}' ({count}x)")

    # 3. Remove illegal control characters
    cleaned = "".join(ch for ch in raw if ord(ch) >= 32 or ch in "\n\r\t")
    if len(cleaned)!= len(raw):
        removed = len(raw) - len(cleaned)
        corrections.append(f"Removed {removed} illegal control characters")
        raw = cleaned

    # 4. Try normal parse
    try:
        result = json.loads(raw)
        if corrections:
            print(f"⚠️ Auto-fixed {path.name}:")
            for c in corrections:
                print(f" • {c}")
        return result
    except json.JSONDecodeError as e1:
        # 5. Attempt fix for multiline strings
        try:
            def fix_string(match):
                s = match.group(0)
                inner = s[1:-1]
                # Replace newlines/tabs with space
                fixed_inner = re.sub(r"[\n\r\t]+", " ", inner)
                fixed_inner = re.sub(r" {2,}", " ", fixed_inner)
                return f'"{fixed_inner}"'

            pattern = r'"(?:\\.|[^"\\])*"'
            raw_fixed = re.sub(pattern, fix_string, raw, flags=re.DOTALL)

            if raw_fixed!= raw:
                corrections.append("Fixed unescaped newlines inside quoted strings")

            result = json.loads(raw_fixed)

            print(f"⚠️ Auto-fixed {path.name}:")
            for c in corrections:
                print(f" • {c}")
            print(f" • Recovered from JSON syntax error at line {e1.lineno}")

            return result

        except json.JSONDecodeError as e2:
            # 6. Unfixable — show detailed error and STOP
            print(f"\n❌ UNFIXABLE JSON ERROR in {path.name}")
            _explain_json_error(path, original, e2)

            if corrections:
                print(f"\nAuto-corrections attempted:")
                for c in corrections:
                    print(f" • {c}")

            print("\n💡 Fix the file and re-run. Execution interrupted.\n")
            raise

def _explain_json_error(path: Path, content: str, error: json.JSONDecodeError):
    """Provide human-friendly error messages"""
    lines = content.split("\n")
    err_line = error.lineno - 1
    start = max(0, err_line - 2)
    end = min(len(lines), err_line + 3)

    print(f" Error: {error.msg} at line {error.lineno}, column {error.colno}\n")
    print(" Context:")
    for i in range(start, end):
        marker = " →" if i == err_line else " "
        snippet = lines[i][:120].replace("\t", " ")
        print(f"{marker} {i+1:3}: {snippet}")

    print("\n Common causes:")
    if "control character" in error.msg.lower():
        print(" • Line break inside \"...\" (press Enter in the middle of text)")
        print(" • Paste from Word/PDF with hidden characters")
    elif "Expecting" in error.msg:
        print(" • Missing comma after previous line")
        print(" • Extra comma before } or ]")
        print(" • Unclosed quote \" ")
    elif "delimiter" in error.msg.lower():
        print(" • Missing colon : between key and value")
        print(" • Example: \"key\" \"value\" should be \"key\": \"value\"")
    elif "property name" in error.msg.lower():
        print(" • Keys must be in double quotes: key → \"key\"")

# ── Rest of file unchanged (deep merge, load_config, etc.) ──────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result

def _resolve_clip_config(raw: dict) -> dict:
    suffix_map = raw.pop("_format_suffix", {})
    shared = raw.pop("shared", {})
    base_keys = {"_clips_base", "_folder_prefix"}
    result = {k: v for k, v in raw.items() if k in base_keys}
    for fmt, block in raw.items():
        if fmt in base_keys or not isinstance(block, dict):
            continue
        suffix = suffix_map.get(fmt, "")
        merged = {}
        if block.get("_extend") == "shared":
            merged = _deep_copy(shared)
        for k, v in block.items():
            if k == "_extend":
                continue
            merged[k] = v
        result[fmt] = _substitute(merged, {"suffix": suffix, "fmt": fmt})
    return result

def _deep_copy(obj):
    if isinstance(obj, dict):
        return {k: _deep_copy(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_copy(v) for v in obj]
    return obj

def _substitute(obj, vars: dict):
    if isinstance(obj, str):
        for key, val in vars.items():
            obj = obj.replace(f"{{{key}}}", str(val))
        return obj
    if isinstance(obj, dict):
        return {k: _substitute(v, vars) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_substitute(v, vars) for v in obj]
    return obj

def load_config(profile: str | None = None) -> dict:
    base_path = INPUT_DIR / "data.json"
    config: dict = {}

    if base_path.exists():
        config = _safe_json_load(base_path)
    else:
        print(f"⚠️ Base config not found: {base_path}")

    if profile:
        profile_path = _resolve_profile_path(profile)
        if profile_path.exists():
            override = _safe_json_load(profile_path)
            config = _deep_merge(config, override)
            print(f"📂 Profile merged: {profile_path.name}")
        else:
            print(f"⚠️ Profile not found: {profile_path} — using base config only")

    config = _load_llm_config(config)
    config = _expand_file_pointers(config)

    for key in ["focus", "audience", "tone", "style", "notes"]:
        if key not in config or config[key] is None:
            config[key] = ""
        elif isinstance(config[key], str):
            config[key] = config[key].strip()

    return config

def _load_llm_config(config: dict) -> dict:
    if config.get("llm_config"):
        config.pop("llmconf", None)
        return config

    llmconf_val = config.get("llmconf")
    llmconf_path = _resolve_llmconf_path(llmconf_val)

    if llmconf_path and llmconf_path.exists():
        raw = _safe_json_load(llmconf_path)
        config["llm_config"] = raw.get("llm_config", raw)
        print(f"🤖 LLM config loaded: {llmconf_path.name}")
    else:
        print(f"⚠️ llm_conf not found: {llmconf_path} — LLM fallback chain unavailable")

    config.pop("llmconf", None)
    return config

def _resolve_llmconf_path(llmconf_val: str | None) -> Path | None:
    if llmconf_val:
        if os.path.isabs(llmconf_val):
            return Path(llmconf_val)
        return PROJECT_ROOT / llmconf_val
    fallback = INPUT_DIR / "llm_conf.json"
    return fallback if fallback.exists() else None

def _expand_file_pointers(config: dict) -> dict:
    from cf2.core.paths import RUNTIME_PATHS
    secrets_dir = str(RUNTIME_PATHS["secrets"])
    secret_patterns = {"client_secret", "client_secrets", "token",
                        "credentials", "api_key", "secret", "credential"}

    def _is_secret(filename: str) -> bool:
        return any(p in filename.lower() for p in secret_patterns)

    def _resolve_path(v: str) -> str:
        if os.path.isabs(v):
            return v
        if v.startswith("input/"):
            return str(PROJECT_ROOT / v)
        if _is_secret(v):
            return os.path.join(secrets_dir, os.path.basename(v))
        if os.path.dirname(v):
            return str(PROJECT_ROOT / v)
        return str(INPUT_DIR / v)

    def _walk(obj: dict | list):
        if isinstance(obj, dict):
            for k, v in list(obj.items()):
                if isinstance(v, str) and k.endswith("_file"):
                    if not os.path.isabs(v):
                        v = _resolve_path(v)
                        obj[k] = v
                    inline_key = k[:-5]
                    if (v.endswith(".json") and inline_key not in obj and os.path.exists(v)):
                        try:
                            loaded = _safe_json_load(Path(v))
                            if "_format_suffix" in loaded or "shared" in loaded:
                                loaded = _resolve_clip_config(loaded)
                            obj[inline_key] = loaded
                        except Exception:
                            pass
                elif isinstance(v, (dict, list)):
                    _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    _walk(item)
    _walk(config)
    return config

def _resolve_profile_path(profile: str) -> Path:
    if os.path.isabs(profile):
        return Path(profile)
    if "/" in profile:
        return INPUT_DIR / profile
    if profile.endswith(".json"):
        return INPUT_DIR / profile
    return INPUT_DIR / f"data{profile}.json"

def list_profiles() -> list[str]:
    names = ["default (data.json)"]
    for f in sorted(INPUT_DIR.glob("data*.json")):
        if f.name in ("data.json", "data.schema.json"):
            continue
        names.append(f.stem[4:])
    return names
