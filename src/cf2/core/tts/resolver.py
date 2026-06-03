"""
cf2/core/tts/resolver.py
Provider-agnostic resolver: tier → provider chain → retry → circuit breaker.
ZERO provider-specific code. Providers loaded dynamically from config.module.
"""
import json
import time
import logging
import importlib
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from threading import Lock

logger = logging.getLogger(__name__)

# ── Process-wide state ────────────────────────────────────────────────────────
_circuit_state: Dict[str, Dict[str, Any]] = {}
_circuit_lock  = Lock()
_provider_cache: Dict[str, Any] = {}
_conf_cache: Optional[dict] = None


# ── Config ────────────────────────────────────────────────────────────────────

def load_conf(force_reload: bool = False) -> dict:
    global _conf_cache
    if _conf_cache and not force_reload:
        return _conf_cache
    p = Path("input/tts_conf.json")
    if not p.exists():
        return {}
    try:
        _conf_cache = json.loads(p.read_text("utf-8")).get("tts_config", {})
    except Exception as exc:
        logger.warning(f"[TTS] Failed to load tts_conf.json: {exc}")
        _conf_cache = {}
    return _conf_cache


# ── Tier / voice resolution (pure config lookup) ──────────────────────────────

def resolve_tier_for_unit(unit_name: str, conf: dict = None) -> str:
    conf = conf or load_conf()
    return conf.get("unit_tier_mapping", {}).get(
        unit_name, conf.get("default_tier", "narration")
    )


def resolve_voice(tier: str, speaker_tag: str, provider: str, conf: dict = None) -> str:
    conf     = conf or load_conf()
    tier_cfg = conf.get("tiers", {}).get(tier, {})
    voices   = tier_cfg.get("voices", {})

    voice = voices.get(speaker_tag) or voices.get("default")
    if not voice:
        voice = next(iter(voices.values()), "en-US-JennyNeural") if voices else "en-US-JennyNeural"

    if provider != "edge":
        fb_map = tier_cfg.get("fallback_voices", {}).get(f"edge_to_{provider}", {})
        voice = fb_map.get(speaker_tag) or fb_map.get("*") or voice
    return voice


# ── Dynamic provider loading ──────────────────────────────────────────────────

def _load_provider(name: str, conf: dict):
    """Lazy-load a provider class by importing config.module."""
    if name in _provider_cache:
        return _provider_cache[name]

    p_cfg = conf.get("providers", {}).get(name)
    if not p_cfg or "module" not in p_cfg:
        return None

    try:
        mod = importlib.import_module(p_cfg["module"])
        provider_cls = getattr(mod, "Provider", None)
        if not provider_cls:
            return None
        _provider_cache[name] = provider_cls(p_cfg)
        return _provider_cache[name]
    except Exception as exc:
        logger.warning(f"[TTS] Could not load provider '{name}': {exc}")
        return None


# ── Circuit breaker ───────────────────────────────────────────────────────────

def _circuit_open(provider: str) -> bool:
    with _circuit_lock:
        st = _circuit_state.get(provider, {"failures": 0, "open_until": 0})
        if st["open_until"] > time.time():
            return True
        if st["open_until"] and st["open_until"] <= time.time():
            _circuit_state[provider] = {"failures": 0, "open_until": 0}
        return False


def _record_success(provider: str) -> None:
    with _circuit_lock:
        _circuit_state[provider] = {"failures": 0, "open_until": 0}


def _record_failure(provider: str, conf: dict) -> None:
    cb = conf.get("circuit_breaker", {})
    threshold = cb.get("failure_threshold", 3)
    cooldown  = cb.get("cooldown_seconds", 300)
    with _circuit_lock:
        st = _circuit_state.setdefault(provider, {"failures": 0, "open_until": 0})
        st["failures"] += 1
        if st["failures"] >= threshold:
            st["open_until"] = time.time() + cooldown
            logger.warning(f"[TTS] Circuit OPEN for '{provider}' — cooldown {cooldown}s")


# ── Public entry point ────────────────────────────────────────────────────────

def synthesize(
    text:        str,
    output_path: str,
    tier:        Optional[str] = None,
    speaker_tag: Optional[str] = None,
    unit:        Optional[str] = None,
    logger_fn=None,
) -> Tuple[bool, str]:
    """
    Synthesize text to audio file via dynamic provider chain.
    Returns (success, provider_used | "silent_fallback").
    """
    log  = logger_fn or logger.info
    conf = load_conf()

    if not conf:
        return _silent_fallback(text, output_path, conf, log), "silent_fallback"

    tier = tier or (resolve_tier_for_unit(unit, conf) if unit else conf.get("default_tier", "narration"))
    speaker_tag = speaker_tag or "default"

    tier_cfg  = conf.get("tiers", {}).get(tier, {})
    if not tier_cfg:
        log(f"⚠️  Tier '{tier}' not found — silent fallback")
        return _silent_fallback(text, output_path, conf, log), "silent_fallback"

    providers = tier_cfg.get("providers", [])
    retry_cfg = conf.get("retry", {})
    max_att   = retry_cfg.get("max_attempts", 3)
    backoff   = retry_cfg.get("backoff_seconds", [1, 2, 4])

    for provider_name in providers:
        if _circuit_open(provider_name):
            log(f"⏭️  '{provider_name}' circuit open — skipping")
            continue

        provider = _load_provider(provider_name, conf)
        if not provider or not provider.is_available():
            log(f"⏭️  '{provider_name}' unavailable — skipping")
            continue

        voice = resolve_voice(tier, speaker_tag, provider_name, conf)

        for attempt in range(max_att):
            try:
                if provider.synthesize(text, output_path, voice):
                    _record_success(provider_name)
                    return True, provider_name
            except Exception as exc:
                log(f"⚠️  '{provider_name}' attempt {attempt+1} failed: {exc}")

            if attempt < max_att - 1:
                time.sleep(backoff[min(attempt, len(backoff) - 1)])

        _record_failure(provider_name, conf)
        log(f"❌ '{provider_name}' exhausted — trying next")

    return _silent_fallback(text, output_path, conf, log), "silent_fallback"


# ── Silent fallback ───────────────────────────────────────────────────────────

def _silent_fallback(text: str, output_path: str, conf: dict, log) -> bool:
    sf = (conf or {}).get("silent_fallback", {
        "enabled": True, "words_per_second": 2.5,
        "min_duration": 1.0, "max_duration": 6.0,
    })
    if not sf.get("enabled", True):
        return False

    wps = sf.get("words_per_second", 2.5)
    mn  = sf.get("min_duration", 1.0)
    mx  = sf.get("max_duration", 6.0)
    dur = max(mn, min(len(text.split()) / wps, mx))

    try:
        from cf2.core.services.ffmpeg_service import FFmpegService
        FFmpegService().create_silent_mp3(output_path, duration=dur)
        log(f"🔇 Silent fallback ({dur:.1f}s): {Path(output_path).name}")
        return True
    except Exception as exc:
        log(f"❌ Silent fallback failed: {exc}")
        return False
