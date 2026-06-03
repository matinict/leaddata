"""
dependency_resolver.py — Dependency Manager
Rule D-3: Unit-Data auto-triggers when consumers need missing inputs.
Rule 19: Paths resolved via workspace/Path.
Rule 28/29: No hardcoded unit names. Deps loaded from config.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from cf2.core.registry import is_unit_available, get_available_units
from config import PATHS

logger = logging.getLogger(__name__)

# ── Load dependencies dynamically ────────────────────────────────────────
def _load_deps() -> Dict[str, Tuple[str, List[str]]]:
    """
    Load UNIT_DEPS from input/unit_deps.json
    Format: {"Unit-Debate": {"producer": "Unit-Data", "files": [...]}}
    """
    deps_path = Path(PATHS["input"]) / "unit_deps.json"

    if not deps_path.exists():
        # Rule 29: observable fallback — create default
        logger.warning(f"CONFIG FALLBACK: {deps_path.name} missing, using defaults")
        default = {
            "Unit-Debate": {
                "producer": "Unit-Data",
                "files": ["debate/propose.md", "debate/oppose.md", "debate/decide.md"]
            },
            "Unit-Animation": {
                "producer": "Unit-Data",
                "files": ["animation/data.csv"]
            },
            "Unit-Definition": {
                "producer": "Unit-Data",
                "files": ["definition/def_En.txt"]
            },
            "Unit-Comparison": {
                "producer": "Unit-Data",
                "files": ["debate/propose.md"]
            }
            # Unit-Prodcast intentionally omitted — self-contained
        }
        try:
            deps_path.write_text(json.dumps(default, indent=2), encoding="utf-8")
            logger.info(f"Created default {deps_path}")
        except Exception:
            pass
        deps_data = default
    else:
        try:
            deps_data = json.loads(deps_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed to load {deps_path}: {e}")
            return {}

    # Validate against registry
    validated = {}
    available = get_available_units()

    for consumer, spec in deps_data.items():
        producer = spec.get("producer")
        files = spec.get("files", [])

        if consumer not in available:
            logger.debug(f"Deps: {consumer} not available, skipping")
            continue
        if producer not in available:
            logger.debug(f"Deps: {producer} not available for {consumer}, skipping")
            continue

        validated[consumer] = (producer, files)
        logger.debug(f"Deps: {consumer} → {producer} ({len(files)} files)")

    return validated

# Load once
UNIT_DEPS = _load_deps()

def is_enabled(unit: str, inputs: dict) -> bool:
    """
    Check if unit is enabled.
    Rule 28: Must be available AND explicitly enabled.
    """
    if not is_unit_available(unit):
        return False
    return bool(inputs.get(unit, False))

def resolve_deps(unit: str, topic: str, workspace: Path, inputs: dict, force: bool) -> None:
    """
    Auto-run producer if consumer needs missing files.
    """
    if unit not in UNIT_DEPS:
        return

    if not is_enabled(unit, inputs):
        return

    dep_unit, files = UNIT_DEPS[unit]

    if not is_unit_available(dep_unit):
        logger.warning(f"Cannot auto-run {dep_unit} for {unit} — not available")
        return

    missing = [f for f in files if not (workspace / f).exists()]

    if not missing:
        return

    if not is_enabled(dep_unit, inputs):
        logger.info(f"{unit} needs {dep_unit} but {dep_unit} not enabled")
        return

    print(f"\n ⚡ {unit} needs {dep_unit} — missing: {missing}\n")
    logger.info(f"Auto-triggering {dep_unit} for {unit}")

    from cf2.core.executor import run_unit_internal
    run_unit_internal(dep_unit, topic, workspace, inputs, force=False)

def reload_deps():
    """Force reload (for testing)."""
    global UNIT_DEPS
    UNIT_DEPS = _load_deps()
