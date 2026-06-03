"""
llm_circuit.py — Circuit Breaker for LLM providers

Tracks per-model failure counts in.runtime/cache/llm_circuit.json.

State machine per model:
  CLOSED → model is healthy, use normally
  OPEN → model failed too many times, skip until cooldown expires
  RECOVER → cooldown expired, allow one attempt (auto-closes on success)

This file has NO dependency on CrewAI or any agent framework.
It only reads/writes a small JSON file and checks timestamps.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import PATHS

logger = logging.getLogger(__name__)

# Where circuit state is persisted between runs
CIRCUIT_FILE: Path = PATHS["cache"] / "llm_circuit.json"

# Action log directory (same as executor)
LOG_DIR = PATHS["logs"] / "llm"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def _log_circuit(action: str, model: str, details: dict = None):
    """Write circuit event to.runtime/logs/llm/"""
    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_model = model.replace("/", "_").replace(":", "_")
        log_file = LOG_DIR / f"{ts}_circuit_{action}_{safe_model}.json"
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action, # "open", "close", "failure", "success", "check"
            "model": model,
            "details": details or {}
        }
        log_file.write_text(json.dumps(payload, indent=2))
    except Exception as e:
        logger.error(f"Failed to write circuit log: {e}")

# ── Internal helpers ──────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)

def _load() -> dict:
    """Read circuit state. Returns {} if file missing or corrupt."""
    try:
        return json.loads(CIRCUIT_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save(state: dict) -> None:
    CIRCUIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CIRCUIT_FILE.write_text(json.dumps(state, indent=2))

def _blank_entry() -> dict:
    return {"failures": 0, "last_failure": None, "open_until": None}

# ── Public API ────────────────────────────────────────────────────────────────

def is_open(model: str, cooldown_seconds: int = 300) -> bool:
    """
    Returns True if this model's circuit is OPEN (should be skipped).

    Side effect: auto-closes expired circuits so recovery is seamless —
    the next call after cooldown passes will return False and allow a retry.
    """
    state = _load()
    entry = state.get(model)

    # No record at all → circuit is closed → model is available
    if not entry or not entry.get("open_until"):
        _log_circuit("check", model, {"status": "closed"})
        return False

    open_until = datetime.fromisoformat(entry["open_until"])

    if _now() >= open_until:
        # Cooldown expired → close the circuit and reset failure count
        state[model] = _blank_entry()
        _save(state)
        logger.info(f"🔄 Circuit CLOSED (recovered): {model}")
        _log_circuit("close", model, {"reason": "cooldown_expired"})
        return False

    # Still within penalty window
    remaining = int((open_until - _now()).total_seconds() / 60)
    logger.debug(f"⚡ Circuit OPEN: {model} — {remaining}m remaining")
    _log_circuit("check", model, {"status": "open", "remaining_seconds": remaining*60})
    return True

def record_failure(model: str, cooldown_seconds: int = 300) -> None:
    """
    Increment failure count for this model.
    Opens the circuit (starts cooldown) once failure_threshold is reached.
    Called only for quota/rate/timeout errors — NOT for auth or logic errors.
    """
    state = _load()
    entry = state.get(model, _blank_entry())

    entry["failures"] += 1
    entry["last_failure"] = _now().isoformat()

    # Open the circuit after the first failure so we don't hammer a dead provider.
    # The cooldown gives the quota time to partially refresh.
    open_until = (_now() + timedelta(seconds=cooldown_seconds)).isoformat()
    entry["open_until"] = open_until

    state[model] = entry
    _save(state)
    logger.warning(
        f"⚡ Circuit recorded failure #{entry['failures']} for {model}. "
        f"Cooling down for {cooldown_seconds}s."
    )
    _log_circuit("failure", model, {
        "failures": entry["failures"],
        "open_until": open_until,
        "cooldown_seconds": cooldown_seconds
    })

def record_success(model: str) -> None:
    """
    Reset failure count on a successful call.
    Keeps the circuit closed for healthy models.
    """
    state = _load()
    if model in state and state[model].get("failures", 0) > 0:
        logger.info(f"✅ Circuit RESET (success): {model}")
        _log_circuit("success", model, {"previous_failures": state[model]["failures"]})
    state[model] = _blank_entry()
    _save(state)

def circuit_status() -> dict:
    """
    Returns a human-readable snapshot of all circuit states.
    Useful for FlowController to log into meta.json under 'llm_circuit'.
    """
    state = _load()
    result = {}
    for model, entry in state.items():
        if entry.get("open_until"):
            open_until = datetime.fromisoformat(entry["open_until"])
            remaining = max(0, int((open_until - _now()).total_seconds()))
            result[model] = f"OPEN — {remaining}s remaining"
        else:
            result[model] = "CLOSED"
    return result
