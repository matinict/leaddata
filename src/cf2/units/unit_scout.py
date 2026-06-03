"""
unit_scout.py — Unit-Scout
Writes topic queue to .runtime/topics/{profile}/topic_memory.json

Config priority (highest → lowest):
  1. scout_config block in data.json   ← channel-specific scout settings
  2. audience_profiles.json[profile]   ← profile niches + scraping_url
  3. top-level data.json keys          ← global defaults
  4. _SCOUT_TASK_DEFAULTS              ← code-level fallback

Scraping URL resolution:
  1. scout_config["scraping_url_file"]
  2. profile_data["scraping_url"]
  3. data/scraping_url_{profile}.json  (naming convention probe)
  4. data/scraping_url.json            (global fallback — Rule 25)
"""
from pathlib import Path
from crewai import Crew
from cf2.crews.crew import CF2Crew
from cf2.core.paths import TOPICS_ROOT

# Code-level fallback — only used when key absent from all config sources
_SCOUT_TASK_DEFAULTS = {
    "platforms":          ["scraping_url", "YouTube", "Facebook", "LinkedIn", "instagram"],
    "niches":             ["AI", "Tech"],
    "min_virality_score": 75,
    "output_queue_size":  10,
    "auto_consume":       True,
    "use_web_search":     True,
    "force_refresh":      False,
    "force_scraping":     False,
    "channel":            "PlayOwnAi",
}

# Keys inside scout_config that map directly to top-level inputs.
# "scraping_url" is handled separately (renamed to scraping_url_file).
_SCOUT_CONFIG_KEYS = {
    "force_scraping", "force_refresh", "platforms", "niches",
    "min_virality_score", "output_queue_size", "auto_consume",
    "use_web_search", "llm_scout",
    "social_credentials_file", "fb_credentials_file",
    "yt_client_secrets_file", "yt_token_file",
}


def _apply_scout_config(inputs: dict) -> None:
    """
    Flatten scout_config block into top-level inputs.
    scout_config wins over existing top-level keys (it's channel-specific config).
    Called before profile and defaults so priority is: scout_config > profile > defaults.
    """
    scout_cfg = inputs.get("scout_config", {})
    if not scout_cfg:
        return

    for k, v in scout_cfg.items():
        if k == "scraping_url":
            # Rename to the canonical key name expected by _resolve_scraping_url
            inputs["scraping_url_file"] = v
        elif k == "niche_strict":
            inputs["niche_strict"] = v
        elif k in _SCOUT_CONFIG_KEYS:
            inputs[k] = v   # hard override — scout_config is authoritative

    if scout_cfg:
        print(f"⚙️   scout_config applied: {list(scout_cfg.keys())}")


def _load_audience_profile(inputs: dict) -> dict:
    import json
    path = inputs.get("audience_profiles_file", "input/audience_profiles.json")
    key  = inputs.get("audience_profile", "US")
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        p = data.get(key, {})
        if not p:
            print(f"⚠️  Unit-Scout: profile '{key}' not in {path}")
        return p
    except FileNotFoundError:
        print(f"⚠️  Unit-Scout: {path} not found — using defaults")
        return {}
    except Exception as exc:
        print(f"⚠️  Unit-Scout: profile load failed — {exc}")
        return {}


def _resolve_scraping_url(inputs: dict, profile: dict) -> str:
    # 1. scout_config set it explicitly (already in inputs["scraping_url_file"])
    explicit = inputs.get("scraping_url_file", "")
    if explicit and explicit != "data/scraping_url.json":
        return explicit
    # 2. Profile owns its sources
    if profile.get("scraping_url"):
        return profile["scraping_url"]
    # 3. Naming convention probe
    key = inputs.get("audience_profile", "US").lower()
    conv = f"data/scraping_url_{key}.json"
    if Path(conv).exists():
        return conv
    # 4. Global fallback
    return "data/scraping_url.json"


def _queue_path(inputs: dict) -> str:
    profile = inputs.get("audience_profile", "global").lower()
    p = TOPICS_ROOT / profile / "topic_memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def run(topic: str, workspace: Path, inputs: dict, force: bool = False):
    # --- 0. Short-circuit logic ---
    # If the topic is not "auto", this unit does not perform scouting.
    if inputs.get("_topic", "").lower() != "auto":
        print(f"⏭️  Unit-Scout skipped: topic is '{inputs.get('_topic')}', not 'auto'.")
        return
    # ── 1. Apply scout_config (highest priority) ──────────────────────────
    _apply_scout_config(inputs)

    profile_key  = inputs.get("audience_profile", "US")
    profile_data = _load_audience_profile(inputs)

    # ── 2. Resolve paths ──────────────────────────────────────────────────
    queue_path        = _queue_path(inputs)
    scraping_url_file = _resolve_scraping_url(inputs, profile_data)

    inputs["output_dir"]        = str(workspace)
    inputs["filename"]          = inputs.get("_slug", workspace.name)
    inputs["scout_queue_path"]  = queue_path
    inputs["scraping_url_file"] = scraping_url_file

    # ── 3. Profile niches = highest priority (profile defines audience identity)
    # scout_config["niches"] is only used when profile has no niches defined
    profile_niches = profile_data.get("niches", [])
    if profile_niches:
        inputs["niches"] = profile_niches
        print(f"🎯  Niches from profile [{profile_key}]: {len(profile_niches)} topics")
    elif inputs.get("niches") and inputs["niches"] not in ([], ["AI", "Tech"]):
        print(f"🎯  Niches from scout_config: {inputs['niches']}")

    # ── 4. Inject remaining profile fields as profile_* (no overwrite) ───
    for k, v in profile_data.items():
        if k not in ("scraping_url", "niches"):
            inputs.setdefault(f"profile_{k}", v)

    # ── 5. Fill remaining task template variables ─────────────────────────
    for k, v in _SCOUT_TASK_DEFAULTS.items():
        inputs.setdefault(k, v)

    print(
        f"🔍  Unit-Scout | profile={profile_key}"
        f" | niches={len(inputs.get('niches', []))}"
        f" | force_scraping={inputs.get('force_scraping')}"
        f" | queue={queue_path}"
        f" | sources={scraping_url_file}"
    )

    factory = CF2Crew(inputs)
    return Crew(
        agents=[factory.scout_trend_agent()],
        tasks=[factory.scout_trending_topics()],
        verbose=False,
    ).kickoff(inputs=inputs)
