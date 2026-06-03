"""
weak_words.py — Central loader for filtered word lists.
One source of truth for slugs, hashtags, keyword extraction.
"""
import json
from pathlib import Path
from functools import lru_cache

_THIS_FILE   = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent.parent.parent
WEAK_FILE    = PROJECT_ROOT / "data" / "weak_words.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    """Load weak_words.json once (cached)."""
    if not WEAK_FILE.exists():
        print(f"⚠️  weak_words.json not found: {WEAK_FILE}")
        return {}
    try:
        with open(WEAK_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Failed to load weak_words.json: {e}")
        return {}


@lru_cache(maxsize=1)
def get_stop_words() -> set:
    """For slug generation: stop_words + contractions."""
    data = _load()
    return set(data.get("stop_words", []) + data.get("contractions", []))


@lru_cache(maxsize=1)
def get_hashtag_skip() -> set:
    """For hashtag filtering: stop_words + weak_verbs + hashtag_skip."""
    data = _load()
    return set(
        data.get("stop_words", []) +
        data.get("weak_verbs", []) +
        data.get("hashtag_skip", [])
    )


@lru_cache(maxsize=1)
def get_weak_verbs() -> set:
    """Auxiliary/weak verbs to exclude from keyword extraction."""
    data = _load()
    return set(data.get("weak_verbs", []))
