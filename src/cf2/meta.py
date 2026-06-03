"""
meta.py — State & Status Manager (Rule 23)
"""
import json
import os
import logging
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)
META_FILENAME = "meta.json"

_VALID_UNITS_CACHE = None
def get_valid_units():
    global _VALID_UNITS_CACHE
    if _VALID_UNITS_CACHE is None:
        try:
            from cf2.core.registry import get_available_units as get_all_unit_names
            _VALID_UNITS_CACHE = get_all_unit_names()
        except Exception:
            _VALID_UNITS_CACHE = []
    return _VALID_UNITS_CACHE

def __getattr__(name):
    if name == "VALID_UNITS":
        return get_valid_units()
    raise AttributeError(name)

def load_meta(workspace: Path, topic: str = "") -> Dict[str, Any]:
    path = workspace / META_FILENAME
    if path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            corrupt = path.with_name(f"{path.stem}.corrupt.{int(time.time())}.json")
            try: path.rename(corrupt)
            except: pass
            logger.error(f"Corrupt meta backed up to {corrupt}")
        except IOError as e:
            logger.error(f"Cannot read meta: {e}")
            raise
    return _build_default_meta(workspace, topic)

def _build_default_meta(workspace: Path, topic: str = "") -> Dict[str, Any]:
    units = get_valid_units()
    if not units:
        logger.warning("No units from registry")
    return {
        "version": "2.3", "slug": workspace.name, "topic": topic,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": {u: "pending" for u in units}, "errors": {}
    }

def save_meta(workspace: Path, data: Dict[str, Any]) -> None:
    path = workspace / META_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, suffix='.tmp', delete=False, encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno()); tmp = Path(f.name)
        tmp.replace(path)
    except Exception as e:
        if tmp and tmp.exists(): tmp.unlink(missing_ok=True)
        raise

def mark_unit(workspace: Path, unit: str, status: str, error: Optional[str] = None) -> None:
    meta = load_meta(workspace)
    meta["status"].setdefault(unit, "pending")
    meta["status"][unit] = status
    meta[f"{unit}_at"] = datetime.now(timezone.utc).isoformat()
    if error: meta.setdefault("errors", {})[unit] = str(error)[:500]
    elif status == "done": meta.get("errors", {}).pop(unit, None)
    save_meta(workspace, meta)

def mark_subtask(workspace: Path, unit: str, subtask: str, status: str) -> None:
    meta = load_meta(workspace)
    meta.setdefault("subtasks", {}).setdefault(unit, {})[subtask] = status
    save_meta(workspace, meta)

def verify_unit_done(unit: str, workspace: Path) -> bool:
    return load_meta(workspace).get("status", {}).get(unit) == "done"

def should_skip(workspace: Path, unit: str, force: bool = False, inputs=None) -> bool:
    return False if force else verify_unit_done(unit, workspace)

def show_status(workspace: Path) -> None:
    meta = load_meta(workspace)
    logger.info(f"Status: {workspace.name} — {len(meta.get('status',{}))} units")

def verify_subtask_done(workspace: Path, unit: str, subtask: str) -> bool:
    return load_meta(workspace).get("subtasks", {}).get(unit, {}).get(subtask) == "done"

def verify_dubbing_stage(workspace: Path, stage: str) -> bool:
    return verify_subtask_done(workspace, "Unit-Dubbing", stage)

def update_status(workspace, unit, status, error=None):
    mark_unit(workspace, unit, status, error=error)
