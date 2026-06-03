"""
cf2/core/tts/__init__.py
Public API — every unit imports from here.

Usage:
    from cf2.core.tts import synthesize
    synthesize(text, "out.mp3", unit="Unit-Classroom", speaker_tag="S1")
"""
from cf2.core.tts.resolver import (
    synthesize,
    resolve_tier_for_unit,
    resolve_voice,
    load_conf,
)

__all__ = ["synthesize", "resolve_tier_for_unit", "resolve_voice", "load_conf"]
