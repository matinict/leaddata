"""
leaddata_intent.py — Dynamic Topic-Oriented Intent Detector (CF2 Tool)

Replaces the hardcoded travel intent tool. This version dynamically searches
for ANY topic (equipment, SaaS, real estate, travel, etc.) to find people
exhibiting high buying/research intent on forums, Reddit, and Q&A sites.

Input:  topic (e.g., "Commercial Truck Leasing"), keywords
Output: {output_dir}/raw/leads_raw.csv (Appends to existing pipeline)

Rule 16: Single output file per tool (appends to raw).
Rule 32: Smart Skip mandatory.
Rule 39: API key resolved via credentials_file.
"""

import logging
from pathlib import Path
from typing import Type, List, Dict, Any, Set
import csv
import json
import re
import time
import requests
from datetime import datetime
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

# Initialize standard CF2 logger
logger = logging.getLogger(__name__)

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# Universal buyer intent modifiers (applies to ANY industry/topic)
INTENT_PHRASES = {
    "high": [
        "looking for", "need recommendations", "how much does", "pricing for",
        "looking to buy", "best company for", "quotes for", "who is the best",
        "need a loan for", "financing options for", "supplier for", "vendor for"
    ],
    "medium": [
        "vs", "compared to", "alternatives to", "reviews of", "is it worth",
        "pros and cons", "experience with", "thinking about buying", "thinking about switching"
    ],
    "low": [
        "what is", "how to", "guide to", "basics of", "meaning of"
    ]
}

CSV_FIELDS = [
    "name", "phone", "phone_formatted", "email", "website",
    "address", "location", "category", "source", "keyword",
    "rating", "review_count", "review_snippet",
    "destination_visited", "review_date", "hotel_reviewed",
    "intent_score", "quality_score", "segment", "last_verified",
]


class IntentSearchInput(BaseModel):
    topic: str = Field(...)
    keywords: List[str] = Field(...)
    output_dir: str = Field(...)
    credentials_file: str = Field(default="")
    max_results_per_keyword: int = Field(default=10)
    skip_if_cached: bool = Field(default=True)


def _load_api_key(credentials_file: str) -> str:
    """Load SerpAPI key from JSON credentials file (CF2 Standard Format)."""
    if not credentials_file: return ""
    p = Path(credentials_file).expanduser()
    if not p.exists(): return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        # Flat format check
        key = str(data.get("api_key") or "").strip()
        if key: return key
        # CF2 Multi-key array format (matches your exact JSON structure)
        for k in data.get("keys", []):
            if k.get("status") == "active" and k.get("api_key"):
                return str(k["api_key"]).strip()
        return ""
    except Exception:
        return ""


def _extract_author(text: str, url: str) -> str:
    reddit_match = re.search(r'reddit\.com/user/([^/]+)/', url)
    if reddit_match: return reddit_match.group(1)
    quora_match = re.search(r'quora\.com/profile/([^/]+)', url)
    if quora_match: return quora_match.group(1).replace("-", " ").title()
    asked_match = re.search(r'(?:asked by|posted by|author:)\s*([A-Za-z0-9_]+)', text, re.IGNORECASE)
    if asked_match: return asked_match.group(1)
    return "Forum Poster"


def _calculate_intent_score(text: str) -> int:
    if not text: return 0
    text_lower = text.lower()
    score = 0

    for phrase in INTENT_PHRASES["high"]:
        if phrase in text_lower: score += 40; break
    for phrase in INTENT_PHRASES["medium"]:
        if phrase in text_lower: score += 25; break
    for phrase in INTENT_PHRASES["low"]:
        if phrase in text_lower: score += 10; break

    if "?" in text: score += 10
    return min(score, 100)


def _get_existing_urls(path: Path) -> Set[str]:
    urls = set()
    if not path.exists(): return urls
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get("source") == "intent_osint" and row.get("website"):
                    urls.add(row["website"])
    except Exception: pass
    return urls


class LeadDataIntentTool(BaseTool):
    name: str = "leaddata_intent_detector"
    description: str = (
        "Dynamically search forums, Reddit, and Q&A sites for people showing "
        "buying/research intent for ANY given topic and keywords."
    )
    args_schema: Type[BaseModel] = IntentSearchInput

    def _run(
        self,
        topic: str,
        keywords: List[str],
        output_dir: str,
        credentials_file: str = "",
        max_results_per_keyword: int = 10,
        skip_if_cached: bool = True,
        **kwargs  # Catches force_reddit, force_quora, etc. from YAML
    ) -> str:

        out_dir = Path(output_dir) / "raw"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_raw.csv"

        api_key = _load_api_key(credentials_file)
        if not api_key:
            logger.error("No SerpAPI key found. Intent search requires an API key.")
            return "❌ No SerpAPI key found. Intent search requires an API key."

        existing_urls = _get_existing_urls(out_file)
        new_leads = []
        total_queries = 0

        logger.info(f"🧠 Searching for Intent Topic: '{topic}'")

        for kw in keywords:
            if total_queries >= 50:
                logger.warning("API query limit (50) reached.")
                break

            # ── DYNAMIC QUERY BUILDER BASED ON YAML FLAGS ─────────
            force_reddit = kwargs.get("force_reddit", False)
            force_quora = kwargs.get("force_quora", False)

            if force_reddit:
                query = f'"{kw}" (site:reddit.com/r/smallbusiness OR site:reddit.com/r/Entrepreneur OR site:reddit.com/r/trucking OR site:reddit.com/r/construction)'
            elif force_quora:
                query = f'"{kw}" (site:quora.com)'
            else:
                query = f'"{kw}" (site:reddit.com OR site:quora.com OR "forum" OR "thread")'

            try:
                logger.info(f"🔎 Querying: {kw[:60]}...")
                response = requests.get(
                    SERPAPI_ENDPOINT,
                    params={
                        "q": query,
                        "engine": "google",
                        "api_key": api_key,
                        "num": max_results_per_keyword,
                        "tbs": "qdr:m"
                    },
                    timeout=30
                )
                total_queries += 1

                if response.status_code != 200:
                    logger.warning(f"HTTP {response.status_code} for keyword: {kw}")
                    continue

                results = response.json().get("organic_results", [])
                if not results:
                    logger.info(f"No results found for: {kw}")

                for result in results:
                    link = result.get("link", "")
                    if link in existing_urls: continue

                    snippet = result.get("snippet", "")
                    title = result.get("title", "")
                    combined_text = f"{title} {snippet}"

                    intent_score = _calculate_intent_score(combined_text)
                    #if intent_score < 25: continue
                    if intent_score < 15: continue  # Catches more "warm" research-phase leads

                    author = _extract_author(combined_text, link)

                    new_leads.append({
                        "name": author,
                        "phone": "",
                        "phone_formatted": "",
                        "email": "",
                        "website": link,
                        "address": "",
                        "location": "",
                        "category": topic,
                        "source": "intent_osint",
                        "keyword": kw,
                        "rating": 0,
                        "review_count": 0,
                        "review_snippet": snippet[:200],
                        "destination_visited": "",
                        "review_date": datetime.now().strftime("%Y-%m-%d"),
                        "hotel_reviewed": "",
                        "intent_score": intent_score,
                        "quality_score": "",
                        "segment": "",
                        "last_verified": datetime.now().strftime("%Y-%m-%d"),
                    })
                    existing_urls.add(link)
                    logger.debug(f"Found high-intent lead: {author} (Score: {intent_score})")

                time.sleep(1.0)

            except requests.exceptions.Timeout:
                logger.error(f"Timeout while searching for: {kw}")
            except Exception as e:
                logger.error(f"Error searching '{kw}': {e}")
                continue

        if not new_leads:
            logger.warning(f"No high-intent leads found for topic: {topic}")
            return f"⚠️ No high-intent leads found for topic: {topic}"

        try:
            write_header = not out_file.exists() or out_file.stat().st_size == 0
            with open(out_file, 'a', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
                if write_header: w.writeheader()
                w.writerows(new_leads)
        except Exception as e:
            logger.error(f"Failed to write to CSV: {e}")
            return f"❌ Failed to write leads to CSV."

        avg_intent = sum(l["intent_score"] for l in new_leads) / len(new_leads)
        success_msg = (
            f"✓ Added {len(new_leads)} intent leads for '{topic}' → raw/leads_raw.csv | "
            f"Avg Intent Score: {avg_intent:.1f}/100"
        )
        logger.info(success_msg)
        return success_msg
