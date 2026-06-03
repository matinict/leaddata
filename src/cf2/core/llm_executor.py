"""
cf2/core/llm_executor.py — Central LLM gateway with fallback + circuit breaker
Rule 14: All LLM calls must route through here.

Features:
- Automatic fallback across model tiers
- Circuit breaker (5-min cooldown on failure)
- Per-call JSON logs
- Live status summary (.runtime/cache/llm_status.json)
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from cf2.core.llm_circuit import is_open, record_failure, record_success
from cf2.core.llm_resolver import load_llm_config

logger = logging.getLogger(__name__)

PATHS = {
    "logs": Path(".runtime/logs/llm"),
    "cache": Path(".runtime/cache"),
}

def _ensure_paths() -> None:
    """Create runtime directories on first use instead of at import time."""
    for p in PATHS.values():
        p.mkdir(parents=True, exist_ok=True)

STATUS_FILE = PATHS["cache"] / "llm_status.json"

_FALLBACK_KEYWORDS = [
    "quota", "rate limit", "429", "too many requests",
    "timeout", "timed out", "connection error",
    "503", "service unavailable", "overloaded", "500",
    "internal server error", "temporarily unavailable",
]

# ─────────────────────────────────────────────────────────────────────────────
# Error classification for dashboard
# ─────────────────────────────────────────────────────────────────────────────

def _classify_error(msg: str) -> str:
    """Detect specific LLM issues from error text"""
    m = msg.lower()
    if any(k in m for k in ["payment", "billing", "insufficient funds", "past due", "invoice", "balance"]):
        return "payment_due"
    if any(k in m for k in ["quota", "usage limit", "credits", "exceeded your", "plan limit"]):
        return "quota_exceeded"
    if any(k in m for k in ["rate limit", "429", "too many requests"]):
        return "rate_limited"
    if any(k in m for k in ["401", "unauthorized", "invalid api key", "forbidden", "403", "api key"]):
        return "auth_error"
    if any(k in m for k in ["timeout", "timed out", "503", "overloaded", "unavailable", "500"]):
        return "overloaded"
    if any(k in m for k in ["model not found", "404", "not exist"]):
        return "model_error"
    return "error"

def should_fallback(exc: Exception) -> bool:
    """Return True if error is recoverable and we should try next model"""
    msg = str(exc).lower()
    return any(k in msg for k in _FALLBACK_KEYWORDS)

# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

def call_with_fallback(agent_name: str, inputs: dict, call_fn: Callable[[dict], Any]) -> Any:
    """
    Execute LLM call with automatic fallback.

    Args:
        agent_name: Name of agent (e.g., 'data_researcher')
        inputs: Full inputs dict (must contain llm_config)
        call_fn: Function that takes model config and returns result

    call_fn signature:
        def call_fn(cfg: dict) -> Any:
            # cfg contains: model, temperature, max_tokens
            # return result string or raise on failure

    Returns:
        Result from first successful model
    """
    _ensure_paths()

    llm_cfg = inputs.get("llm_config") or load_llm_config(inputs.get("llmconf"))
    agent_cfg = llm_cfg.get("agents", {}).get(agent_name, {})
    tier_name = agent_cfg.get("tier", "default")
    tier = llm_cfg.get("tiers", {}).get(tier_name, {})

    # Filter out None models and provide clear error if missing
    models = tier.get("models") or [llm_cfg.get("default")]
    models = [m for m in models if m]

    if not models:
        raise RuntimeError(
            f"No models configured for agent '{agent_name}' "
            f"and no default model set in llm_conf.json"
        )

    # FIX: Use nested .get() to preserve valid falsy values like 0
    temperature = agent_cfg.get("temperature", tier.get("temperature", 0.7))
    max_tokens = agent_cfg.get("max_tokens", tier.get("max_tokens", 4096))

    cooldown = llm_cfg.get("circuit_breaker", {}).get("cooldown_seconds", 300)

    # ── Cloud block when Unit-Data is OFF ─────────────────────────────────
    unit_data_enabled = inputs.get("Unit-Data", True)
    if not unit_data_enabled:
        original_count = len(models)
        models = [m for m in models if m.startswith("ollama/")]
        blocked = original_count - len(models)

        if blocked > 0:
            logger.info(f"🔒 Unit-Data OFF — blocked {blocked} cloud models")

        if not models:
            # FIX: Make fallback configurable instead of hardcoding
            local_fallback = llm_cfg.get("local_fallback", "ollama/deepseek-r1:1.5b")
            models = [local_fallback]
            logger.warning(f"🔒 Unit-Data OFF — no local models in tier, forcing {local_fallback}")

    last_error = None

    for model in models:
        if is_open(model):
            logger.debug(f"⏭️ [{agent_name}] Skipping {model} (circuit OPEN)")
            continue

        cfg = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        logger.info(f"🤖 [{agent_name}] Calling → {model}")

        try:
            result = call_fn(cfg)
            record_success(model)
            logger.info(f"✅ [{agent_name}] Success ← {model}")
            _write_action_log(agent_name, model, cfg, "success", result=result)
            _update_llm_summary(model, "success", result=result)
            return result

        except Exception as exc:
            last_error = exc

            if should_fallback(exc):
                logger.warning(f"⚡ [{agent_name}] Fallback from {model}: {exc}")
                record_failure(model, cooldown_seconds=cooldown)
                _write_action_log(agent_name, model, cfg, "fallback", error=exc)
                _update_llm_summary(model, "fallback", error=exc)
                continue
            else:
                logger.error(f"💀 [{agent_name}] Fatal error on {model}: {exc}")
                _write_action_log(agent_name, model, cfg, "fatal", error=exc)
                _update_llm_summary(model, "fatal", error=exc)
                raise

    # All models exhausted
    raise RuntimeError(f"All LLM models failed for {agent_name}. Last error: {last_error}")

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────

def _write_action_log(agent: str, model: str, cfg: dict, status: str, result: Any = None, error: Exception = None):
    """Write per-call JSON log"""
    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        unique_id = uuid.uuid4().hex[:8]
        safe_model = model.replace("/", "_").replace(":", "_")
        path = PATHS["logs"] / f"{ts}_{unique_id}_{status}_{safe_model}.json"

        data = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent,
            "model": model,
            "config": cfg,
            "status": status,
        }

        if error:
            data["error"] = str(error)[:500]
            data["error_type"] = _classify_error(str(error))

        if result is not None:
            data["result_preview"] = str(result)[:200]

        path.write_text(json.dumps(data, indent=2))
    except Exception as e:
        logger.error(f"Failed to write action log: {e}")

def _update_llm_summary(model: str, status: str, error: Exception = None, result: Any = None):
    """Update live status dashboard"""
    try:
        # Load existing
        summary = {}
        if STATUS_FILE.exists():
            try:
                summary = json.loads(STATUS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                summary = {}

        # Get circuit info
        circuit = {}
        try:
            from cf2.core.llm_circuit import get_circuit_state
            circuit = get_circuit_state(model)
        except ImportError:
            try:
                from cf2.core.llm_circuit import _load as _load_circuit
                circuit = _load_circuit().get(model, {})
            except Exception:
                pass
        except Exception:
            pass

        # Initialize or update entry
        entry = summary.get(model, {
            "success_count": 0,
            "failure_count": 0,
            "first_seen": datetime.now().isoformat()
        })

        entry.update({
            "last_call": datetime.now().isoformat(),
            "status": status,
            "circuit": "OPEN" if circuit.get("open_until") else "CLOSED",
            "open_until": circuit.get("open_until"),
            "last_error": str(error)[:200] if error else None,
            "error_type": _classify_error(str(error)) if error else None,
        })

        if status == "success":
            entry["success_count"] = entry.get("success_count", 0) + 1
            entry["last_success"] = datetime.now().isoformat()
            entry["error_type"] = None
            entry["last_error"] = None
        else:
            entry["failure_count"] = entry.get("failure_count", 0) + 1

        summary[model] = entry

        # FIX: Atomic write pattern to prevent race conditions
        tmp_path = STATUS_FILE.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        os.replace(tmp_path, STATUS_FILE)

    except Exception as e:
        logger.error(f"Failed to update LLM summary: {e}")
