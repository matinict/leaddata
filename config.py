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
      4. Has directory components    → PROJECT_ROOT / value (preserves structure)
      5. Simple filename only        → INPUT_DIR / filename (legacy behavior)

    Pointer expansion:
      Any key ending in '_file' that points to a .json file and has a
      sibling key with the same name minus '_file' will be loaded and
      injected inline.
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
        if _os.path.dirname(v):
            return str(PROJECT_ROOT / v)
        return str(INPUT_DIR / v)

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
