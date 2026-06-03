"""
trend_queue_helper.py
─────────────────────────────────────────────────────────────────────────────
Utility functions for managing the topic_memory.json lifecycle.
Import in main.py or call standalone.

Queue path convention: .runtime/topics/{profile}/topic_memory.json
  Default profile: "global"  →  .runtime/topics/global/topic_memory.json
─────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# ── Default queue path via .runtime/topics/ ──────────────────────────────
_THIS_FILE   = Path(__file__).resolve()
_PROJECT_ROOT = _THIS_FILE.parent.parent.parent.parent   # src/cf2/tools → ×4
QUEUE_PATH   = str(_PROJECT_ROOT / ".runtime" / "topics" / "global" / "topic_memory.json")


def load_queue(path: str = QUEUE_PATH) -> list:
    """Load topic_memory.json; extract 'queue' list; return empty list on error."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data.get("queue", data.get("items", []))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_queue(queue: list, path: str = QUEUE_PATH) -> None:
    """Save queue list back into topic_memory.json structure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            memory = json.load(f)
        if not isinstance(memory, dict):
            memory = {"queue": [], "current": None, "archive": []}
        memory["queue"] = queue
        memory["_updated_at"] = datetime.now(timezone.utc).isoformat()
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(memory, f, indent=2, ensure_ascii=False)
    except Exception:
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(queue, f, indent=2, ensure_ascii=False)


def mark_topic_used(title: str, performance: Optional[dict] = None, path: str = QUEUE_PATH) -> bool:
    """Mark a topic as USED (archived) in topic_memory.json after production completes."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            memory = json.load(f)
        if not isinstance(memory, dict):
            memory = {"queue": [], "current": None, "archive": []}

        queue = memory.get("queue", [])
        title_lower = title.lower()
        found = False

        for t in queue:
            t_title = t.get("title", t.get("topic", "")).lower()
            if t_title == title_lower:
                t["status"] = "done"
                t["completed_at"] = datetime.now(timezone.utc).isoformat()
                if performance:
                    t["performance"] = performance
                if "archive" not in memory:
                    memory["archive"] = []
                memory["archive"].append(t)
                found = True
                break

        if found:
            memory["queue"] = [t for t in queue if t.get("title", t.get("topic", "")).lower() != title_lower]
            memory["_updated_at"] = datetime.now(timezone.utc).isoformat()
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(memory, f, indent=2, ensure_ascii=False)
            print(f"[TopicMemory] ✅ Archived: \"{title}\"")
        else:
            print(f"[TopicMemory] ⚠️  Topic not found: \"{title}\"")

        return found
    except Exception as e:
        print(f"[TopicMemory] ⚠️  Error: {e}")
        return False


def print_queue_summary(path: str = QUEUE_PATH) -> None:
    """Print a human-readable queue status summary."""
    queue = load_queue(path)
    if not queue:
        print("[TopicMemory] Queue is empty.")
        return

    from collections import Counter
    status_counts = Counter(t.get("status", "UNKNOWN") for t in queue)

    print(f"\n📋 Topic Memory Summary  ({path})")
    print(f"   Total topics: {len(queue)}")

    for status, count in sorted(status_counts.items()):
        icon = {"UNUSED": "📌 ", "SELECTED": "🎯 ", "IN_PROGRESS": "⚙️  ", "done": "✅ ", "ARCHIVED": "🗃️  "}.get(status, "❓ ")
        print(f"   {icon} {status}: {count}")

    unused = [t for t in queue if t.get("status") in ("UNUSED", "queued")]
    if unused:
        print(f"\n   🏆 Top UNUSED Topics:")
        for i, t in enumerate(unused[:5], 1):
            print(f"   {i}. [{t.get('virality_score', t.get('total_score', '?')):>3}] {t.get('title', t.get('topic', 'N/A'))[:65]}")
    print()


if __name__ == "__main__":
    print_queue_summary()
