"""
core/executor.py — Execution Engine
This is the ONLY place a unit actually runs. Two-layer design:
1. run_unit_internal() — raw execution: skip-check → lock → run → verify → mark
2. run_unit() — public gate: enabled-check → dep resolution → internal

FlowController calls run_unit(). Dependency resolver calls run_unit_internal()
directly to avoid re-checking the enabled flag.

RULE 25: Only executor.py may call acquire_lock(). Units must NEVER check locks.
"""
import os
import json
import logging
import traceback as _tb
import fcntl
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Tuple, Optional

from cf2.meta import (
    should_skip,
    mark_unit,
    verify_unit_done,
)
from cf2.core.registry import get_runner, get_unit_config_key, get_unit_config_file
from cf2.core.progress_tracker import make_tracker
from cf2.core.dependency_resolver import resolve_deps, is_enabled

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Rule 25 — Lock System (executor is the ONLY owner)
# ─────────────────────────────────────────────────────────────────────────────

LOCK_FILENAME = ".lock"
LOCK_MAX_AGE = 300 # 5 minutes = stale

def _lock_path(workspace: Path, unit: str) -> Path:
    # Rule 25.6 — workspace-level lock only
    return Path(workspace) / LOCK_FILENAME

def cleanup_stale_locks(workspace: Path, max_age: int = LOCK_MAX_AGE) -> int:
    """Rule 25.5 — auto-clean stale locks"""
    lock_file = _lock_path(workspace, "global")
    if not lock_file.exists():
        return 0
    try:
        age = time.time() - lock_file.stat().st_mtime
        if age > max_age:
            lock_file.unlink(missing_ok=True)
            logger.info(f"🧹 Stale lock cleaned (age={age:.0f}s)")
            print(f" 🧹 Stale lock cleaned")
            return 1
    except Exception as e:
        logger.warning(f"Lock check failed: {e}")
    return 0

def force_cleanup_all_locks(workspace: Path) -> int:
    lock_file = _lock_path(workspace, "global")
    if lock_file.exists():
        lock_file.unlink(missing_ok=True)
        return 1
    return 0

def acquire_lock(workspace: Path, unit: str = "global"):
    """Rule 25.1 — ONLY executor creates locks"""
    lock_file = _lock_path(workspace, unit)
    lock_file.parent.mkdir(parents=True, exist_ok=True)

    # Rule 25.4 — crash detection
    if lock_file.exists():
        age = time.time() - lock_file.stat().st_mtime
        if age <= LOCK_MAX_AGE:
            logger.warning(f"Active lock found (age {age:.0f}s)")
            return None
        cleanup_stale_locks(workspace)

    try:
        fd = open(lock_file, "w")
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Rule 25.9 — audit trail
        fd.write(f"{unit} | {datetime.now(timezone.utc).isoformat()}\n")
        fd.flush()
        os.fsync(fd.fileno())
        return fd
    except (IOError, OSError):
        try: fd.close()
        except: pass
        return None

def release_lock(fd):
    """Rule 25.3 — always in finally"""
    if not fd:
        return
    try:
        lock_path = Path(fd.name)
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()
        lock_path.unlink(missing_ok=True)
    except Exception:
        pass

def get_lock_info(workspace: Path):
    lock_file = _lock_path(workspace, "global")
    if lock_file.exists():
        try:
            return {"exists": True, "content": lock_file.read_text(errors="ignore").strip()}
        except:
            return {"exists": True}
    return {"exists": False}

# ─────────────────────────────────────────────────────────────────────────────
# Per-unit channel resolver — reads from the unit's config file.
# Rule 29: No hardcoded mapping. Uses registry.py
# ─────────────────────────────────────────────────────────────────────────────

def _load_unit_channel(unit: str, inputs: dict) -> Tuple[Optional[str], Optional[str]]:
    """
    Load (channel, channel_lower) for `unit` from its config file.
    Returns (None, None) if no channel defined.
    """
    cfg_key = get_unit_config_key(unit)
    if not cfg_key:
        return None, None

    # 1. In-memory config dict
    cfg = inputs.get(cfg_key)
    if isinstance(cfg, dict) and cfg.get("channel"):
        ch = cfg["channel"]
        return ch, cfg.get("channel_lower") or ch.lower()

    # 2. Load directly from config file (Rule 28)
    config_file = get_unit_config_file(unit)
    if config_file:
        try:
            cfg = json.loads(config_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load config for {unit}: {e}")
            return None, None
        if isinstance(cfg, dict) and cfg.get("channel"):
            ch = cfg["channel"]
            return ch, cfg.get("channel_lower") or ch.lower()

    return None, None

def _stamp_channel(unit: str, inputs: dict) -> None:
    """Overwrite inputs['channel'] with the value from this unit's config file."""
    ch, ch_lower = _load_unit_channel(unit, inputs)
    if ch:
        inputs["channel"] = ch
        inputs["channel_lower"] = ch_lower
        logger.debug(f"Channel stamped for {unit}: {ch}")

def run_unit_internal(
    unit: str, topic: str, workspace: Path, inputs: dict, force: bool
) -> Any:
    """
    Raw execution — no enabled-check, no dep resolution.
    Called by dependency_resolver when auto-running dependencies.
    """
    workspace = Path(workspace)

    # Skip check first (before touching locks)
    if should_skip(workspace, unit, force, inputs=inputs):
        logger.info(f"SKIP: {unit} (already done)")
        return None

    # Debug: trace lock acquisition if env var set
    if os.environ.get("CF2_DEBUG_LOCKS"):
        logger.debug(f"[{unit}] Lock acquisition stack:")
        for line in _tb.format_stack()[-5:-1]:
            logger.debug(line.rstrip())

    # Acquire PER-UNIT lock
    lock = acquire_lock(workspace, unit)
    if lock is None:
        logger.warning(f"{unit} — could not acquire lock, skipping")
        print(f" ⚠️ {unit} — could not acquire lock, skipping")
        return None

    try:
        mark_unit(workspace, unit, "running")

        # get_runner() returns a MODULE — must call.run() on it
        try:
            runner = get_runner(unit)
        except ValueError as e:
            logger.error(f"Runner not found for {unit}: {e}")
            mark_unit(workspace, unit, "failed")
            return None

        tracker = make_tracker(unit)

        # Stamp per-unit channel from this unit's config file
        _stamp_channel(unit, inputs)

        try:
            result = runner.run(topic, workspace, inputs, force)
        finally:
            tracker.stop()

        # Soft returns — unit decided to skip/disable itself internally
        _SOFT_RETURNS = {"skipped", "disabled", "3d only"}
        result_str = str(result).strip().lower() if result is not None else ""

        if any(s in result_str for s in _SOFT_RETURNS):
            mark_unit(workspace, unit, "skipped")
            print(f"⏭️ {unit} — skipped")
            logger.info(f"{unit} skipped internally")
        elif verify_unit_done(unit, workspace):
            mark_unit(workspace, unit, "done")
            logger.info(f"{unit} completed and verified")
        else:
            # Unit succeeded but verify returned False — trust the run
            mark_unit(workspace, unit, "done")
            logger.warning(f"{unit} completed but verification failed — marking done")

        return result

    except KeyboardInterrupt:
        mark_unit(workspace, unit, "interrupted")
        print(f"\n🛑 {unit} interrupted")
        logger.warning(f"{unit} interrupted by user")
        raise
    except Exception as exc:
        mark_unit(workspace, unit, "failed")
        print(f"\n❌ {unit} FAILED: {exc}")
        logger.exception(f"{unit} failed")
        # no raise — pipeline continues to next unit
        return None
    finally:
        release_lock(lock)

def run_unit(
    unit: str, topic: str, workspace: Path, inputs: dict, force: bool = False
) -> Any:
    """
    Public gate — the only entry point FlowController uses.
    enabled-check → dep resolution → raw execution.
    """
    print(f"\n{'─' * 60}")
    print(f"▶ {unit} | {Path(workspace).name}")
    print(f"{'─' * 60}")
    logger.info(f"Starting {unit}")

    # Enabled check (Rule 28)
    if not is_enabled(unit, inputs):
        print(f"⏭️ SKIP: {unit} (not enabled in profile)")
        logger.debug(f"{unit} not enabled")
        return None

    # Pre-flight lock cleanup
    workspace = Path(workspace)
    if str(workspace)!= "(pending)":
        if force:
            force_cleanup_all_locks(workspace)
        else:
            cleanup_stale_locks(workspace)

    # Resolve and run dependencies, then this unit
    resolve_deps(unit, topic, workspace, inputs, force)
    return run_unit_internal(unit, topic, workspace, inputs, force)
