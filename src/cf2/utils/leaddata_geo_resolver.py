"""
leaddata_geo_resolver.py — Dynamic Global Context Resolver Utility

Extracts regional context (phone prefix, country code, search language)
from topic strings to automate localized lead generation.
"""
from typing import Dict

# Global Region Map
# Maps common country names/codes to phone prefixes and SerpAPI 'hl' codes
GLOBAL_REGION_MAP = {
    # North America
    "usa": {"prefix": "+1", "code": "US", "hl": "en"},
    "united states": {"prefix": "+1", "code": "US", "hl": "en"},
    "canada": {"prefix": "+1", "code": "CA", "hl": "en"},
    "mexico": {"prefix": "+52", "code": "MX", "hl": "es"},
    # Europe
    "uk": {"prefix": "+44", "code": "GB", "hl": "en"},
    "united kingdom": {"prefix": "+44", "code": "GB", "hl": "en"},
    "england": {"prefix": "+44", "code": "GB", "hl": "en"},
    "france": {"prefix": "+33", "code": "FR", "hl": "fr"},
    "germany": {"prefix": "+49", "code": "DE", "hl": "de"},
    "spain": {"prefix": "+34", "code": "ES", "hl": "es"},
    "italy": {"prefix": "+39", "code": "IT", "hl": "it"},
    "netherlands": {"prefix": "+31", "code": "NL", "hl": "nl"},
    # Asia & Pacific
    "australia": {"prefix": "+61", "code": "AU", "hl": "en"},
    "india": {"prefix": "+91", "code": "IN", "hl": "en"},
    "japan": {"prefix": "+81", "code": "JP", "hl": "ja"},
    "china": {"prefix": "+86", "code": "CN", "hl": "zh-cn"},
    "singapore": {"prefix": "+65", "code": "SG", "hl": "en"},
    # Middle East & Africa
    "uae": {"prefix": "+971", "code": "AE", "hl": "ar"},
    "dubai": {"prefix": "+971", "code": "AE", "hl": "ar"},
    "south africa": {"prefix": "+27", "code": "ZA", "hl": "en"},
    # South America
    "brazil": {"prefix": "+55", "code": "BR", "hl": "pt-BR"},
    "argentina": {"prefix": "+54", "code": "AR", "hl": "es"},
}


def resolve_global_context(topic: str, config: dict) -> Dict[str, str]:
    """
    Scans the topic string for country/region hints.
    Falls back to explicit config, then safe international defaults.
    """
    topic_lower = topic.lower()

    # 1. Try to find a match in the topic string
    for key, meta in GLOBAL_REGION_MAP.items():
        if key in topic_lower:
            return meta

    # 2. Fallback to explicit config if provided by the user
    explicit_prefix = config.get("collect_config", {}).get("maps_config", {}).get("phone_country_prefix")
    explicit_code = config.get("normalize_config", {}).get("phone_country_default")
    explicit_hl = config.get("collect_config", {}).get("hl")

    if explicit_prefix or explicit_code:
        return {
            "prefix": explicit_prefix or "+1",
            "code": explicit_code or "US",
            "hl": explicit_hl or "en"
        }

    # 3. Ultimate safe defaults (International format, English language)
    return {"prefix": "+1", "code": "US", "hl": "en"}
