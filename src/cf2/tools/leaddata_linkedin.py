"""
leaddata_linkedin.py — LinkedIn Company Directory Scraper (CF2 Tool)
Source: Google Search targeting site:linkedin.com/company
Output: {output_dir}/raw/leads_raw.csv
"""
import logging
import csv
import json
import time
import re
import requests
from pathlib import Path
from typing import Type, List
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

logger = logging.getLogger(__name__)
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# Standard schema used across all CF2 lead tools
CSV_FIELDS = [
    "name", "phone", "phone_formatted", "email", "website",
    "address", "location", "category", "source", "keyword",
    "rating", "review_count", "review_snippet",
    "destination_visited", "review_date", "hotel_reviewed",
    "intent_score", "quality_score", "segment", "last_verified",
]

def _load_api_key(credentials_file: str) -> str:
    """Load SerpAPI key from JSON credentials file (CF2 Standard Format)."""
    if not credentials_file: return ""
    p = Path(credentials_file).expanduser()
    if not p.exists(): return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        key = str(data.get("api_key") or "").strip()
        if key: return key
        for k in data.get("keys", []):
            if k.get("status") == "active" and k.get("api_key"):
                return str(k["api_key"]).strip()
        return ""
    except Exception:
        return ""

class LinkedInScraperInput(BaseModel):
    topic: str = Field(...)
    keywords: List[str] = Field(...)
    output_dir: str = Field(...)
    credentials_file: str = Field(default="")
    max_results_per_keyword: int = Field(default=20)
    skip_if_cached: bool = Field(default=True)

class LinkedInScraperTool(BaseTool):
    name: str = "leaddata_linkedin"
    description: str = "Scrape LinkedIn company directories for B2B leads."
    args_schema: Type[BaseModel] = LinkedInScraperInput

    def _run(self, topic: str, keywords: List[str], output_dir: str,
             credentials_file: str = "", max_results_per_keyword: int = 20,
             skip_if_cached: bool = True, **kwargs) -> str:

        out_dir = Path(output_dir) / "raw"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_raw.csv"
        api_key = _load_api_key(credentials_file)

        if not api_key:
            logger.error("❌ No SerpAPI key found for LinkedIn scrape.")
            return "❌ No SerpAPI key found."

        leads = []
        for kw in keywords[:5]: # Limit to prevent API exhaustion
            logger.info(f"👔 Searching LinkedIn for: {kw[:60]}...")
            try:
                r = requests.get(SERPAPI_ENDPOINT, params={
                    "q": f'"{kw}" site:linkedin.com/company',
                    "api_key": api_key, "num": max_results_per_keyword, "hl": "en"
                }, timeout=30)

                if r.status_code != 200:
                    logger.warning(f"⚠️ HTTP {r.status_code} for {kw}")
                    continue

                results = r.json().get("organic_results", [])

                for res in results:
                    snippet = res.get("snippet", "")
                    link = res.get("link", "")
                    # Clean up the title (usually has " | LinkedIn" at the end)
                    title = res.get("title", "").replace(" | LinkedIn", "").strip()

                    # Extract industry from snippet if possible
                    industry = "B2B Company"
                    industry_match = re.search(r'(\d+[,]?\d*\s*employees?|\bIT\b|\bFinancial\b|\bConstruction\b|\bSoftware\b)', snippet, re.IGNORECASE)
                    if industry_match: industry = industry_match.group(0)

                    leads.append({
                        "name": title,
                        "phone": "",
                        "phone_formatted": "",
                        "email": "",
                        "website": link,
                        "address": "",
                        "location": "",
                        "category": industry,
                        "source": "linkedin_company",
                        "keyword": kw,
                        "rating": 0,
                        "review_count": 0,
                        "review_snippet": snippet[:200],
                        "destination_visited": "",
                        "review_date": "",
                        "hotel_reviewed": "",
                        "intent_score": 20, # Low intent, high quality data
                        "quality_score": "",
                        "segment": "",
                        "last_verified": time.strftime("%Y-%m-%d")
                    })
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"❌ LinkedIn search error: {e}")

        if not leads:
            logger.warning("⚠️ No LinkedIn companies found")
            return "⚠️ No LinkedIn companies found"

        # Append to CSV
        try:
            write_header = not out_file.exists() or out_file.stat().st_size == 0
            with open(out_file, 'a', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
                if write_header: w.writeheader()
                w.writerows(leads)
        except Exception as e:
            logger.error(f"❌ Failed to write LinkedIn leads: {e}")
            return f"❌ Failed to write leads to CSV."

        success_msg = f"✓ Added {len(leads)} LinkedIn companies"
        logger.info(success_msg)
        return success_msg
