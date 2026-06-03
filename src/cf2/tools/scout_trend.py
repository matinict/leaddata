"""
social_trend_scout_tool.py
──────────────────────────────────────────────────────────────────────────────
SocialTrend Scout Tool for CrewAI Video Factory

Design principles
─────────────────
• ZERO static niche/hashtag/category values — everything derived at runtime
  from the niches list passed via data.json → trend_scout_config.niches
• topic_memory.json has NO size limit — all discovered topics are kept
• Archive entries carry full video URLs (YouTube, Facebook, TikTok) set by
  main.py when a video is completed and uploaded

force_scraping behaviour
────────────────────────
• force_scraping=true  → Always scrape live from all platforms in the list.
  Ignores any previously cached/memory topics. Bypasses smart-skip.
• force_scraping=false → Memory-first: load topics from data/topic_memory.json.
  Only scrape if queue has no fresh UNUSED/queued topics.

scraping_url platform
─────────────────────
• Include "scraping_url" in the platforms list to activate URL scraping.
• URLs are read from the file pointed to by scraping_url_file
  (default: "data/scraping_url.json").
• scraping_url.json schema:
    [
      {"url": "https://...", "niche": "AI", "label": "optional tag"},
      ...
    ]
• The scraper fetches each URL, extracts page titles / og:title / headlines
  and converts them into candidate topics scored like any other source.

Data layers (each falls back to the next on failure):
  1. scraping_url URLs   → custom URL scraper (if "scraping_url" in platforms)
  2. Real platform APIs  → YouTube Data API + RapidAPI
  3. LLM web search      → litellm (model-agnostic, no Anthropic tool required)
  4. Dynamic seed bank   → built from input niches, never hardcoded

topic_memory.json schema
─────────────────────────
{
  "queue": [                          ← all UNUSED / IN_PROGRESS (no size limit)
    {
      "title":          "...",
      "niche":          "LLM",
      "platforms":      ["YouTube", "LinkedIn"],
      "virality_score": 87,
      "debate_score":   73,
      "format_scores":  {"debate": 73, "bar_chart": 30, ...},
      "best_format":    "debate",
      "emotional_hook": "Curiosity / Surprise",
      "raw_signals":    {"engagement": 90, ...},
      "data_source":    "llm_web_search",
      "status":         "UNUSED",
      "discovered_at":  "2026-03-28T...",
      "selected_at":    null,
      "used_at":        null,
      "performance":    {}
    }
  ],
  "current": null,
  "archive": [                        ← completed topics with video publish URLs
    {
      ...same fields...,
      "status":       "done",
      "completed_at": "2026-03-28T...",
      "video_urls": {                 ← populated by main.py after upload
        "youtube":  "https://youtu.be/...",
        "facebook": "https://facebook.com/...",
        "tiktok":   "https://tiktok.com/..."
      },
      "performance": {
        "yt_views": 0, "yt_likes": 0, "yt_comments": 0
      }
    }
  ],
  "_updated_at": "2026-03-28T...",
  "_note": "queue has no size limit. archive entries include video_urls."
}

scraping_url.json schema (data/scraping_url.json)
──────────────────────────────────────────────────
Named-group schema (recommended — niche auto-derived from group key):
{
  "ai_news_sources": [
    {
      "name":         "TechCrunch AI",
      "base_url":     "https://techcrunch.com/",
      "category_url": "https://techcrunch.com/category/artificial-intelligence/",
      "type":         "news"
    }
  ],
  "political_news_sources": [ ... ],
  "religion_blogs":          [ ... ],
  "finance_sources":         [ ... ]
}
Group key name auto-maps to niche:
  "ai_*"        → "AI"    |  "politic_*"  → "Politics"
  "religion_*"  → "Religion"  |  "finance_*"  → "Finance"
  "tech_*"      → "Tech"  |  "health_*"   → "Health"  (etc.)

Flat-list schema (legacy, still supported):
[
  {"url": "https://...", "niche": "AI", "label": "hackernews"},
  ...
]
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import json
import math
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

try:
    from litellm import completion as _llm_completion
    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False


# ── Credentials ───────────────────────────────────────────────────────────────
# Read from input/social_credentials.json (same file used by all other tools).
# Env vars RAPIDAPI_KEY / YOUTUBE_API_KEY still work as legacy fallback.

def _load_social_creds(path: str = "input/social_credentials.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

_SOCIAL_CREDS: dict = _load_social_creds()

def _get_rapid_key() -> str:
    return (
        os.environ.get("RAPIDAPI_KEY", "").strip()
        or (_SOCIAL_CREDS.get("RapidAPI") or {}).get("api_key", "").strip()
    )

def _get_yt_key() -> str:
    return (
        os.environ.get("YOUTUBE_API_KEY", "").strip()
        or (_SOCIAL_CREDS.get("YouTube") or {}).get("api_key", "").strip()
    )

# ── RapidAPI host + endpoint constants ───────────────────────────────────────
_RAPID_HOST_IG       = "instagram-scraper-api2.p.rapidapi.com"
_RAPID_EP_IG         = "/v1.2/hashtag"
_RAPID_HOST_LINKEDIN = "linkedin-api8.p.rapidapi.com"
_RAPID_EP_LINKEDIN   = "/search-posts"
_RAPID_HOST_FB       = "facebook-scraper3.p.rapidapi.com"
_RAPID_EP_FB         = "/search/post"

_KEY_MIN_LEN = 30   # keys shorter than this are placeholders


class _RapidAPINotSubscribed(Exception):
    """Raised on first 403 — key is valid but not subscribed to this host."""


# ── Dynamic niche → YouTube category IDs ─────────────────────────────────────
# Lookup table keyed by lowercase niche slug. New niches auto-map to "default".
_NICHE_YT_CATEGORIES: dict[str, list[str]] = {
    "ai":             ["28", "27"],
    "llm":            ["28", "27"],
    "genai":          ["28", "27"],
    "ml":             ["28", "27"],
    "tech":           ["28"],
    "future of work": ["22", "27"],
    "work":           ["22", "27"],
    "crypto":         ["28", "25"],
    "web3":           ["28"],
    "startup":        ["22", "25"],
    "finance":        ["25"],
    "health":         ["26"],
    "education":      ["27"],
    "default":        ["28"],
}

def _yt_categories_for_niches(niches: list[str]) -> list[str]:
    """Derive YouTube category IDs from any arbitrary niche list."""
    cat_ids: list[str] = []
    for niche in niches:
        nl = niche.lower().strip()
        matched = False
        for key, ids in _NICHE_YT_CATEGORIES.items():
            if key in nl or nl in key:
                cat_ids.extend(ids)
                matched = True
        if not matched:
            cat_ids.extend(_NICHE_YT_CATEGORIES["default"])
    return list(dict.fromkeys(cat_ids))


def _niche_for_yt_cat(cat_id: str, niches: list[str]) -> str:
    """Return the best-matching niche for a YouTube category ID."""
    for niche in niches:
        if cat_id in _NICHE_YT_CATEGORIES.get(niche.lower().strip(), []):
            return niche
    return niches[0] if niches else "General"


# ── Dynamic niche → hashtags ──────────────────────────────────────────────────
_NICHE_HASHTAG_SEEDS: dict[str, list[str]] = {
    "ai":             ["artificialintelligence", "aitools", "chatgpt", "machinelearning"],
    "llm":            ["llm", "gpt", "generativeai", "promptengineering"],
    "genai":          ["generativeai", "aiart", "stablediffusion", "midjourney"],
    "ml":             ["machinelearning", "deeplearning", "neuralnetworks", "datascience"],
    "tech":           ["technology", "techindustry", "bigtech", "techtrends"],
    "future of work": ["futureofwork", "remotework", "aiworkplace", "automation"],
    "work":           ["remotework", "productivity", "leadership", "careertips"],
    "crypto":         ["bitcoin", "ethereum", "cryptocurrency", "defi"],
    "web3":           ["web3", "nft", "blockchain", "decentralized"],
    "startup":        ["startup", "entrepreneurship", "venturecapital", "founders"],
    "finance":        ["personalfinance", "investing", "stockmarket", "wealthbuilding"],
    "health":         ["healthcare", "mentalhealth", "wellness", "medtech"],
    "education":      ["elearning", "onlinecourse", "edtech", "learning"],
}

def _hashtags_for_niches_dynamic(niches: list[str]) -> list[str]:
    """Build hashtag list dynamically — no static fallback required."""
    tags: list[str] = []
    for niche in niches:
        nl = niche.lower().strip()
        matched = False
        for key, ht in _NICHE_HASHTAG_SEEDS.items():
            if key in nl or nl in key:
                tags.extend(ht)
                matched = True
        if not matched:
            slug = re.sub(r"[^a-z0-9]", "", nl)
            if slug:
                tags.append(slug)
            tags.extend(["artificialintelligence", "tech", "innovation"])
    seen: set[str] = set()
    return [t for t in tags if not (t in seen or seen.add(t))]  # type: ignore


def _niche_for_tag_dynamic(tag: str, niches: list[str]) -> str:
    """Map a hashtag back to the best-matching niche from the input list."""
    tl = tag.lower()
    for niche in niches:
        nl = niche.lower().strip()
        seeds = _NICHE_HASHTAG_SEEDS.get(nl, [])
        if tl in seeds or nl in tl:
            return niche
    return niches[0] if niches else "General"


# ── Dynamic seed bank ─────────────────────────────────────────────────────────
# Templates use {niche} — titles adapt to any niche passed from data.json.
_SEED_TEMPLATES: list[dict] = [
    {"tmpl": "Is {niche} Actually Changing the World or Just Hype?",
     "e": 88, "g": 84, "em": 85, "s": 87},
    {"tmpl": "The Dark Side of {niche} Nobody Talks About",
     "e": 91, "g": 87, "em": 92, "s": 89},
    {"tmpl": "{niche} in 2026: What Experts Are Getting Wrong",
     "e": 85, "g": 88, "em": 81, "s": 86},
    {"tmpl": "Will {niche} Replace Human Jobs? The Real Answer",
     "e": 93, "g": 89, "em": 91, "s": 90},
    {"tmpl": "{niche} vs Human Intelligence: Who Actually Wins?",
     "e": 87, "g": 83, "em": 88, "s": 85},
    {"tmpl": "The {niche} Bubble Is About to Burst — Here's Why",
     "e": 86, "g": 90, "em": 89, "s": 88},
    {"tmpl": "How {niche} Is Quietly Killing Traditional Industries",
     "e": 84, "g": 86, "em": 87, "s": 83},
    {"tmpl": "Top {niche} Tools in 2026: Ranked by Real Experts",
     "e": 82, "g": 85, "em": 76, "s": 84},
    {"tmpl": "The {niche} Skills That Will Make You Rich in 2026",
     "e": 89, "g": 87, "em": 84, "s": 88},
    {"tmpl": "Is {niche} Ethical? The Debate That Divides Experts",
     "e": 85, "g": 81, "em": 90, "s": 83},
]

def _build_seed_bank(niches: list[str], platforms: list[str]) -> list[dict]:
    """Build seed topics entirely from niche input — zero hardcoded titles."""
    results: list[dict] = []
    seen: set[str] = set()
    for niche in niches:
        for td in _SEED_TEMPLATES:
            title = td["tmpl"].format(niche=niche)
            if title.lower() in seen:
                continue
            seen.add(title.lower())
            results.append({
                "title":           title,
                "niche":           niche,
                "platforms":       platforms[:2] if platforms else ["YouTube"],
                "engagement":      td["e"],
                "growth_speed":    td["g"],
                "emotional":       td["em"],
                "search_momentum": td["s"],
            })
    return results



# =============================================================================
# SCRAPING URL — GROUP KEY → NICHE MAPPING  (module-level, Pydantic-safe)
# =============================================================================
# Maps scraping_url.json group key slugs to human-readable niche labels.
# Kept at module level (NOT inside BaseTool subclass) so Pydantic v2 cannot
# intercept the underscore-prefixed name and wrap it as ModelPrivateAttr.
# Add new mappings freely — no code changes anywhere else needed.

_GROUP_NICHE_MAP: dict[str, str] = {
    "ai":          "AI",
    "llm":         "LLM",
    "genai":       "GenAI",
    "ml":          "ML",
    "tech":        "Tech",
    "politic":     "Politics",
    "religion":    "Religion",
    "faith":       "Religion",
    "spiritual":   "Religion",
    "health":      "Health",
    "finance":     "Finance",
    "crypto":      "Crypto",
    "web3":        "Web3",
    "startup":     "Startup",
    "science":     "Science",
    "climate":     "Climate",
    "education":   "Education",
    "sports":      "Sports",
    "entertain":   "Entertainment",
    "business":    "Business",
    "world":       "World News",
    "local":       "Local News",
    "gaming":      "Gaming",
    "social":      "Social Media",
    "security":    "Cybersecurity",
    "cyber":       "Cybersecurity",
    "space":       "Space",
    "auto":        "Automotive",
    "food":        "Food",
    "travel":      "Travel",
}


def _niche_from_group_key(key: str, fallback: str) -> str:
    """Derive a human-readable niche from a scraping_url.json group key.

    Example:  "ai_news_sources"       → "AI"
              "political_news_sources" → "Politics"
              "religion_blogs"         → "Religion"
              "unknown_category"       → fallback
    """
    kl = key.lower()
    for slug, niche in _GROUP_NICHE_MAP.items():
        if slug in kl:
            return niche
    return fallback


def _remap_niches(candidates: list[dict], profile_niches: list[str]) -> list[dict]:
    """
    Remap each scraped candidate's niche to the closest profile niche.

    Matches title words (≥4 chars) against niche label words (≥4 chars).
    Best hit count wins. Falls back to original group-key niche when
    no profile niche matches — preserving AI/Tech topics that are
    genuinely off-profile but still relevant.

    Examples (US profile niches):
      "Housing Prices Hit Record High"  → "Housing Crisis USA"  (shares "housing")
      "Student Loan Forgiveness Debate" → "Student Debt Crisis" (shares "student")
      "Musk v. Altman OpenAI Battle"    → no match → stays "AI"
    """
    niche_keywords: dict[str, set[str]] = {
        n: {w.lower() for w in re.findall(r"[A-Za-z]{4,}", n)}
        for n in profile_niches
    }
    niche_keywords = {n: kw for n, kw in niche_keywords.items() if kw}

    for c in candidates:
        title_words = {w.lower() for w in re.findall(r"[A-Za-z]{4,}", c.get("title", ""))}
        best_niche, best_hits = None, 0
        for niche, keywords in niche_keywords.items():
            hits = len(title_words & keywords)
            if hits > best_hits:
                best_hits, best_niche = hits, niche
        if best_niche:
            c["niche"] = best_niche
    return candidates


# ── Weak-hook patterns that kill CTR ─────────────────────────────────────
_WEAK_PREFIXES = re.compile(
    r"^(how |why |what |when |where |who |the way |here'?s? |this is |"
    r"report[s]?[: ]|study[: ]|data[: ]|analysis[: ]|survey[: ]|"
    r"analysts? say|experts? say|experts? warn|sources? say|"
    r"new report|new study|new data|new research|"
    r"according to|it turns out|turns out)",
    re.IGNORECASE,
)
_NEWS_PATTERNS = [
    # "X's Y is Z" → extract core conflict
    (re.compile(r"^(.+?)\s+(?:is|are|was|were)\s+(?:a|an|the)\s+(.+),\s*analysts?\s+say", re.I), "conflict"),
    # "How X brought about Y" → "Did X Really Cause Y?"
    (re.compile(r"^how\s+(.+?)\s+(?:brought|caused|led|triggered)\s+(.+)", re.I),              "how_caused"),
    # "X rails against / slams / blasts Y" → "X vs Y: Who Has the Power?"
    (re.compile(r"^(.+?)\s+(?:rails? against|slams?|blasts?|attacks?|targets?)\s+(.+)", re.I), "rails_against"),
    # "Logjam / backlog / crisis of X" → "Is X Broken?"
    (re.compile(r"^(?:logjam|backlog|crisis|collapse|failure)\s+of\s+(.+)", re.I),             "system_broken"),
    # "What smart/experts are saying about X" → "X: Fair or Too Far?"
    (re.compile(r"^what\s+(?:smart people|experts?|analysts?)\s+are\s+saying\s+about\s+(.+)", re.I), "experts_say"),
]

# Debate reframe templates keyed by pattern type
_DEBATE_REWRITES = {
    "conflict":      lambda m: f"Is {_cap(m.group(1))} Really a Win — Or Just Politics?",
    "how_caused":    lambda m: f"Did {_cap(m.group(1))} Really Cause {_cap(m.group(2))}?",
    "rails_against": lambda m: f"{_cap(m.group(1))} vs {_cap(m.group(2))}: Who Has the Power?",
    "system_broken": lambda m: f"Is {_cap(m.group(1))} Completely Broken?",
    "experts_say":   lambda m: f"{_cap(m.group(1))}: Fair or Too Far?",
}

def _cap(s: str) -> str:
    """Capitalize first letter only."""
    s = s.strip()
    return s[0].upper() + s[1:] if s else s


def _rewrite_to_debate(candidate: dict) -> dict:
    """
    Rewrite a news-style headline to a debate-format title.
    Stores original in candidate["original_title"] for reference.
    Boosts emotional signal by +8 when rewrite succeeds (debate framing
    increases emotional engagement).

    Pattern:
      ❌ "Logjam of U.S. immigration applications puts millions at risk"
      ✅ "Is America's Immigration System Completely Broken?"

      ❌ "What smart people are saying about Mamdani's tax proposal"
      ✅ "Mamdani's Tax Proposal: Fair or Too Far?"

      ❌ "Orbán's defeat is a win for democracy, analysts say"
      ✅ "Is Orbán's Defeat Really a Win — Or Just Politics?"
    """
    title = candidate.get("title", "").strip()
    if not title or len(title) < 20:
        return candidate

    rewritten = None

    # Try named patterns first
    for pattern, key in _NEWS_PATTERNS:
        m = pattern.match(title)
        if m:
            try:
                rewritten = _DEBATE_REWRITES[key](m)
            except Exception:
                pass
            break

    # Fallback: strip weak prefix + append "?"
    if not rewritten and _WEAK_PREFIXES.match(title):
        stripped = _WEAK_PREFIXES.sub("", title).strip(" .,;:")
        if len(stripped) > 20:
            # Wrap in "Is X Actually True?" frame
            rewritten = f"Is {stripped[0].upper() + stripped[1:]}?"

    if rewritten and rewritten != title:
        candidate["original_title"] = title
        candidate["title"]          = rewritten
        # Boost emotional score — debate framing raises engagement
        candidate["emotional"] = min(100, candidate.get("emotional", 72) + 8)

    return candidate


# Scoring signals — module-level so Pydantic v2 cannot intercept them
_DEBATE_TRIGGERS: list[str] = [
    "vs ", "versus ", "better ", "worse ", "dangerous ", "future of ",
    "killing ", "will replace ", "replace ", "end of ", "dead ",
    "better than ", "worse than ", "threat ", "should we ",
    "is ", "does ", "can ", "will ", "human vs ",
    "real or ", "or just ", "actually ", "myth ", "truth about ",
    "biggest debate ", "controversial ", "unpopular opinion ",
]

_FORMAT_SIGNALS: dict[str, list[str]] = {
    "debate":    ["vs ", "or ", "is ", "does ", "will ", "can ", "should ",
                  "better ", "debate ", "opinion ", "truth ", "myth ",
                  "really ", "actually "],
    "bar_chart": ["growth ", "rise ", "top ", "best ", "most popular ",
                  "rank ", "2024 ", "2025 ", "2026 ", "over time ",
                  "history ", "evolution ", "fastest ", "biggest ",
                  "leading ", "comparison "],
    "definition":["what is ", "how does ", "explain ", "guide to ",
                  "introduction ", "beginners ", "basics ", "learn ",
                  "understand ", "overview "],
    "shorts":    ["quick ", "shocking ", "you won't believe ", "secret ",
                  "hack ", "tip ", "in 60 seconds ", "fast ", "viral ", "trend "],
}


# =============================================================================
# INPUT SCHEMA
# =============================================================================

class SocialTrendScoutInput(BaseModel):
    platforms: list[str] = Field(
        default=["YouTube", "Facebook", "LinkedIn", "instagram"],
        description=(
            "Platforms to monitor. Include 'scraping_url' to also scrape custom URLs "
            "from the file at scraping_url_file."
        ),
    )
    niches: list[str] = Field(
        default=["AI", "Tech"],
        description=(
            "Niches from data.json trend_scout_config.niches. "
            "ALL hashtags, YT categories, seed topics, and LLM prompts are "
            "generated dynamically from this list. No static values anywhere."
        ),
    )
    min_virality_score: int = Field(
        default=75, ge=0, le=100,
        description="Minimum virality score (0-100) to enter the queue.",
    )
    auto_consume: bool = Field(
        default=True,
        description="Mark the top topic SELECTED after scouting.",
    )
    use_web_search: bool = Field(
        default=True,
        description="Enable real API + LLM fallback.",
    )
    queue_path: str = Field(
        default="data/topic_memory.json",
        description="Path to topic_memory.json. No size limit on queue.",
    )
    force_refresh: bool = Field(
        default=False,
        description="Force fresh scout even if fresh real-source topics exist.",
    )
    force_scraping: bool = Field(
        default=False,
        description=(
            "When True: always scrape live from all platforms — ignores cached memory, "
            "bypasses smart-skip entirely. "
            "When False: memory-first — load UNUSED topics from topic_memory.json; "
            "only scrape if no fresh topics exist in the queue."
        ),
    )
    scraping_url_file: str = Field(
        default="data/scraping_url.json",
        description=(
            "Path to JSON file listing custom URLs to scrape when 'scraping_url' is "
            "included in platforms. Schema: [{\"url\": \"...\", \"niche\": \"AI\", \"label\": \"...\"}]"
        ),
    )
    llm_scout: str | None = Field(
        default=None,
        description="LLM model for topic generation. None = project default.",
    )


# =============================================================================
# TOOL
# =============================================================================

class SocialTrendScoutTool(BaseTool):
    name: str = "ScoutTrendScout"
    description: str = (
        "Discovers trending high-virality topics filtered by niches from data.json. "
        "All hashtags, YT categories, seed titles derived dynamically from input niches. "
        "topic_memory.json stores ALL topics (no limit). "
        "Archive records include YouTube, Facebook, TikTok video URLs."
    )
    args_schema: type[BaseModel] = SocialTrendScoutInput

    # =========================================================================
    # ENTRY POINT
    # =========================================================================

    def _run(
        self,
        platforms: list[str] | None = None,
        niches: list[str] | None = None,
        min_virality_score: int = 75,
        auto_consume: bool = True,
        use_web_search: bool = True,
        queue_path: str = "data/topic_memory.json",
        force_refresh: bool = False,
        force_scraping: bool = False,
        scraping_url_file: str = "data/scraping_url.json",
        llm_scout: str | None = None,
        **kwargs: Any,
    ) -> str:

        platforms = platforms or ["YouTube", "Facebook", "LinkedIn", "instagram"]
        niches    = niches    or ["AI", "Tech"]

        print(f"[Scout] Niches: {niches}  |  Platforms: {platforms}")
        print(f"[Scout] force_scraping={force_scraping}  |  force_refresh={force_refresh}")

        # Auto-enable live scraping when the queue file doesn't exist yet.
        # Without this, an empty queue falls through to the LLM layer which
        # hangs on large niche lists (20+ niches → huge prompt → slow response).
        # scraping_url is faster, more relevant, and already configured.
        if not force_scraping and not os.path.exists(queue_path):
            print(f"[Scout] Queue file not found — enabling live scraping for first run.")
            force_scraping = True

        file_data = self._load_file(queue_path)
        queue     = file_data.get("queue",   [])
        archive   = file_data.get("archive", [])

        # ── MEMORY-FIRST MODE (force_scraping=False) ───────────────────────────
        # When force_scraping is OFF, serve from memory if fresh topics exist.
        # This differs from force_refresh — force_refresh only controls the
        # real-API smart-skip; force_scraping=False adds a full memory-first
        # shortcut that returns immediately without hitting any platform.
        if not force_scraping:
            fresh_memory = [
                t for t in queue
                if t.get("status") in ("UNUSED", "queued")
            ]
            if fresh_memory:
                best = fresh_memory[0]
                print(
                    f"[Scout] Memory-first: {len(fresh_memory)} UNUSED topics in queue "
                    f"— skipping live scrape (force_scraping=false)."
                )
                if auto_consume and best.get("status") == "UNUSED":
                    best["status"]      = "SELECTED"
                    best["selected_at"] = datetime.now(timezone.utc).isoformat()
                self._save_file(queue_path, queue, archive)
                lines = [
                    "⏭️  Memory-first Skip (force_scraping=false)",
                    f"   Loaded from:     {queue_path}",
                    f"   Queue total:     {len(fresh_memory)} UNUSED topics",
                    " ",
                    "TOP TOPIC FROM MEMORY:",
                    f"   Title:          \"{best.get('title')}\"",
                    f"   Virality Score: {best.get('virality_score')}/100",
                    f"   Best Format:    {best.get('best_format', 'debate')}",
                    f"   Niche:          {best.get('niche')}",
                    f"   Data Source:    {best.get('data_source', 'memory')}",
                    f"   Status:         {best.get('status')}",
                    " ",
                    "TOP 5 FROM MEMORY:",
                ]
                for i, t in enumerate(fresh_memory[:5], 1):
                    icon = "►" if t.get("status") == "SELECTED" else " "
                    lines.append(
                        f"   {i}.{icon}[{t.get('virality_score', '?'):>3}] "
                        f"{t.get('title', 'N/A')[:65]}  "
                        f"({t.get('best_format','debate')}) [{t.get('data_source','?')[:4]}]"
                    )
                lines += [" ", "Set force_scraping=true in trend_scout_config to force live scraping."]
                return "\n".join(lines)
            else:
                print("[Scout] Memory empty — proceeding with live scrape despite force_scraping=false.")

        # ── SMART SKIP for real-source topics (only when not force_scraping) ───
        if not force_scraping and not force_refresh:
            fresh = [
                t for t in queue
                if t.get("status") in ("UNUSED", "queued")
                and t.get("data_source") in ("real_api", "llm_web_search", "scraping_url")
                and self._age_hours(t.get("discovered_at", "")) < 6
            ]
            if fresh:
                best = fresh[0]
                age  = self._age_hours(best.get("discovered_at", ""))
                return (
                    f"Smart Skip: {len(fresh)} fresh real-source topics ({age:.1f}h ago).\n"
                    f"Top: \"{best['title']}\"\n"
                    f"  Virality: {best.get('virality_score')} | "
                    f"Format: {best.get('best_format', 'debate')} | "
                    f"Platforms: {', '.join(best.get('platforms', []))}\n"
                    f"Queue: {queue_path}"
                )

        llm_model  = llm_scout or kwargs.get("llm_model") or None
        n_fetch    = min(10, max(5, len(niches) * 3))
        candidates, data_source = self._generate_candidates(
            niches, platforms, use_web_search, llm_model, n_fetch,
            force_scraping=force_scraping,
            scraping_url_file=scraping_url_file,
        )

        # Rewrite news-style headlines to debate-format titles before scoring.
        # Rule: trigger a decision in the viewer's mind, not inform first.
        candidates = [_rewrite_to_debate(c) for c in candidates]

        scored = sorted(
            [s for raw in candidates for s in [self._score_topic(raw, niches)]
             if s["virality_score"] >= min_virality_score],
            key=lambda x: x["virality_score"], reverse=True
        )

        # NO SIZE LIMIT — keep every topic
        archive_titles     = {t.get("title", "").lower() for t in archive}
        real_queued_titles = {
            t.get("title", "").lower() for t in queue
            if t.get("data_source") in ("real_api", "llm_web_search", "scraping_url")
        }

        now_iso    = datetime.now(timezone.utc).isoformat()
        new_topics = []
        for t in scored:
            tl = t["title"].lower()
            if tl in archive_titles or tl in real_queued_titles:
                continue
            t["status"]        = "UNUSED"
            t["discovered_at"] = now_iso
            t["data_source"]   = data_source
            new_topics.append(t)

        if data_source in ("real_api", "llm_web_search", "scraping_url"):
            kept = [t for t in queue
                    if t.get("status") in ("UNUSED", "IN_PROGRESS", "queued")
                    and t.get("data_source") in ("real_api", "llm_web_search", "scraping_url")]
        else:
            kept = [t for t in queue
                    if t.get("status") in ("UNUSED", "IN_PROGRESS", "queued")]

        # ── Queue hygiene: when force_scraping, purge stale junk from kept ──────
        # Old runs may have enqueued titles that would now fail the noise filter
        # (e.g. "AI News | Latest AI News, Analysis & Events" from before the fix).
        # Remove any kept topic whose title contains obvious noise markers.
        if force_scraping and kept:
            _STALE_CONTAINS = (" | ", "latest news, analysis", "spotlight:",
                               "dmwf spotlight", "join our", "sign up",
                               "subscribe to", "editorial spotlight")
            _STALE_SUFFIX_RE = re.compile(
                r"^.{0,40}\s*\|\s*.{0,60}(news|analysis|events|updates|blog)s?\s*$",
                re.IGNORECASE,
            )
            pre_purge = len(kept)
            kept = [
                t for t in kept
                if not any(p in t.get("title", "").lower() for p in _STALE_CONTAINS)
                and not _STALE_SUFFIX_RE.match(t.get("title", ""))
            ]
            purged = pre_purge - len(kept)
            if purged:
                print(f"[Scout] Queue hygiene: purged {purged} stale/junk topics from queue.")

        merged = new_topics + kept
        if not merged:
            merged = [t for t in queue if t.get("status") in ("UNUSED", "queued")]

        best = merged[0] if merged else None
        if auto_consume and best and best.get("status") == "UNUSED":
            best["status"]      = "SELECTED"
            best["selected_at"] = now_iso

        self._save_file(queue_path, merged, archive)

        lines = [
            "✅ Social Trend Scout Complete",
            f"   Mode:           {'🔴 force_scraping=true (live)' if force_scraping else '🟢 memory-first (live fallback)'}",
            f"   Data source:    {data_source}",
            f"   Niches scanned: {', '.join(niches)}",
            f"   Platforms:      {', '.join(platforms)}",
            f"   New topics:     {len(new_topics)}  |  Queue total: {len(merged)}  |  Archive: {len(archive)}",
            f"   Queue path:     {queue_path}  (no size limit)",
            " ",
        ]
        if best:
            lines += [
                "TOP TOPIC SELECTED:",
                f"   Title:          \"{best.get('title')}\"",
                f"   Virality Score: {best.get('virality_score')}/100",
                f"   Debate Score:   {best.get('debate_score')}/100",
                f"   Best Format:    {best.get('best_format', 'debate')}",
                f"   Niche:          {best.get('niche')}",
                f"   Platforms:      {', '.join(best.get('platforms', []))}",
                f"   Emotional Hook: {best.get('emotional_hook', 'N/A')}",
                f"   Data Source:    {best.get('data_source', 'unknown')}",
                f"   Status:         {best['status']}",
                " ", "TOP 5 QUEUE:",
            ]
            for i, t in enumerate(merged[:5], 1):
                icon = "►" if t.get("status") == "SELECTED" else " "
                lines.append(
                    f"   {i}.{icon}[{t.get('virality_score', '?'):>3}] "
                    f"{t.get('title', 'N/A')[:65]}  "
                    f"({t.get('best_format','debate')}) [{t.get('data_source','?')[:4]}]"
                )
        lines += [" ", "Set \"topic\": \"auto\" in data.json to consume automatically."]
        return "\n".join(lines)

    # =========================================================================
    # CANDIDATE GENERATION — 3-layer fallback
    # =========================================================================

    def _generate_candidates(
        self,
        niches: list[str],
        platforms: list[str],
        use_web_search: bool,
        llm_model: str | None,
        n_topics: int,
        force_scraping: bool = False,
        scraping_url_file: str = "data/scraping_url.json",
    ) -> tuple[list[dict], str]:

        pl = [p.lower() for p in platforms]

        # ── Layer 0 — Custom URL scraper (runs before all other layers) ────────
        # Activated when "scraping_url" appears in the platforms list.
        if "scraping_url" in pl:
            try:
                url_results = self._fetch_scraping_urls(niches, scraping_url_file, n_topics)
                if url_results:
                    print(f"[Scout] scraping_url: {len(url_results)} candidates from custom URLs.")
                    return url_results, "scraping_url"
                print("[Scout] scraping_url: 0 results — falling back to platform APIs.")
            except Exception as exc:
                print(f"[Scout] scraping_url error: {exc} — falling back to platform APIs.")

        yt_key    = _get_yt_key()
        rapid_key = _get_rapid_key()
        yt_ok     = use_web_search and bool(yt_key)    and len(yt_key)    >= _KEY_MIN_LEN
        rapid_ok  = use_web_search and bool(rapid_key) and len(rapid_key) >= _KEY_MIN_LEN

        # Layer 1 — Platform APIs
        if yt_ok or rapid_ok:
            try:
                results = self._fetch_platform_data(
                    niches, platforms,
                    yt_key    if yt_ok    else "",
                    rapid_key if rapid_ok else "",
                    n_topics,
                )
                if results:
                    print(f"[Scout] Real API: {len(results)} candidates.")
                    return results, "real_api"
                print("[Scout] Real APIs 0 results — falling back to LLM.")
            except _RapidAPINotSubscribed as e:
                print(f"[Scout] {e} — going to LLM.")
            except Exception as exc:
                print(f"[Scout] Real API error: {exc} — going to LLM.")
        else:
            if use_web_search:
                print("[Scout] No valid API keys — going to LLM.")

        # Layer 2 — LLM web search
        if use_web_search and _LITELLM_AVAILABLE:
            try:
                results = self._generate_via_llm(niches, platforms, llm_model, n_topics)
                if results:
                    return results, "llm_web_search"
            except Exception as exc:
                print(f"[Scout] LLM failed: {exc} — falling back to seed bank.")

        # Layer 3 — Dynamic seed bank
        print("[Scout] Using dynamic seed bank (built from input niches).")
        return _build_seed_bank(niches, platforms), "seed_bank"

    # =========================================================================
    # LAYER 1 — PLATFORM FETCHERS
    # =========================================================================

    def _fetch_platform_data(
        self,
        niches: list[str],
        platforms: list[str],
        yt_key: str,
        rapid_key: str,
        n_topics: int,
    ) -> list[dict]:
        pl = [p.lower() for p in platforms]
        all_raw: list[dict] = []

        if "youtube" in pl:
            if yt_key:
                all_raw.extend(self._fetch_youtube(niches, yt_key, n_topics))
            else:
                all_raw.extend(self._fetch_youtube_rss(niches, n_topics))

        if rapid_key:
            rapid_map = []
            if any(p in pl for p in ("instagram", "ig")):
                rapid_map.append(("Instagram", self._fetch_instagram))
            if "linkedin" in pl:
                rapid_map.append(("LinkedIn",  self._fetch_linkedin))
            if "facebook" in pl:
                rapid_map.append(("Facebook",  self._fetch_facebook))

            for name, fetcher in rapid_map:
                try:
                    all_raw.extend(fetcher(niches, rapid_key, n_topics))
                except _RapidAPINotSubscribed:
                    raise
                except Exception as exc:
                    print(f"[Scout/{name}] {exc} — skipping.")

        seen: set[str] = set()
        unique: list[dict] = []
        for item in all_raw:
            k = item.get("title", "").lower().strip()
            if k and k not in seen:
                seen.add(k)
                unique.append(item)
        return unique

    # =========================================================================
    # LAYER 0 — CUSTOM URL SCRAPER
    # =========================================================================

    def _fetch_scraping_urls(
        self,
        niches: list[str],
        scraping_url_file: str,
        n: int,
    ) -> list[dict]:
        """
        Scrape candidate topics from a user-defined scraping_url.json file.

        Supports TWO schemas — auto-detected at load time:

        ① Named-group schema (recommended):
          {
            "ai_news_sources": [
              {
                "name":         "TechCrunch AI",
                "base_url":     "https://techcrunch.com/",
                "category_url": "https://techcrunch.com/category/artificial-intelligence/",
                "type":         "news"
              },
              ...
            ],
            "political_news_sources": [ ... ],
            "religion_blogs":         [ ... ]
          }
          • Group key (e.g. "ai_news_sources") is used to auto-derive the niche.
          • Scraping target is `category_url` (falls back to `base_url`).
          • `type` field is stored as metadata but doesn't affect scraping.

        ② Flat-list schema (legacy):
          [
            {"url": "https://...", "niche": "AI", "label": "hackernews"},
            ...
          ]

        For each URL the scraper extracts headlines in this priority order:
          1. <og:title> meta tag   (best — usually the page's canonical title)
          2. All <h2> tags         (article headlines on listing/category pages)
          3. All <h3> tags         (sub-headlines, card titles)
          4. All <h1> tags         (page-level title — less useful on listing pages)
          5. <title> tag           (last resort — often contains site name suffix)

        All extracted strings are HTML-cleaned, entity-decoded, deduplicated,
        and returned as scored candidate dicts for _score_topic().
        """
        # ── Load file ──────────────────────────────────────────────────────────
        if not os.path.exists(scraping_url_file):
            print(f"[Scout/scraping_url] File not found: {scraping_url_file}")
            return []

        try:
            with open(scraping_url_file, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
        except Exception as exc:
            print(f"[Scout/scraping_url] Cannot read {scraping_url_file}: {exc}")
            return []

        # ── Normalise into flat list of (url, niche, label, source_type) ───────
        default_niche = niches[0] if niches else "AI"
        url_entries: list[tuple[str, str, str, str]] = []  # (url, niche, label, type)

        if isinstance(raw_data, dict):
            # ① Named-group schema
            for group_key, sources in raw_data.items():
                if not isinstance(sources, list):
                    continue
                group_niche = _niche_from_group_key(group_key, default_niche)
                print(f"[Scout/scraping_url] Group '{group_key}' → niche='{group_niche}' "
                      f"({len(sources)} sources)")
                for src in sources:
                    if not isinstance(src, dict):
                        continue
                    # Prefer category_url (listing page) over base_url (home page)
                    url = (
                        src.get("category_url") or
                        src.get("base_url") or
                        src.get("url") or ""
                    ).strip()
                    label       = (src.get("name") or src.get("label") or url[:50]).strip()
                    source_type = (src.get("type") or "news").strip()
                    if url.startswith("http"):
                        url_entries.append((url, group_niche, label, source_type))

        elif isinstance(raw_data, list):
            # ② Flat-list schema (legacy)
            for entry in raw_data:
                if not isinstance(entry, dict):
                    continue
                url   = (entry.get("url") or entry.get("category_url") or "").strip()
                niche = (entry.get("niche") or default_niche).strip()
                label = (entry.get("label") or entry.get("name") or url[:50]).strip()
                stype = (entry.get("type") or "news").strip()
                if url.startswith("http"):
                    url_entries.append((url, niche, label, stype))

        else:
            print(f"[Scout/scraping_url] Unrecognised schema in {scraping_url_file} "
                  f"(expected dict or list, got {type(raw_data).__name__})")
            return []

        if not url_entries:
            print(f"[Scout/scraping_url] No valid URLs found in {scraping_url_file}")
            return []

        print(f"[Scout/scraping_url] Total sources to scrape: {len(url_entries)}")

        results: list[dict] = []
        seen_titles: set[str] = set()

        # ── Noise constants — defined ONCE before the URL loop ─────────────────
        # Keeping these outside the per-URL loop avoids re-creating them on every
        # iteration (which was harmless but wasteful and confusing to read).
        _NOISE_EXACT: frozenset[str] = frozenset({
            "home", "menu", "search", "subscribe", "newsletter", "sign in",
            "log in", "log out", "sign up", "contact", "about", "privacy",
            "terms", "cookie policy", "read more", "learn more", "see all",
            "view all", "load more", "show more", "back to top", "share",
            "follow us", "get started", "try for free", "join now",
            "advertisement", "sponsored", "related articles", "more stories",
            "trending now", "editor's pick", "editors pick", "top stories",
            "editorial spotlight", "editorial spotlight focus",
            "spotlight focus", "in focus", "special report",
            "breaking news", "latest news", "news", "blog", "press", "careers",
            "write for us", "advertise", "sitemap", "accessibility",
            "topics", "sections", "categories", "tags", "authors",
            "dmwf spotlight", "spotlight",
        })
        _NOISE_STARTSWITH: tuple[str, ...] = (
            "join our", "sign up for", "subscribe to", "follow us on",
            "get the", "download the", "try our", "click here",
            "read our", "see our", "view our", "check out our",
            "all rights reserved", "copyright ©", "© 20",
            "powered by", "built with",
            # Section-header prefixes used by marketing sites
            "dmwf spotlight:", "spotlight:", "featured:", "sponsored:",
            "advertisement:", "partner content:", "promoted:",
        )
        _NOISE_CONTAINS: tuple[str, ...] = (
            " | ", " - home", "latest news, analysis",
            "all rights reserved", "cookie", "privacy policy",
            "terms of service", "terms of use",
            # Marketing/newsletter section labels embedded in titles
            "dmwf spotlight", " spotlight:", "spotlight focus",
            # Event/conference/promo noise
            "in-person event", "in person event", "expo ,", ", expo",
            "register now", "register today", "early bird",
            "free webinar", "live webinar", "virtual summit",
            "conference agenda", "attend the", "book your ticket",
        )
        # Site-name suffix patterns: "X News | Latest X News" → discard whole
        _SITE_SUFFIX_RE = re.compile(
            r"^.{0,40}\s*\|\s*.{0,60}(news|analysis|events|updates|blog|"
            r"magazine|weekly|daily|podcast|newsletter)s?\s*$",
            re.IGNORECASE,
        )
        # Controversy/emotion signal words for dynamic scoring
        _CONTROVERSY_WORDS: frozenset[str] = frozenset({
            "why", "how", "what", "when", "will", "is", "are", "does",
            "can", "should", "could", "would", "vs", "versus", "against",
            "threat", "risk", "danger", "replace", "kill", "end", "dead",
            "future", "change", "revolution", "crisis", "fight", "battle",
            "debate", "controversy", "problem", "fail", "collapse",
            "breakthrough", "secret", "hidden", "truth", "lie", "myth",
            "exposed", "leak", "ban", "regulation", "warning", "alarm",
            "surprise", "shock", "unexpected", "confirmed", "denied",
        })

        for url, niche, label, source_type in url_entries:
            # ── Fetch page ────────────────────────────────────────────────────
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36"
                        ),
                        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "en-US,en;q=0.9",
                        "Accept-Encoding": "identity",
                    },
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw_bytes = resp.read(400_000)   # 400 KB cap per page
                    charset   = "utf-8"
                    ct        = resp.headers.get("Content-Type", "")
                    if "charset=" in ct:
                        charset = ct.split("charset=")[-1].split(";")[0].strip() or "utf-8"
                    html = raw_bytes.decode(charset, errors="replace")

            except Exception as exc:
                print(f"[Scout/scraping_url] {label} — fetch error: {exc}")
                continue

            # ── Extract headlines from HTML ────────────────────────────────────
            # Strategy: listing/category pages expose article titles in h2/h3.
            # Home pages and single-article pages expose them in og:title / h1.
            # We collect all, deduplicate, then score.
            candidates_raw: list[str] = []

            # 1. og:title (best for single-article pages)
            for og_pat in [
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']{10,150})["\']',
                r'<meta[^>]+content=["\']([^"\']{10,150})["\'][^>]+property=["\']og:title["\']',
            ]:
                og_m = re.search(og_pat, html, re.IGNORECASE)
                if og_m:
                    candidates_raw.append(og_m.group(1).strip())
                    break

            # 2. <h2> tags — best for category/listing pages (article card titles)
            h2_matches = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.IGNORECASE | re.DOTALL)
            for raw_h2 in h2_matches[:20]:
                clean = re.sub(r"<[^>]+>", " ", raw_h2)
                clean = " ".join(clean.split()).strip()
                if len(clean) >= 15:
                    candidates_raw.append(clean)

            # 3. <h3> tags — sub-headlines, card titles on news listing pages
            h3_matches = re.findall(r"<h3[^>]*>(.*?)</h3>", html, re.IGNORECASE | re.DOTALL)
            for raw_h3 in h3_matches[:20]:
                clean = re.sub(r"<[^>]+>", " ", raw_h3)
                clean = " ".join(clean.split()).strip()
                if len(clean) >= 15:
                    candidates_raw.append(clean)

            # 4. <h1> tags
            h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
            for raw_h1 in h1_matches[:5]:
                clean = re.sub(r"<[^>]+>", " ", raw_h1)
                clean = " ".join(clean.split()).strip()
                if len(clean) >= 15:
                    candidates_raw.append(clean)

            # 5. <title> tag (last resort — often has site name appended)
            title_m = re.search(r"<title[^>]*>([^<]{5,200})</title>", html, re.IGNORECASE)
            if title_m:
                # Strip common " | SiteName" suffixes
                t = title_m.group(1).strip()
                for sep in [" | ", " - ", " – ", " — ", " · "]:
                    if sep in t:
                        t = t.split(sep)[0].strip()
                if len(t) >= 15:
                    candidates_raw.append(t)

            # ── Baseline engagement scores — adjusted by source type ───────────
            _type_scores = {
                "news":       (78, 75, 72, 76),
                "research":   (74, 72, 68, 85),
                "official":   (76, 74, 70, 82),
                "technical":  (72, 70, 65, 80),
                "analysis":   (75, 73, 74, 78),
                "newsletter": (80, 77, 82, 75),
            }
            base_eng, base_gs, base_emo, base_sm = _type_scores.get(
                source_type, (78, 75, 72, 76)
            )

            # ── Clean, filter, score and emit candidates ───────────────────────
            page_hits = 0
            for raw_title in candidates_raw:
                # ── HTML entity decode — named + numeric (decimal + hex) ─────────
                # Step 1: named entities (most common)
                for ent, ch in [
                    ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&apos;", "'"), ("&nbsp;", " "),
                    ("&mdash;", "—"), ("&ndash;", "–"), ("&hellip;", "…"),
                    ("&lsquo;", "'"), ("&rsquo;", "'"),
                    ("&ldquo;", '"'), ("&rdquo;", '"'),
                    ("&copy;", "©"), ("&reg;", "®"), ("&trade;", "™"),
                ]:
                    raw_title = raw_title.replace(ent, ch)
                # Step 2: numeric decimal entities  &#NNNN; → chr(NNNN)
                raw_title = re.sub(
                    r"&#(\d+);",
                    lambda m: chr(int(m.group(1))),
                    raw_title,
                )
                # Step 3: numeric hex entities  &#xNNNN; → chr(0xNNNN)
                raw_title = re.sub(
                    r"&#x([0-9a-fA-F]+);",
                    lambda m: chr(int(m.group(1), 16)),
                    raw_title,
                )

                # Strip residual HTML and normalise whitespace
                raw_title = re.sub(r"<[^>]+>", "", raw_title)
                raw_title = " ".join(raw_title.split()).strip()

                tl = raw_title.lower()

                # ── Length guard ───────────────────────────────────────────────
                if not (20 <= len(raw_title) <= 200):
                    continue

                # ── Exact noise match ──────────────────────────────────────────
                if tl in _NOISE_EXACT:
                    continue

                # ── Starts-with noise ──────────────────────────────────────────
                if any(tl.startswith(p) for p in _NOISE_STARTSWITH):
                    continue

                # ── Contains noise substring ───────────────────────────────────
                if any(p in tl for p in _NOISE_CONTAINS):
                    continue

                # ── Site-name suffix pattern (e.g. "AI News | Latest AI News") ─
                if _SITE_SUFFIX_RE.match(raw_title):
                    continue

                # ── Must contain at least one real word (>3 chars) beyond digits ─
                real_words = [w for w in re.findall(r"[a-zA-Z]{4,}", raw_title)]
                if len(real_words) < 3:
                    continue

                # ── Reject titles that are mostly punctuation / list fragments ──
                # e.g. "Expo , In-Person Events" — comma-separated label fragments
                # Heuristic: if >25% of chars are non-alpha non-space → skip
                non_alpha = len(re.findall(r"[^a-zA-Z0-9\s\-'\"\.!?]", raw_title))
                if len(raw_title) > 0 and non_alpha / len(raw_title) > 0.25:
                    continue

                # ── Deduplicate ────────────────────────────────────────────────
                if tl in seen_titles:
                    continue
                seen_titles.add(tl)

                # ── All-caps section headers / UI labels ───────────────────────
                # e.g. "EDITORIAL SPOTLIGHT FOCUS", "TRENDING NOW", "IN FOCUS"
                alpha_words = re.findall(r"[A-Za-z]+", raw_title)
                if alpha_words and all(w.isupper() for w in alpha_words):
                    seen_titles.discard(tl)
                    continue

                # Count how many controversy/emotion words appear in the title.
                title_words = set(re.findall(r"[a-z]+", tl))
                controversy_hits = len(title_words & _CONTROVERSY_WORDS)

                # Boost: each controversy word adds ~3 pts (capped at +20)
                boost = min(20, controversy_hits * 3)

                # Question titles get an extra +5 (high debate potential)
                if raw_title.rstrip().endswith("?"):
                    boost = min(25, boost + 5)

                # Titles with a year reference (recency signal) +3
                if re.search(r"\b20(2[4-9]|3\d)\b", raw_title):
                    boost = min(25, boost + 3)

                eng = min(100, base_eng + boost)
                gs  = min(100, base_gs  + boost)
                emo = min(100, base_emo + boost)
                sm  = min(100, base_sm  + boost)

                results.append({
                    "title":           raw_title,
                    "niche":           niche,
                    "platforms":       ["scraping_url"],
                    "source_type":     source_type,
                    "source_label":    label,
                    "engagement":      eng,
                    "growth_speed":    gs,
                    "emotional":       emo,
                    "search_momentum": sm,
                })
                page_hits += 1
                if len(results) >= n * 4:
                    break

            print(f"[Scout/scraping_url] {label}: {page_hits} candidates extracted.")

        if not results:
            print("[Scout/scraping_url] No usable titles found across all URLs.")
        if niches:
            results = _remap_niches(results, niches)
        return results

    def _fetch_youtube(self, niches: list[str], api_key: str, n: int) -> list[dict]:
        results: list[dict] = []
        seen_ids: set[str] = set()
        for cat_id in (_yt_categories_for_niches(niches) or ["28"])[:3]:
            try:
                p = urllib.parse.urlencode({
                    "part": "id", "chart": "mostPopular", "regionCode": "US",
                    "videoCategoryId": cat_id, "maxResults": min(n, 25), "key": api_key,
                })
                data = self._http_get_json(f"https://www.googleapis.com/youtube/v3/videos?{p}")
                ids  = [i["id"] for i in data.get("items", []) if i.get("id") not in seen_ids]
                if not ids:
                    continue
                seen_ids.update(ids)
                p2   = urllib.parse.urlencode({"part": "snippet,statistics", "id": ",".join(ids), "key": api_key})
                data2 = self._http_get_json(f"https://www.googleapis.com/youtube/v3/videos?{p2}")
                nl   = _niche_for_yt_cat(cat_id, niches)
                for item in data2.get("items", []):
                    sn   = item.get("snippet", {})
                    st   = item.get("statistics", {})
                    t    = sn.get("title", "").strip()
                    v    = int(st.get("viewCount",    0))
                    li   = int(st.get("likeCount",    0))
                    co   = int(st.get("commentCount", 0))
                    if not t or v < 10_000:
                        continue
                    results.append({
                        "title": t, "niche": nl, "platforms": ["YouTube"],
                        "engagement":      self._norm_log(v,  10_000, 50_000_000),
                        "growth_speed":    self._norm_log(li, 100,    500_000),
                        "emotional":       self._norm_log(co, 50,     200_000),
                        "search_momentum": self._norm_log(v,  10_000, 50_000_000),
                    })
            except Exception as exc:
                print(f"[Scout/YouTube] cat={cat_id}: {exc}")
        return results

    def _fetch_youtube_rss(self, niches: list[str], n: int) -> list[dict]:
        results: list[dict] = []
        seen: set[str] = set()
        for cat_id in (_yt_categories_for_niches(niches) or ["28"])[:2]:
            try:
                url = (
                    "https://www.youtube.com/feeds/videos.xml"
                    f"?chart=trending&videoCategoryId={cat_id}&regionCode=US"
                )
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0 (compatible; VideoFactory/1.0)"}
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    xml_bytes = resp.read()
                root = ET.fromstring(xml_bytes)
                ns   = {"atom": "http://www.w3.org/2005/Atom"}
                nl   = _niche_for_yt_cat(cat_id, niches)
                for rank, entry in enumerate(root.findall("atom:entry", ns)[:n], start=1):
                    tel   = entry.find("atom:title", ns)
                    title = (tel.text or "").strip() if tel is not None else ""
                    if not title or title.lower() in seen:
                        continue
                    seen.add(title.lower())
                    rs = max(55, 100 - rank * 3)
                    results.append({
                        "title": title, "niche": nl, "platforms": ["YouTube"],
                        "engagement": rs, "growth_speed": rs - 5,
                        "emotional": rs - 10, "search_momentum": rs,
                    })
            except Exception as exc:
                print(f"[Scout/YouTube-RSS] cat={cat_id}: {exc}")
        if results:
            print(f"[Scout/YouTube-RSS] {len(results)} titles (no API key).")
        return results

    def _fetch_instagram(self, niches: list[str], rapid_key: str, n: int) -> list[dict]:
        results: list[dict] = []
        for tag in _hashtags_for_niches_dynamic(niches)[:4]:
            try:
                params = urllib.parse.urlencode({"hashtag": tag})
                data   = self._http_get_json(
                    f"https://{_RAPID_HOST_IG}{_RAPID_EP_IG}?{params}",
                    headers={"x-rapidapi-host": _RAPID_HOST_IG, "x-rapidapi-key": rapid_key},
                )
                sections = (
                    data.get("data", {}).get("top",    {}).get("sections", [])
                    or data.get("data", {}).get("recent", {}).get("sections", [])
                    or []
                )
                for section in sections[:n]:
                    media = (
                        section.get("layout_content", {})
                               .get("medias", [{}])[0].get("media", {})
                    )
                    cap   = (media.get("caption") or {}).get("text", "").strip()
                    title = self._caption_to_title(cap)
                    if not title:
                        continue
                    li = int(media.get("like_count", 0))
                    co = int(media.get("comment_count", 0))
                    pl = int(media.get("play_count") or media.get("view_count") or 0)
                    results.append({
                        "title": title,
                        "niche": _niche_for_tag_dynamic(tag, niches),
                        "platforms": ["instagram"],
                        "engagement":      self._norm_log(li, 500,   1_000_000),
                        "growth_speed":    self._norm_log(pl, 1_000, 10_000_000),
                        "emotional":       self._norm_log(co, 10,    50_000),
                        "search_momentum": self._norm_log(li, 500,   1_000_000),
                    })
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    raise _RapidAPINotSubscribed(
                        f"Instagram 403 — subscribe to {_RAPID_HOST_IG} on rapidapi.com"
                    )
                print(f"[Scout/Instagram] tag=#{tag}: HTTP {exc.code}")
            except Exception as exc:
                print(f"[Scout/Instagram] tag=#{tag}: {exc}")
        return results

    def _fetch_linkedin(self, niches: list[str], rapid_key: str, n: int) -> list[dict]:
        results: list[dict] = []
        for kw in niches[:3]:
            try:
                params = urllib.parse.urlencode({
                    "keywords": kw, "sortBy": "relevance", "datePosted": "past-week",
                })
                data = self._http_get_json(
                    f"https://{_RAPID_HOST_LINKEDIN}{_RAPID_EP_LINKEDIN}?{params}",
                    headers={"x-rapidapi-host": _RAPID_HOST_LINKEDIN, "x-rapidapi-key": rapid_key},
                )
                posts = data.get("data", data.get("items", data.get("results", [])))
                if isinstance(posts, dict):
                    posts = posts.get("items", [])
                for post in (posts or [])[:n]:
                    text  = (post.get("text") or post.get("commentary") or "").strip()
                    title = self._caption_to_title(text)
                    if not title:
                        continue
                    re_   = int(post.get("totalReactionCount") or post.get("likeCount") or post.get("numLikes", 0))
                    co    = int(post.get("commentsCount") or post.get("numComments", 0))
                    rep   = int(post.get("repostsCount")  or post.get("numShares",   0))
                    results.append({
                        "title": title, "niche": kw, "platforms": ["LinkedIn"],
                        "engagement":      self._norm_log(re_,  50, 100_000),
                        "growth_speed":    self._norm_log(rep,  5,  10_000),
                        "emotional":       self._norm_log(co,   10, 20_000),
                        "search_momentum": self._norm_log(re_,  50, 100_000),
                    })
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    raise _RapidAPINotSubscribed(
                        f"LinkedIn 403 — subscribe to {_RAPID_HOST_LINKEDIN} on rapidapi.com"
                    )
                print(f"[Scout/LinkedIn] kw={kw}: HTTP {exc.code}")
            except Exception as exc:
                print(f"[Scout/LinkedIn] kw={kw}: {exc}")
        return results

    def _fetch_facebook(self, niches: list[str], rapid_key: str, n: int) -> list[dict]:
        results: list[dict] = []
        for kw in niches[:3]:
            try:
                params = urllib.parse.urlencode({"query": kw, "count": min(n, 10)})
                data   = self._http_get_json(
                    f"https://{_RAPID_HOST_FB}{_RAPID_EP_FB}?{params}",
                    headers={"x-rapidapi-host": _RAPID_HOST_FB, "x-rapidapi-key": rapid_key},
                )
                posts = data.get("data", data.get("posts", data.get("results", [])))
                for post in (posts or [])[:n]:
                    text  = (post.get("message") or post.get("text") or post.get("story") or "").strip()
                    title = self._caption_to_title(text)
                    if not title:
                        continue
                    _r = post.get("reactions", {})
                    re_ = int(
                        _r.get("summary", {}).get("total_count", 0) if isinstance(_r, dict)
                        else post.get("reactionCount", post.get("likeCount", 0))
                    )
                    _c = post.get("comments", {})
                    co  = int(
                        _c.get("summary", {}).get("total_count", 0) if isinstance(_c, dict)
                        else post.get("commentCount", 0)
                    )
                    _s = post.get("shares", {})
                    sh  = int(
                        _s.get("count", 0) if isinstance(_s, dict)
                        else post.get("shareCount", 0)
                    )
                    results.append({
                        "title": title, "niche": kw, "platforms": ["Facebook"],
                        "engagement":      self._norm_log(re_, 100, 500_000),
                        "growth_speed":    self._norm_log(sh,  10,  50_000),
                        "emotional":       self._norm_log(co,  20,  100_000),
                        "search_momentum": self._norm_log(re_, 100, 500_000),
                    })
            except urllib.error.HTTPError as exc:
                if exc.code == 403:
                    raise _RapidAPINotSubscribed(
                        f"Facebook 403 — subscribe to {_RAPID_HOST_FB} on rapidapi.com"
                    )
                print(f"[Scout/Facebook] kw={kw}: HTTP {exc.code}")
            except Exception as exc:
                print(f"[Scout/Facebook] kw={kw}: {exc}")
        return results

    # =========================================================================
    # LAYER 2 — LLM TOPIC GENERATION
    # =========================================================================

    def _generate_via_llm(
        self,
        niches: list[str],
        platforms: list[str],
        llm_model: str | None,
        n_topics: int,
    ) -> list[dict]:
        model      = llm_model or os.environ.get("LITELLM_MODEL", "deepseek/deepseek-chat")
        niches_str = ", ".join(niches)
        today      = datetime.now(timezone.utc).strftime("%B %d, %Y")
        ex_niche   = niches[0] if niches else "AI"

        prompt = f"""Today is {today}.

You are a viral content strategist for a YouTube/LinkedIn channel covering: {niches_str}.

Find {n_topics} topics ACTIVELY TRENDING RIGHT NOW (past 2-4 weeks).
Cover ALL these niches: {niches_str}

Rules:
- Each must be a punchy opinionated VIDEO TITLE
- Prioritise controversy, fear, curiosity, strong opinions
- Timely angles only — no evergreen basics

Return ONLY a valid JSON array starting with [ and ending with ].
[
  {{
    "title": "Is {ex_niche} Actually Creating or Destroying Jobs in 2026?",
    "niche": "{ex_niche}",
    "platforms": ["YouTube", "LinkedIn"],
    "engagement": 91,
    "growth_speed": 88,
    "emotional": 87,
    "search_momentum": 90
  }}
]
Score fields 0-100. Return exactly {n_topics} items. JSON only."""

        _WEB_SEARCH_PROVIDERS = {"anthropic", "claude", "openai"}
        provider = model.split("/")[0].lower() if "/" in model else ""
        call_kwargs: dict = {
            "model":      model,
            "messages":   [{"role": "user", "content": prompt}],
            "max_tokens": 4096,
        }
        if any(p in provider for p in _WEB_SEARCH_PROVIDERS):
            call_kwargs["tools"] = [{"type": "web_search_20250305", "name": "web_search"}]

        resp    = _llm_completion(**call_kwargs)
        message = resp.choices[0].message

        raw_text = ""
        if hasattr(message, "content") and message.content:
            if isinstance(message.content, str):
                raw_text = message.content
            elif isinstance(message.content, list):
                for block in message.content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        raw_text += block.get("text", "")
                    elif hasattr(block, "text"):
                        raw_text += block.text or ""
        if not raw_text:
            raw_text = str(message)

        # Normalise smart quotes
        raw_text = (raw_text
                    .replace("\u2018", "'").replace("\u2019", "'")
                    .replace("\u201c", '"').replace("\u201d", '"'))
        raw_text = re.sub(r"```(?:json)?", "", raw_text).strip().strip("`").strip()

        json_str = self._extract_json_array(raw_text) or self._salvage_partial_json(raw_text)
        if not json_str:
            raise ValueError(f"LLM returned no parseable JSON. Got: {raw_text[:300]}")

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM JSON parse error: {e}. Snippet: {json_str[:300]}")

        validated: list[dict] = []
        for t in parsed:
            if not isinstance(t, dict) or not t.get("title"):
                continue
            validated.append({
                "title":           str(t["title"]).strip(),
                "niche":           str(t.get("niche", niches[0] if niches else "General")),
                "platforms":       list(t.get("platforms", platforms[:2])),
                "engagement":      min(100, max(0, int(t.get("engagement",      80)))),
                "growth_speed":    min(100, max(0, int(t.get("growth_speed",    80)))),
                "emotional":       min(100, max(0, int(t.get("emotional",       80)))),
                "search_momentum": min(100, max(0, int(t.get("search_momentum", 80)))),
            })

        if not validated:
            raise ValueError("LLM returned no valid topic objects.")

        print(f"[Scout] LLM returned {len(validated)} topics via {model}.")
        return validated

    # =========================================================================
    # SCORING
    # =========================================================================

    def _score_topic(self, raw: dict, niches: list[str]) -> dict:
        title       = raw["title"]
        tl          = title.lower()
        engagement   = raw.get("engagement",      70)
        growth_speed = raw.get("growth_speed",    70)
        emotional    = raw.get("emotional",        70)
        search_mom   = raw.get("search_momentum", 70)

        virality     = int(0.30 * engagement + 0.25 * growth_speed
                           + 0.25 * emotional + 0.20 * search_mom)
        debate_hits  = sum(1 for t in _DEBATE_TRIGGERS if t in tl)
        debate_score = min(100, 40 + debate_hits * 15 + max(0, emotional - 70))

        format_scores: dict[str, int] = {}
        for fmt, signals in _FORMAT_SIGNALS.items():
            hits = sum(1 for s in signals if s in tl)
            format_scores[fmt] = min(100, 30 + hits * 20)
        format_scores["debate"] = max(format_scores.get("debate", 0), debate_score)
        best_format = max(format_scores, key=lambda k: format_scores[k])

        hook = (
            "Fear / Controversy" if emotional >= 90 else
            "Curiosity / Surprise" if emotional >= 80 else
            "Debate / Opinion" if emotional >= 70 else
            "Informational"
        )

        return {
            "title":          title,
            "niche":          raw.get("niche", niches[0] if niches else "General"),
            "platforms":      raw.get("platforms", []),
            "virality_score": virality,
            "debate_score":   int(debate_score),
            "format_scores":  format_scores,
            "best_format":    best_format,
            "emotional_hook": hook,
            "raw_signals":    {
                "engagement": engagement, "growth_speed": growth_speed,
                "emotional": emotional, "search_momentum": search_mom,
            },
            "status":        "NEW",
            "discovered_at": "",
            "selected_at":   None,
            "used_at":       None,
            "performance":   {},
        }

    # =========================================================================
    # FILE I/O
    # =========================================================================

    @staticmethod
    def _decode_html_entities(text: str) -> str:
        """Decode HTML entities in a string — named + decimal + hex numeric."""
        for ent, ch in [
            ("&amp;", "&"), ("&quot;", '"'), ("&apos;", "'"), ("&nbsp;", " "),
            ("&mdash;", "—"), ("&ndash;", "–"), ("&hellip;", "…"),
            ("&lsquo;", "'"), ("&rsquo;", "'"), ("&ldquo;", '"'), ("&rdquo;", '"'),
            ("&copy;", "©"), ("&reg;", "®"), ("&trade;", "™"),
        ]:
            text = text.replace(ent, ch)
        # &#NNNN; decimal
        text = re.sub(r"&#(\d+);",          lambda m: chr(int(m.group(1))),        text)
        # &#xNNNN; hex
        text = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), text)
        return text

    @staticmethod
    def _load_file(path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                queue   = data.get("queue",   [])
                archive = data.get("archive", [])
            else:
                queue   = data if isinstance(data, list) else []
                archive = []

            # ── Retroactive entity decode ──────────────────────────────────────
            # Any topic titles that entered the queue before the HTML entity fix
            # was applied will still contain raw entities (&#8217; etc.).
            # Decode them here on load so the queue self-heals automatically.
            _needs_save = False
            for entry_list in (queue, archive):
                for item in entry_list:
                    raw = item.get("title", "")
                    if raw and ("&#" in raw or "&amp;" in raw or "&quot;" in raw):
                        # Use the instance method via a temporary call
                        for ent, ch in [
                            ("&amp;","&"),("&quot;",'"'),("&apos;","'"),("&nbsp;"," "),
                            ("&mdash;","—"),("&ndash;","–"),("&hellip;","…"),
                            ("&lsquo;","'"),("&rsquo;","'"),("&ldquo;",'"'),("&rdquo;",'"'),
                        ]:
                            raw = raw.replace(ent, ch)
                        raw = re.sub(r"&#(\d+);",           lambda m: chr(int(m.group(1))),        raw)
                        raw = re.sub(r"&#x([0-9a-fA-F]+);", lambda m: chr(int(m.group(1), 16)), raw)
                        if raw != item["title"]:
                            item["title"] = raw
                            _needs_save = True

            if _needs_save:
                cleaned = sum(
                    1 for el in (queue, archive)
                    for item in el
                    if "&#" not in item.get("title","")
                )
                print(f"[Scout/_load_file] ✅ Retroactive entity decode applied to queue/archive.")

            return {"queue": queue, "archive": archive}
        except Exception:
            return {"queue": [], "archive": []}

    @staticmethod
    def _save_file(path: str, queue: list[dict], archive: list[dict]) -> None:
        """
        Persist topic_memory.json.
        queue   — NO size limit. All UNUSED/IN_PROGRESS topics kept.
        archive — completed topics. main.py populates video_urls after upload:
                  { "youtube": "...", "facebook": "...", "tiktok": "..." }
        """
        os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "queue":   queue,
                "current": None,
                "archive": archive,
                "_updated_at": datetime.now(timezone.utc).isoformat(),
                "_note": (
                    "queue: no size limit — all topics kept. "
                    "archive.video_urls {youtube, facebook, tiktok} set by main.py after upload."
                ),
            }, f, indent=2, ensure_ascii=False)

    # =========================================================================
    # HELPERS
    # =========================================================================

    @staticmethod
    def _extract_json_array(text: str) -> str | None:
        start = text.find("[")
        if start == -1:
            return None
        depth = in_str = escape = False
        depth = 0
        in_str = False
        escape = False
        for i, ch in enumerate(text[start:], start):
            if escape:
                escape = False
                continue
            if ch == "\\" and in_str:
                escape = True
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        return None

    @staticmethod
    def _salvage_partial_json(text: str) -> str | None:
        start = text.find("[")
        if start == -1:
            return None
        fragment = text[start:]
        objects: list[str] = []
        buf = ""
        obj_depth = in_str = escape = False
        obj_depth = 0
        in_str = False
        escape = False
        for ch in fragment:
            if escape:
                escape = False
                buf += ch
                continue
            if ch == "\\" and in_str:
                escape = True
                buf += ch
                continue
            if ch == '"' and not escape:
                in_str = not in_str
                buf += ch
                continue
            if in_str:
                buf += ch
                continue
            if ch == "{":
                obj_depth += 1
                buf += ch
            elif ch == "}":
                obj_depth -= 1
                buf += ch
                if obj_depth == 0 and buf.strip():
                    objects.append(buf.strip())
                    buf = ""
            elif obj_depth > 0:
                buf += ch
        if objects:
            print(f"[Scout] Salvaged {len(objects)} objects from truncated LLM response.")
            return "[" + ",".join(objects) + "]"
        return None

    @staticmethod
    def _http_get_json(url: str, headers: dict | None = None) -> dict:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                raise urllib.error.HTTPError(url, resp.status, "Non-200", {}, None)
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _norm_log(value: int, floor: int, ceil: int) -> int:
        if value <= floor:
            return 0
        if value >= ceil:
            return 100
        return int(100 * math.log(value / floor) / math.log(ceil / floor))

    @staticmethod
    def _caption_to_title(text: str, max_len: int = 100) -> str:
        if not text:
            return ""
        text = re.sub(r"https?://\S+", "", text)
        text = re.sub(r"[#@]\w+", "", text)
        text = " ".join(text.split())
        sentence = re.split(r"[.\n!?]", text)[0].strip()
        if len(sentence) < 15:
            sentence = text[:max_len].strip()
        return sentence[:max_len] if len(sentence) >= 15 else ""

    @staticmethod
    def _age_hours(iso_str: str) -> float:
        if not iso_str:
            return 999.0
        try:
            dt  = datetime.fromisoformat(iso_str)
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now - dt).total_seconds() / 3600
        except Exception:
            return 999.0
