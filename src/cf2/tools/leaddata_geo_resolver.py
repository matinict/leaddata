"""
leaddata_geo_resolver.py — Dynamic Global Context Resolver Utility
"""
from typing import Dict

GLOBAL_REGION_MAP = {
    "usa": {"prefix": "+1", "code": "US", "hl": "en"},
    "united states": {"prefix": "+1", "code": "US", "hl": "en"},
    "canada": {"prefix": "+1", "code": "CA", "hl": "en"},
    "ontario": {"prefix": "+1", "code": "CA", "hl": "en"}, # Added for your specific topic
    "mexico": {"prefix": "+52", "code": "MX", "hl": "es"},
    "uk": {"prefix": "+44", "code": "GB", "hl": "en"},
    "united kingdom": {"prefix": "+44", "code": "GB", "hl": "en"},
    "france": {"prefix": "+33", "code": "FR", "hl": "fr"},
    "germany": {"prefix": "+49", "code": "DE", "hl": "de"},
    "australia": {"prefix": "+61", "code": "AU", "hl": "en"},
    "india": {"prefix": "+91", "code": "IN", "hl": "en"},
}

def resolve_global_context(topic: str, config: dict) -> Dict[str, str]:
    topic_lower = topic.lower()
    for key, meta in GLOBAL_REGION_MAP.items():
        if key in topic_lower:
            return meta

    explicit_prefix = config.get("collect_config", {}).get("maps_config", {}).get("phone_country_prefix")
    explicit_code = config.get("normalize_config", {}).get("phone_country_default")
    explicit_hl = config.get("collect_config", {}).get("hl")

    if explicit_prefix or explicit_code:
        return {"prefix": explicit_prefix or "+1", "code": explicit_code or "US", "hl": explicit_hl or "en"}

    return {"prefix": "+1", "code": "US", "hl": "en"}
