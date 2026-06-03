"""
llm_resolver.py — LLM Config Resolver with Automatic Fallback
Single-point gate: all LLM decisions happen here, never in agents.

Rules:
    1. WHAT model to use (resolved here, from llm_conf.json)
    2. HOW to call it (done in llm_executor.py)
    3. Policy (allowed agents, Unit-Data flag) is read from config — no static code
    4. Never raise on policy blocks — always return a safe local fallback so flow continues
    5. Emergency escalation: Unit-Data=true triggers premium cloud models (bypassing ollama-only)
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from cf2.core.llm_circuit import is_open
from config import PATHS

logger = logging.getLogger(__name__)

# Action log directory
LOG_DIR = PATHS["logs"] / "llm"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def _log_resolve(agent_name: str, tier_name: str, model: str, reason: str):
    """Write resolver decision to .runtime/logs/llm/"""
    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_model = model.replace("/", "_").replace(":", "_")
        log_file = LOG_DIR / f"{ts}_resolve_{agent_name}_{safe_model}.json"
        payload = {
            "timestamp": datetime.now().isoformat(),
            "agent": agent_name,
            "tier": tier_name,
            "model": model,
            "reason": reason
        }
        log_file.write_text(json.dumps(payload, indent=2))
    except Exception as e:
        logger.error(f"Failed to write resolver log: {e}")

# ── Config loader ─────────────────────────────────────────────────────────────

def load_llm_config(inputs: dict) -> dict:
    """
    Load llm_config from inputs["llmconf"] or inline inputs["llm_config"]
    """
    llmconf_path = inputs.get("llmconf")
    if llmconf_path:
        path = Path(llmconf_path)
        if not path.is_absolute():
            from config import PATHS
            path = PATHS["root"] / llmconf_path
        try:
            raw = json.loads(path.read_text())
            return raw.get("llm_config", raw)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Cannot load llm_conf from '{llmconf_path}': {exc}")

    llm_cfg = inputs.get("llm_config")
    if llm_cfg:
        return llm_cfg

    raise RuntimeError("No LLM config found. Set 'llmconf' path or embed 'llm_config' in inputs.")

# ── Core resolver ─────────────────────────────────────────────────────────────

def resolve_llm(agent_name: str, inputs: dict) -> dict:
    """
    SINGLE-POINT LLM GATE
    - All policy lives in llm_conf.json → access_control
    - Never raises — always returns a safe fallback so flow continues
    - Logs only for enabled units (keeps pcf logs readable)
    - Emergency escalation when Unit-Data=true (highest priority)
    """
    # 1. Load LLM config from inputs (file or inline)
    try:
        llm_cfg = load_llm_config(inputs)
    except Exception as exc:
        logger.error(f"1. Config load failed: {exc}")
        return {"model": "ollama/deepseek-r1:1.5b", "temperature": 0.5, "max_tokens": 512}

    # 2. Read policy from config (no hardcoded values)
    ac = llm_cfg.get("access_control", {})
    UNIT_DATA_ONLY = ac.get("unit_data_only", False)
    ALLOWED_AGENTS = set(ac.get("allowed_agents", []))
    LOCAL_FALLBACK = ac.get("local_fallback", "ollama/deepseek-r1:1.5b")
    FORCE_LOCAL = ac.get("force_local_when_disabled", True)
    ENFORCE_OLLAMA = ac.get("enforce_ollama_only", False)

    # Emergency Escalation Settings
    EMERGENCY_TIER_NAME = ac.get("emergency_tier", None)
    EMERGENCY_BYPASS_OLLAMA = ac.get("emergency_bypass_ollama_only", True)

    # 3. Map each agent to its owning unit (for quiet logging)
    AGENT_UNIT = {
        "data_researcher": "Unit-Data", "csv_generator": "Unit-Data",
        "definition_specialist": "Unit-Data", "data_comparison_specialist": "Unit-Data",
        "debater": "Unit-Debate", "judge": "Unit-Debate",
        "debater_m": "Unit-Debate", "judge_m": "Unit-Debate", "score_analyst": "Unit-Debate",
        "scout": "Unit-Scout",
        "prodcast_scriptwriter": "Unit-Prodcast",
        "video_producer": "Unit-Animation", "audio_engineer": "Unit-Animation",
        "classroom_script_writer": "Unit-Classroom"
    }

    # 4. Choose log level: INFO for enabled units, DEBUG for disabled (keeps logs clean)
    unit_name = AGENT_UNIT.get(agent_name, "")
    unit_enabled = inputs.get(unit_name, True) if unit_name else True
    log = logger.info if unit_enabled else logger.debug

    # 5. Get circuit-breaker settings
    cb_cfg = llm_cfg.get("circuit_breaker", {})
    cooldown = cb_cfg.get("cooldown_seconds", 300)
    unit_data_enabled = inputs.get("Unit-Data", False)
    data_llm_enabled = inputs.get("data_llm_enabled", False)

    # Log the initial state for this agent
    log(f"--- Resolving LLM for '{agent_name}' ---")
    log(f"State: Unit-Data={unit_data_enabled}, data_llm={data_llm_enabled}, FORCE_LOCAL={FORCE_LOCAL}, ENFORCE_OLLAMA={ENFORCE_OLLAMA}")

    # 6. GATE 1 — Whitelist check (Unit-Data only mode)
    if UNIT_DATA_ONLY and ALLOWED_AGENTS and agent_name not in ALLOWED_AGENTS:
        log(f"6. GATE 1 BLOCKED: '{agent_name}' not in allowed_agents → {LOCAL_FALLBACK}")
        _log_resolve(agent_name, "blocked", LOCAL_FALLBACK, "not_allowed")
        return {"model": LOCAL_FALLBACK, "temperature": 0.3, "max_tokens": 256}

    # 7. GATE 2 — Unit-Data master switch (if OFF, force local)
    if not unit_data_enabled or not data_llm_enabled:
        if FORCE_LOCAL:
            log(f"7. GATE 2 BLOCKED: Unit-Data/Data_LLM OFF & FORCE_LOCAL=True → Returning safe fallback: {LOCAL_FALLBACK}")
            _log_resolve(agent_name, "forced_local", LOCAL_FALLBACK, "unit_data_disabled_forced")
            return {"model": LOCAL_FALLBACK, "temperature": 0.5, "max_tokens": 512}
        else:
            log(f"7. GATE 2 PASSED: Unit-Data/Data_LLM OFF, but FORCE_LOCAL=False → Allowing tier resolution to continue")
            _log_resolve(agent_name, "skipped_force_local", "none", "unit_data_disabled_but_not_forced")

    # ══════════════════════════════════════════════════════════════════════════
    # 7.5 GATE 2.5 — EMERGENCY ESCALATION (Unit-Data = true = highest priority)
    # ══════════════════════════════════════════════════════════════════════════
    if not unit_data_enabled:
        log(f"7.5. EMERGENCY CHECK: Skipping emergency tier for '{agent_name}' because Unit-Data is OFF.")
    elif unit_data_enabled and EMERGENCY_TIER_NAME:
        log(f"7.5. EMERGENCY CHECK: Unit-Data is ON. Checking emergency tier '{EMERGENCY_TIER_NAME}'...")
        emergency_tier = llm_cfg.get("tiers", {}).get(EMERGENCY_TIER_NAME)
        if emergency_tier:
            e_models = emergency_tier.get("models", [])
            e_temperature = emergency_tier.get("temperature", 0.3)
            e_max_tokens = emergency_tier.get("max_tokens", 8192)

            # During emergency: bypass enforce_ollama_only to reach cloud models
            if EMERGENCY_BYPASS_OLLAMA:
                e_models_filtered = e_models  # Allow all models
                log(f"7.5. EMERGENCY BYPASS: Allowing all models (including cloud) for emergency.")
            else:
                e_models_filtered = [m for m in e_models if m.startswith("ollama/")]

            for model in e_models_filtered:
                if is_open(model, cooldown_seconds=cooldown):
                    log(f"7.5. Skipping {model} (circuit open, emergency tier)")
                    _log_resolve(agent_name, EMERGENCY_TIER_NAME, model, "skipped_emergency_circuit_open")
                    continue

                log(f"7.5. EMERGENCY SELECTED: '{agent_name}' escalated → {model}")
                _log_resolve(agent_name, EMERGENCY_TIER_NAME, model, "emergency_escalation")
                return {"model": model, "temperature": e_temperature, "max_tokens": e_max_tokens}

            # All emergency models down — fall through to normal tier
            logger.warning(f"7.5. Emergency tier '{EMERGENCY_TIER_NAME}' all down → falling back to normal tier")
        else:
            logger.warning(f"7.5. Emergency tier '{EMERGENCY_TIER_NAME}' not found in config → falling back to normal tier")
    # ══════════════════════════════════════════════════════════════════════════

    # 8. Resolve agent → tier (normal resolution)
    agent_entry = llm_cfg.get("agents", {}).get(agent_name)
    if not agent_entry:
        log(f"8. Agent '{agent_name}' not in config → using default")
        model = llm_cfg.get("default", LOCAL_FALLBACK)
        _log_resolve(agent_name, "default", model, "agent_not_found")
        return {"model": model, "temperature": 0.5, "max_tokens": 4096}

    tier_name = agent_entry.get("tier", "research")
    log(f"8. Agent '{agent_name}' assigned to tier: '{tier_name}'")

    tier = llm_cfg.get("tiers", {}).get(tier_name)

    # 9. Validate tier exists
    if not tier:
        logger.error(f"9. Tier '{tier_name}' missing → fallback")
        _log_resolve(agent_name, tier_name, LOCAL_FALLBACK, "tier_missing")
        return {"model": LOCAL_FALLBACK, "temperature": 0.5, "max_tokens": 512}

    models = tier.get("models", [])
    temperature = tier.get("temperature", 0.7)
    max_tokens = tier.get("max_tokens", 4096)
    log(f"9. Tier '{tier_name}' available models: {models}")

    # 10. Enforce Ollama-only if configured (normal mode)
    if ENFORCE_OLLAMA:
        original_count = len(models)
        models = [m for m in models if m.startswith("ollama/")]
        if len(models) < original_count:
            log(f"10. ENFORCE_OLLAMA=True: Filtered out {original_count - len(models)} non-Ollama models. Remaining: {models}")
        if not models:
            log(f"10. ENFORCE_OLLAMA=True: No models left after filter, using LOCAL_FALLBACK")
            models = [LOCAL_FALLBACK]

    # 11. Walk the fallback chain, skip open circuits
    for model in models:
        if is_open(model, cooldown_seconds=cooldown):
            log(f"11. Skipping {model} (circuit open)")
            _log_resolve(agent_name, tier_name, model, "skipped_circuit_open")
            continue

        # 12. Success — return first healthy model
        log(f"12. RESOLVED: '{agent_name}' → {model}")
        _log_resolve(agent_name, tier_name, model, "selected")
        return {"model": model, "temperature": temperature, "max_tokens": max_tokens}

    # 13. All models failed — final graceful fallback
    logger.error(f"13. All models down for '{agent_name}' → {LOCAL_FALLBACK}")
    _log_resolve(agent_name, tier_name, LOCAL_FALLBACK, "all_unavailable")
    return {"model": LOCAL_FALLBACK, "temperature": 0.3, "max_tokens": 256}

def resolve_model_chain(agent_name: str, inputs: dict) -> list[str]:
    """
    Returns the full ordered model list for an agent's tier,
    regardless of circuit state. Useful for logging and diagnostics.
    """
    llm_cfg = load_llm_config(inputs)
    agent_entry = llm_cfg.get("agents", {}).get(agent_name, {})
    tier_name = agent_entry.get("tier", "research")
    tier = llm_cfg.get("tiers", {}).get(tier_name, {})
    return tier.get("models", [llm_cfg.get("default")])
