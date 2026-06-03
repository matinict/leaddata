"""
core/paths.py — Single source of truth for ALL project paths.

File location:  src/cf2/core/paths.py
Project root:   4 parents up  →  .../cf2/

Rule: Every other module imports from here. Zero scattered path math elsewhere.

Directory layout this file owns:
    cf2/
    └── .runtime/                ← ALL runtime data lives here
        ├── output/              ← topic workspaces (Rule 10)
        │   └── {TopicSlug}/
        │       ├── debate/
        │       ├── animation/
        │       ├── definition/
        │       ├── YT/
        │       ├── meta.json
        │       └── .lock
        ├── topics/              ← Unit-Scout queues, per audience profile
        │   ├── us/
        │   │   └── topic_memory.json
        │   ├── ca/
        │   │   └── topic_memory.json
        │   └── global/
        │       └── topic_memory.json
        ├── logs/                ← pipeline-level operational logs
        ├── cache/               ← transient cache (safe to delete)
        ├── secrets/             ← OAuth tokens, API keys (git-ignored)
        └── meta/                ← global meta registry (all topics)
"""
from pathlib import Path
from typing import Dict


# ── Project root ──────────────────────────────────────────────────────────────
# src/cf2/core/paths.py → .parent×4 → project root (cf2/)
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent.parent.parent


# ── Input (source data, configs, credentials) ────────────────────────────────
INPUT_DIR: Path = PROJECT_ROOT / "input"

# ── Runtime root — ALL generated/operational data lives here ─────────────────
# Nothing the pipeline produces ever lands directly in PROJECT_ROOT.
# .runtime/ is git-ignored in its entirety.
RUNTIME_ROOT: Path = PROJECT_ROOT / ".runtime"

# Topic workspaces: .runtime/output/{TopicSlug}/
OUTPUT_ROOT: Path = RUNTIME_ROOT / "output"

# Scout queues: .runtime/topics/{profile}/topic_memory.json
# Unit-Scout writes here. topic_resolver.py reads from here.
# Never use data/topic_memory.json — that path is legacy and unsupported.
TOPICS_ROOT: Path = RUNTIME_ROOT / "topics"

RUNTIME_PATHS: Dict[str, Path] = {
    "root"   : RUNTIME_ROOT,
    "output" : OUTPUT_ROOT,               # topic workspaces
    "topics" : TOPICS_ROOT,               # scout queues per audience profile
    "logs"   : RUNTIME_ROOT / "logs",     # executor traces, progress, lock warnings
    "cache"  : RUNTIME_ROOT / "cache",    # transient — safe to wipe between runs
    "secrets": RUNTIME_ROOT / "secrets",  # OAuth tokens, client_secrets.json
    "meta"   : RUNTIME_ROOT / "meta",     # global topic registry
}


# ── Auto-create all directories on import ─────────────────────────────────────
INPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
TOPICS_ROOT.mkdir(parents=True, exist_ok=True)
for _p in RUNTIME_PATHS.values():
    _p.mkdir(parents=True, exist_ok=True)


# ── Per-topic workspace helpers ───────────────────────────────────────────────

def get_topic_dir(slug: str) -> Path:
    """
    Return the workspace root for a given topic slug.
    Caller is responsible for slug collision handling (Rule 12).
    The folder is created if it does not exist.
    """
    p = OUTPUT_ROOT / slug
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_topic_paths(slug: str) -> Dict[str, Path]:
    """
    Return all standard sub-paths for a topic workspace.
    Sub-directories are created automatically; meta.json and .lock are not.

    Usage:
        from cf2.core.paths import get_topic_paths
        paths = get_topic_paths("IcelandYetBeats")
        debate_dir = paths["debate"]
    """
    base = get_topic_dir(slug)

    paths: Dict[str, Path] = {
        "root"      : base,
        "debate"    : base / "debate",
        "animation" : base / "animation",
        "definition": base / "definition",
        "comparison": base / "comparison",
        "yt"        : base / "YT",
        "meta"      : base / "meta.json",   # file — do not mkdir
        "lock"      : base / ".lock",       # file — do not mkdir
    }

    for key, path in paths.items():
        if key not in ("meta", "lock"):
            path.mkdir(parents=True, exist_ok=True)

    return paths


# ── Scout queue helpers ───────────────────────────────────────────────────────

def get_queue_path(profile: str = "global") -> Path:
    """
    Return the topic_memory.json path for a given audience profile.
    Creates the profile directory automatically.

    Examples:
        get_queue_path("US")     → .runtime/topics/us/topic_memory.json
        get_queue_path("CA")     → .runtime/topics/ca/topic_memory.json
        get_queue_path()         → .runtime/topics/global/topic_memory.json
    """
    p = TOPICS_ROOT / profile.lower()
    p.mkdir(parents=True, exist_ok=True)
    return p / "topic_memory.json"


# ── Runtime log helpers ───────────────────────────────────────────────────────

def get_log_path(name: str) -> Path:
    """Return a log file path inside .runtime/logs/."""
    return RUNTIME_PATHS["logs"] / f"{name}.log"


def get_cache_path(name: str) -> Path:
    """Return a cache file path inside .runtime/cache/."""
    return RUNTIME_PATHS["cache"] / name
