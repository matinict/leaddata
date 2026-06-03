"""
leaddata_reddit.py — Dynamic Reddit Intent Scraper (CF2 Tool)
Fixed 2026-06-02: SSL handling + mirrors + real User-Agent
"""
import logging
import csv
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from typing import Type, List
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

logger = logging.getLogger(__name__)

CSV_FIELDS = [
    "name", "phone", "phone_formatted", "email", "website",
    "address", "location", "category", "source", "keyword",
    "rating", "review_count", "review_snippet",
    "destination_visited", "review_date", "hotel_reviewed",
    "intent_score", "quality_score", "segment", "last_verified",
]

class RedditScrapeInput(BaseModel):
    topic: str = Field(...)
    keywords: List[str] = Field(...)
    output_dir: str = Field(...)
    credentials_file: str = Field(default="")
    subreddits: List[str] = Field(default=None)
    min_post_upvotes: int = Field(default=5)
    post_recency_days: int = Field(default=30)
    max_posts_per_sub: int = Field(default=50)
    skip_if_cached: bool = Field(default=True)

class RedditTravelScraperTool(BaseTool):
    name: str = "leaddata_reddit"
    description: str = "Scrape Reddit for high-intent discussions on ANY topic."
    args_schema: Type[BaseModel] = RedditScrapeInput

    def _run(
        self,
        topic: str,
        keywords: List[str],
        output_dir: str,
        credentials_file: str = "",
        subreddits: List[str] = None,
        min_post_upvotes: int = 5,
        post_recency_days: int = 30,
        max_posts_per_sub: int = 50,
        skip_if_cached: bool = True,
        **kwargs
    ) -> str:

        if not subreddits:
            subreddits = ["smallbusiness"]

        out_dir = Path(output_dir) / "raw"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_raw.csv"

        cache_key = f"reddit_{','.join(subreddits)}_{post_recency_days}d"
        cache_file = out_dir / f".cache_{cache_key}.json"

        if skip_if_cached and cache_file.exists():
            try:
                cache = json.loads(cache_file.read_text())
                if (datetime.now() - datetime.fromisoformat(cache["timestamp"])).days < 1:
                    logger.info(f"⏭️ Skipped Reddit scrape (cached): {len(cache['leads'])} leads")
                    return f"⏭️ Skipped Reddit scrape (cached): {len(cache['leads'])} leads"
            except Exception:
                pass

        leads = []
        # FIX 1: Real browser UA - Reddit blocks bots
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        }
        search_query = " OR ".join(f'"{kw}"' for kw in keywords)

        # FIX 2: Multiple mirrors + SSL fallback
        mirrors = [
            "https://www.reddit.com",
            "https://old.reddit.com",
            "https://np.reddit.com",
            "https://teddit.net",
            "https://libreddit.spike.codes"
        ]

        for sub in subreddits:
            logger.info(f"🔍 Scraping r/{sub} for: {search_query[:80]}...")
            posts_found = False

            for base_url in mirrors:
                try:
                    # FIX 3: verify=False to bypass your CERTIFICATE_VERIFY_FAILED
                    r = requests.get(
                        f"{base_url}/r/{sub}/search.json",
                        params={
                            "q": search_query,
                            "sort": "new",
                            "limit": max_posts_per_sub,
                            "restrict_sr": "true",
                            "type": "link"
                        },
                        headers=headers,
                        timeout=15,
                        verify=False # <-- critical for your environment
                    )

                    if r.status_code == 429:
                        logger.warning(f"⚠️ Rate limit on {base_url}, sleeping 5s")
                        time.sleep(5)
                        continue
                    if r.status_code == 403:
                        logger.warning(f"⚠️ {base_url} blocked (403), trying next...")
                        continue
                    if r.status_code!= 200:
                        continue

                    posts = r.json().get("data", {}).get("children", [])
                    posts_found = True

                    for post in posts:
                        data = post.get("data", {})
                        created_utc = datetime.fromtimestamp(data.get("created_utc", 0))
                        if (datetime.now() - created_utc).days > post_recency_days:
                            continue
                        if data.get("score", 0) < min_post_upvotes:
                            continue

                        author = data.get("author", "")
                        if not author or author == "[deleted]":
                            continue

                        post_url = f"https://reddit.com{data.get('permalink', '')}"
                        title = data.get("title", "")
                        selftext = data.get("selftext", "")

                        leads.append({
                            "name": author,
                            "phone": "",
                            "phone_formatted": "",
                            "email": "",
                            "website": post_url,
                            "address": "",
                            "location": "",
                            "category": topic,
                            "source": "reddit_planner",
                            "keyword": sub,
                            "rating": data.get("score", 0),
                            "review_count": data.get("num_comments", 0),
                            "review_snippet": f"{title} {selftext}"[:200],
                            "destination_visited": "",
                            "review_date": created_utc.isoformat(),
                            "hotel_reviewed": "",
                            "intent_score": 85,
                            "quality_score": "",
                            "segment": "",
                            "last_verified": datetime.now().strftime("%Y-%m-%d"),
                        })
                    break # success, stop trying mirrors

                except requests.exceptions.SSLError as e:
                    logger.warning(f"⚠️ SSL error on {base_url}: {str(e)[:60]}... trying next")
                    continue
                except Exception as e:
                    logger.warning(f"⚠️ Error on {base_url}: {e}")
                    continue

            if not posts_found:
                logger.warning(f"⚠️ All Reddit endpoints failed for r/{sub}")

        if not leads:
            logger.warning("⚠️ No Reddit leads found matching criteria")
            return "⚠️ No Reddit leads found matching criteria"

        # Deduplicate
        existing_urls = set()
        if out_file.exists():
            try:
                with open(out_file, 'r', encoding='utf-8') as f:
                    for row in csv.DictReader(f):
                        if row.get("source") == "reddit_planner" and row.get("website"):
                            existing_urls.add(row["website"])
            except Exception:
                pass

        new_leads = [l for l in leads if l["website"] not in existing_urls]

        try:
            write_header = not out_file.exists() or out_file.stat().st_size == 0
            with open(out_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction='ignore')
                if write_header:
                    writer.writeheader()
                writer.writerows(new_leads)
        except Exception as e:
            logger.error(f"❌ Failed to write Reddit leads: {e}")
            return f"❌ Failed to write leads to CSV."

        try:
            cache_file.write_text(json.dumps({
                "timestamp": datetime.now().isoformat(),
                "leads": [l["website"] for l in new_leads]
            }))
        except Exception:
            pass

        success_msg = f"✓ Added {len(new_leads)} Reddit leads to leads_raw.csv"
        logger.info(success_msg)
        return success_msg
