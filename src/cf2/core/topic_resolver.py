"""
core/topic_resolver.py — Topic resolution + slug + workspace + CACHE
Rule 10: All workspaces in.runtime/output/{slug}
Rule 11: PascalCase slug, 3 meaningful words, stop-words skipped.
Rule 12: __01/__02 collision suffix — never overwrite another topic's folder.
Rule 2:  Topic priority: CLI → queue → data.json

NEW: Cache in.runtime/cache/topics/{slug}.json
     If same topic+unit exists, return cached data instantly.
"""
import re
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

from cf2.core.weak_words import get_stop_words

# ── Paths ─────────────────────────────────────────────────────────────────
_THIS_FILE   = Path(__file__).resolve()
PROJECT_ROOT = _THIS_FILE.parent.parent.parent.parent
OUTPUT_ROOT  = PROJECT_ROOT / ".runtime" / "output"
TOPICS_ROOT  = PROJECT_ROOT / ".runtime" / "topics"
CACHE_ROOT   = PROJECT_ROOT / ".runtime" / "cache" / "topics"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
TOPICS_ROOT.mkdir(parents=True, exist_ok=True)
CACHE_ROOT.mkdir(parents=True, exist_ok=True)

_STOP_WORDS = get_stop_words()

# ── Cache helpers ─────────────────────────────────────────────────────────
def _cache_key(topic: str, unit: str, profile: str) -> str:
    raw = f"{topic.lower().strip()}|{unit}|{profile}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def cache_get(topic: str, unit: str, profile: str, ttl_days: int = 7):
    """Return cached payload or None"""
    key = _cache_key(topic, unit, profile)
    path = CACHE_ROOT / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        if ttl_days:
            ts = datetime.fromisoformat(data["_cached_at"])
            if datetime.now() - ts > timedelta(days=ttl_days):
                path.unlink(missing_ok=True)
                return None
        return data["payload"]
    except:
        return None

def cache_set(topic: str, unit: str, profile: str, payload: dict):
    """Save payload to cache"""
    key = _cache_key(topic, unit, profile)
    path = CACHE_ROOT / f"{key}.json"
    path.write_text(json.dumps({
        "_cached_at": datetime.now().isoformat(),
        "_topic": topic,
        "_unit": unit,
        "_profile": profile,
        "payload": payload
    }, indent=2, ensure_ascii=False))
    return path

# ── Slug (Rule 11) ────────────────────────────────────────────────────────
def generate_slug(topic: str, n_words: int = 3) -> str:
    clean = re.sub(r"[^A-Za-z0-9\s]", "", topic)
    words = [w for w in clean.split() if w.lower() not in _STOP_WORDS]
    return "".join(w.capitalize() for w in words[:n_words]) or "Unknown"

# ── Workspace (Rule 12) ───────────────────────────────────────────────────
def resolve_workspace(topic: str, slug: str) -> Path:
    """Same topic → reuse folder. New topic → slug__01, slug__02, …"""
    def _owns(folder: Path) -> bool:
        mp = folder / "meta.json"
        if not mp.exists():
            contents = [f for f in folder.iterdir() if f.name != "__pycache__"]
            return len(contents) == 0 or all(f.is_dir() for f in contents)
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            return m.get("topic") == topic or m.get("slug") == folder.name
        except Exception:
            return False

    base = OUTPUT_ROOT / slug
    if not base.exists():
        base.mkdir(parents=True)
        return base
    if _owns(base):
        return base

    counter = 1
    while True:
        candidate = OUTPUT_ROOT / f"{slug}__{counter:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
        if _owns(candidate):
            return candidate
        counter += 1

# ── Queue helpers ─────────────────────────────────────────────────────────
def _queue_file(inputs: dict) -> Path:
    profile = inputs.get("audience_profile", "global").lower()
    p = TOPICS_ROOT / profile
    p.mkdir(parents=True, exist_ok=True)
    return p / "topic_memory.json"

def pick_from_queue(inputs: dict) -> str:
    path = _queue_file(inputs)
    if not path.exists():
        print(f"⚠️  Queue not found: {path}")
        return ""
    try:
        data  = json.loads(path.read_text(encoding="utf-8"))
        queue = data.get("queue", []) if isinstance(data, dict) else data
    except Exception as exc:
        print(f"⚠️  Queue read error: {exc}")
        return ""
    candidates = [t for t in queue if t.get("status") in ("SELECTED", "UNUSED", "queued")]
    if not candidates:
        print(f"⚠️  No UNUSED topics in queue: {path}")
        return ""
    best = max(candidates, key=lambda t: t.get("virality_score", 0))
    best["status"] = "IN_PROGRESS"
    if isinstance(data, dict):
        data["queue"] = queue
    else:
        data = {"queue": queue, "archive": []}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    title = best.get("title", "").strip()
    print(f"📥  Auto-topic [{best.get('virality_score', 0)}pts]: {title}")
    return title

# ── Topic resolution (Rule 2) ─────────────────────────────────────────────
def resolve_topic(inputs: dict) -> str:
    topic = inputs.get("topic", "").strip()
    if topic and topic.lower() != "auto":
        return topic
    scout_on = bool(inputs.get("Unit-Scout") or inputs.get("social_scout_unit"))
    if scout_on:
        picked = pick_from_queue(inputs)
        if picked:
            return picked
        return "auto"
    return ""
