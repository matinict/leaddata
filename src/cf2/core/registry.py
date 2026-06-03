"""
src/cf2/core/registry.py
Unit registry — maps unit name to runner module.
Rule 28/29: NO hardcodes. Loaded from input/unit.json
"""
import importlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Internal cache ─────────────────────────────────────────────────────────
_REGISTRY: List[dict] = []
_AVAILABLE: Set[str] = set()
_MODULE_CACHE: Dict[str, object] = {}
_LOADED = False


def _load():
    """Load registry once from input/unit.json"""
    global _REGISTRY, _AVAILABLE, _LOADED
    if _LOADED:
        return

    reg_path = Path("input/unit.json")
    if not reg_path.exists():
        logger.error("❌ Rule 28: input/unit.json missing")
        _LOADED = True
        return

    try:
        data = json.loads(reg_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error(f"Failed to load registry: {e}")
        _LOADED = True
        return

    unit_dir = Path("input/unit")

    for u in sorted(data.get("units", []), key=lambda x: x.get("order", 999)):
        name = u["name"]
        cfg_file = unit_dir / u["file"]

        _REGISTRY.append(u)

        if cfg_file.exists():
            _AVAILABLE.add(name)
            logger.debug(f"✅ {name} available")
        else:
            logger.debug(f"⏭️ {name} skipped — {u['file']} missing")

    _LOADED = True


# ── Public API ─────────────────────────────────────────────────────────────

def get_runner(unit: str):
    """Return the module for the given unit name. Lazy import + cache."""
    if unit in _MODULE_CACHE:
        return _MODULE_CACHE[unit]

    _load()
    if unit not in _AVAILABLE:
        raise ValueError(
            f"Unknown/unavailable unit: '{unit}'. Available: {sorted(_AVAILABLE)}"
        )

    # "Unit-LeadData" → "cf2.units.unit_leaddata"
    module_name = "cf2.units." + unit.lower().replace("-", "_")

    try:
        module = importlib.import_module(module_name)
        _MODULE_CACHE[unit] = module
        return module
    except ImportError as e:
        raise ValueError(f"Failed to import '{module_name}' for {unit}: {e}")


def get_available_units() -> Set[str]:
    """Return set of unit names that have config files."""
    _load()
    return _AVAILABLE.copy()


def get_pipeline_order() -> List[str]:
    """Return ordered list of available units."""
    _load()
    return [u["name"] for u in _REGISTRY if u["name"] in _AVAILABLE]


def get_unit_config_key(unit: str) -> Optional[str]:
    """Get config key (e.g., 'Unit-Debate' → 'debate_config')."""
    _load()
    for u in _REGISTRY:
        if u["name"] == unit:
            return u.get("config_key")
    return None


def get_unit_config_file(unit: str) -> Optional[Path]:
    """Get path to unit's config file."""
    _load()
    unit_dir = Path("input/unit")
    for u in _REGISTRY:
        if u["name"] == unit:
            cfg = unit_dir / u["file"]
            return cfg if cfg.exists() else None
    return None


def is_unit_available(unit: str) -> bool:
    """Check if unit has config file."""
    _load()
    return unit in _AVAILABLE


def build_unit_flags(explicit_flags: Dict[str, bool] = None) -> Dict[str, bool]:
    """
    Build unit enable/disable flags.
    - Not available → False
    - Available, no flag → False (opt-in)
    - Available, flag=true → True
    """
    _load()
    explicit = explicit_flags or {}
    return {
        u["name"]: bool(explicit.get(u["name"], False)) if u["name"] in _AVAILABLE else False
        for u in _REGISTRY
    }


def invalidate_cache():
    """Force reload (for testing)."""
    global _REGISTRY, _AVAILABLE, _MODULE_CACHE, _LOADED
    _REGISTRY = []
    _AVAILABLE = set()
    _MODULE_CACHE = {}
    _LOADED = False
