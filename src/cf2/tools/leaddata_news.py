"""
leaddata_news.py — Google News Trend Scraper (CF2 Tool)
Output: {output_dir}/raw/leads_raw.csv
"""
import logging
import csv
import time
import requests
from pathlib import Path
from typing import Type, List
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

logger = logging.getLogger(__name__)
SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
CSV_FIELDS = [
    "name", "phone", "phone_formatted", "email", "website",
    "address", "location", "category", "source", "keyword",
    "rating", "review_count", "review_snippet",
    "destination_visited", "review_date", "hotel_reviewed",
    "intent_score", "quality_score", "segment", "last_verified",
]

def _load_api_key(credentials_file: str) -> str:
    if not credentials_file: return ""
    p = Path(credentials_file).expanduser()
    if not p.exists(): return ""
    try:
        import json
        data = json.loads(p.read_text(encoding="utf-8"))
        key = str(data.get("api_key") or "").strip()
        if key: return key
        for k in data.get("keys", []):
            if k.get("status") == "active" and k.get("api_key"): return str(k["api_key"]).strip()
        return ""
    except Exception: return ""

class NewsTrendInput(BaseModel):
    topic: str = Field(...)
    keywords: List[str] = Field(...)
    output_dir: str = Field(...)
    credentials_file: str = Field(default="")
    max_results_per_keyword: int = Field(default=10)

class GoogleTrendsTool(BaseTool):
    name: str = "leaddata_trends"
    description: str = "Scrape Google News for trending articles related to the topic."
    args_schema: Type[BaseModel] = NewsTrendInput

    def _run(self, topic: str, keywords: List[str], output_dir: str,
             credentials_file: str = "", max_results_per_keyword: int = 10, **kwargs) -> str:

        out_dir = Path(output_dir) / "raw"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_raw.csv"
        api_key = _load_api_key(credentials_file)

        if not api_key: return "❌ No SerpAPI key found."

        leads = []
        for kw in keywords[:3]:
            logger.info(f"📰 Searching News for: {kw}")
            try:
                # Use tbm=nws for Google News
                r = requests.get(SERPAPI_ENDPOINT, params={
                    "q": kw, "engine": "google", "tbm": "nws",
                    "api_key": api_key, "num": max_results_per_keyword
                }, timeout=30)

                if r.status_code != 200: continue
                results = r.json().get("news_results", [])

                for res in results:
                    leads.append({
                        "name": res.get("source", "News Outlet"),
                        "phone": "", "phone_formatted": "", "email": "",
                        "website": res.get("link", ""),
                        "address": "", "location": "",
                        "category": "Trend/News", "source": "google_trends",
                        "keyword": kw, "rating": 0, "review_count": 0,
                        "review_snippet": res.get("title", ""),
                        "destination_visited": "", "review_date": res.get("date", "")[:10],
                        "hotel_reviewed": "", "intent_score": 10, # Very low intent, high context
                        "quality_score": "", "segment": "",
                        "last_verified": time.strftime("%Y-%m-%d")
                    })
                time.sleep(1.0)
            except Exception as e:
                logger.error(f"News search error: {e}")

        if not leads: return "⚠️ No news trends found"

        write_header = not out_file.exists() or out_file.stat().st_size == 0
        with open(out_file, 'a', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
            if write_header: w.writeheader()
            w.writerows(leads)

        return f"✓ Added {len(leads)} trend/news signals"
