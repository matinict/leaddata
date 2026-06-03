"""
leaddata_collect.py — Dynamic Global Lead Collection Tool (CF2 Compliant)
Output: {output_dir}/raw/leads_raw.csv

Sources (switchable via config):
  maps:            Fetch BUSINESS listings via SerpAPI Google Maps (Global)
                   → Fields: name, phone, phone_formatted, address, website, location
  maps_reviewers:  Fetch PEOPLE who reviewed hotels/attractions (traveler mining)
                   → Fields: name, location, review_date, hotel_reviewed, review_count
  csv:             Optional fallback for testing only

Global/Dynamic Features:
  - Accepts 'hl' parameter for localized Google Maps results (e.g., 'fr' for France, 'de' for Germany).
  - Dynamic phone prefixing (+1, +44, +33, etc.) passed from the router.
  - Optional lightweight email scraper (scrape_emails=True).
"""
from pathlib import Path
from typing import Type, List, Dict, Any, Tuple
import csv
import json
import re
import time
import requests
from datetime import datetime
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# Strict universal schema expected by downstream normalize/score tools
CSV_FIELDS = [
    # Core identity
    "name", "phone", "phone_formatted", "email", "website",
    "address", "location",
    # Classification
    "category", "source", "keyword",
    # Quality signals
    "rating", "review_count", "review_snippet",
    # Traveler-specific (empty for business leads)
    "destination_visited", "review_date", "hotel_reviewed",
    # Scoring pipeline
    "intent_score", "quality_score", "segment",
    # Metadata
    "last_verified",
]

SUPPORTED_SOURCES = {"maps", "maps_reviewers", "csv"}


# ─────────────────────────────────────────────────────────────────────────────
# Credential helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_api_key(credentials_file: str) -> str:
    """Read api_key from JSON credentials file."""
    if not credentials_file:
        return ""
    p = Path(credentials_file).expanduser()
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        key = data.get("api_key")
        if key:
            return str(key).strip()
        for k in data.get("keys", []):
            if k.get("status") == "active" and k.get("api_key"):
                return str(k["api_key"]).strip()
        return ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Data cleaning & formatting helpers
# ─────────────────────────────────────────────────────────────────────────────

def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")

def _clean_text(value: Any, max_len: int = None) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        value = (
            value.get("text") or value.get("snippet")
            or value.get("description") or value.get("value") or ""
        )
    text = str(value).replace("\n", "  ").replace("\r", "  ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:max_len] if max_len is not None else text

def _to_int(value: Any) -> int:
    if value is None: return 0
    if isinstance(value, bool): return int(value)
    if isinstance(value, (int, float)): return int(value)
    if isinstance(value, dict):
        for key in ["reviews", "review_count", "count", "total", "value", "text"]:
            if key in value:
                parsed = _to_int(value[key])
                if parsed: return parsed
        return 0
    s = str(value).lower().replace(",", "").strip()
    if not s: return 0
    m = re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?\s*reviews?", s)
    if not m: m = re.search(r"(\d+(?:\.\d+)?)\s*([kmb])?", s)
    if not m: return 0
    n = float(m.group(1))
    suffix = (m.group(2) or "").lower()
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    return int(n * multipliers.get(suffix, 1))

def _to_float(value: Any) -> float:
    if value is None: return 0.0
    try: return float(value)
    except (ValueError, TypeError): return 0.0

def _category_to_str(value: Any, default: str = "Business") -> str:
    if value is None: return default
    if isinstance(value, list):
        cleaned = [_clean_text(v) for v in value if _clean_text(v)]
        return ", ".join(cleaned) if cleaned else default
    text = _clean_text(value)
    return text or default

def _format_phone_e164(phone: str, country_prefix: str = "+1") -> str:
    """Format phone to E.164 standard using dynamic country prefix."""
    if not phone: return ""
    cleaned = re.sub(r"\s+", "", phone.strip())
    cleaned = re.sub(r"[^\d+]", "", cleaned)
    if not cleaned: return ""
    if not cleaned.startswith("+"):
        cleaned = cleaned.lstrip("0")
        cleaned = country_prefix + cleaned
    return cleaned

def _phone_is_valid(phone: str) -> bool:
    """Basic check: at least 7 digits."""
    return len(re.sub(r"\D", "", phone)) >= 7

def _scrape_email_from_website(website: str, timeout: int = 5) -> str:
    """Lightweight, fast scrape to find a contact email on a homepage."""
    if not website: return ""
    try:
        if not website.startswith("http"): website = f"https://{website}"
        r = requests.get(website, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        if r.status_code == 200:
            emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', r.text)
            valid = [e for e in emails if not any(x in e.lower() for x in ['wix.com', 'sentry', 'googleapis', 'wordpress.org', 'example.com'])]
            if valid: return valid[0].lower()
    except Exception:
        pass
    return ""


# ─────────────────────────────────────────────────────────────────────────────
# SerpAPI response parsers
# ─────────────────────────────────────────────────────────────────────────────

def _get_local_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict): return []
    for key in ["local_results", "places_results"]:
        value = payload.get(key)
        if isinstance(value, list): return value
        if isinstance(value, dict):
            for subkey in ["places", "results", "items"]:
                subvalue = value.get(subkey)
                if isinstance(subvalue, list): return subvalue
    return []

def _get_reviews_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict): return []
    value = payload.get("reviews")
    if isinstance(value, list): return value
    for key in ["reviews_results", "user_reviews"]:
        value = payload.get(key)
        if isinstance(value, list): return value
        if isinstance(value, dict):
            for subkey in ["reviews", "results", "items"]:
                subvalue = value.get(subkey)
                if isinstance(subvalue, list): return subvalue
    return []

def _place_identifier_params(place: Dict[str, Any]) -> Tuple[Dict[str, str], str]:
    data_id = place.get("data_id")
    place_id = place.get("place_id")
    if data_id: return {"data_id": data_id}, "data_id"
    if place_id: return {"place_id": place_id}, "place_id"
    return {}, ""


# ─────────────────────────────────────────────────────────────────────────────
# Date parsing (traveler mode)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_review_date(date_str: str, recency_days: int = 90) -> bool:
    if not date_str: return True
    s = str(date_str).lower().strip()
    s = re.sub(r"^edited\s+", "", s).strip()
    if not s: return True
    if any(token in s for token in ["just now", "today"]): return True
    if "yesterday" in s: return recency_days >= 1
    m = re.search(r"(\d+|a|an)\s*(second|minute|hour|day|week|month|year)s?\s+ago", s)
    if m:
        num_str, unit = m.groups()
        num = 1 if num_str in {"a", "an"} else int(num_str)
        days_ago = {"second": 0, "minute": 0, "hour": 0, "day": num, "week": num * 7, "month": num * 30, "year": num * 365}.get(unit, 999999)
        return days_ago <= recency_days
    for fmt in ["%B %Y", "%b %Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"]:
        try:
            review_dt = datetime.strptime(s, fmt)
            return (datetime.now() - review_dt).days <= recency_days
        except ValueError: continue
        except Exception: return True
    return True

def _get_user_review_count(user: Dict[str, Any]) -> int:
    if not isinstance(user, dict): return 0
    candidates = [user.get("reviews"), user.get("review_count"), user.get("review_count_text"), user.get("contributor_reviews"), user.get("contributions"), user.get("activity")]
    for c in candidates:
        parsed = _to_int(c)
        if parsed: return parsed
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# CSV I/O
# ─────────────────────────────────────────────────────────────────────────────

def _csv_has_data_rows(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0: return False
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if any(str(cell).strip() for cell in row): return True
        return False
    except Exception: return path.stat().st_size > 0

def _write_leads_csv(path: Path, leads: List[Dict[str, Any]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(leads)


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic schema
# ─────────────────────────────────────────────────────────────────────────────

class LeadDataCollectInput(BaseModel):
    topic: str = Field(...)
    keywords: List[str] = Field(...)
    output_dir: str = Field(...)
    sources: List[str] = Field(default_factory=lambda: ["maps"])
    credentials_file: str = Field(default="")
    api_endpoint: str = Field(default=SERPAPI_ENDPOINT)
    engine: str = Field(default="google_maps")
    search_type: str = Field(default="search")
    hl: str = Field(default="en")  # DYNAMIC: Host language for localized results
    request_timeout: int = Field(default=30)
    max_results_per_keyword: int = Field(default=20)
    skip_if_cached: bool = Field(default=True)
    # ── Business-mode params ──────────────────────────────────────────────
    require_phone: bool = Field(default=True)
    require_website: bool = Field(default=False)
    min_rating: float = Field(default=0.0)
    min_reviews: int = Field(default=0)
    phone_country_prefix: str = Field(default="+1")  # DYNAMIC: Passed from router
    request_delay_seconds: float = Field(default=1.0)
    scrape_emails: bool = Field(default=False)  # Optional global enrichment
    # ── Traveler-mode params ──────────────────────────────────────────────
    reviewer_recency_days: int = Field(default=90)
    reviewer_min_activity: int = Field(default=5)
    # ── CSV fallback ──────────────────────────────────────────────────────
    csv_file: str = Field(default="")


# ─────────────────────────────────────────────────────────────────────────────
# Tool
# ─────────────────────────────────────────────────────────────────────────────

class LeadDataCollectTool(BaseTool):
    name: str = "leaddata_collect"
    description: str = (
        "Dynamically collect raw global leads from SerpAPI Google Maps. "
        "source='maps' → business leads. source='maps_reviewers' → traveler leads. "
        "Output: raw/leads_raw.csv"
    )
    args_schema: Type[BaseModel] = LeadDataCollectInput

    def _collect_maps_businesses(
        self, api_key: str, keywords: List[str], api_endpoint: str, engine: str,
        search_type: str, hl: str, request_timeout: int, max_results_per_keyword: int,
        require_phone: bool, require_website: bool, min_rating: float,
        min_reviews: int, phone_country_prefix: str, request_delay_seconds: float,
        scrape_emails: bool
    ) -> List[Dict[str, Any]]:
        """Collect business listings globally from Google Maps."""
        all_leads: List[Dict[str, Any]] = []
        seen: set = set()

        for kw in keywords:
            try:
                print(f"  🏢 [maps] Searching ({hl}): '{kw}'")
                r = requests.get(
                    api_endpoint,
                    params={
                        "q": kw,
                        "engine": engine,
                        "type": search_type,
                        "api_key": api_key,
                        "hl": hl,  # Inject dynamic language
                        "num": max_results_per_keyword,
                    },
                    timeout=request_timeout,
                )

                if r.status_code != 200:
                    print(f"  ⚠️  HTTP {r.status_code} for '{kw}'")
                    continue

                payload = r.json()
                if payload.get("error"):
                    print(f"  ❌ SerpAPI error '{kw}': {payload['error']}")
                    continue

                results = _get_local_results(payload)
                stats = {"total": len(results), "no_phone": 0, "no_website": 0, "low_rating": 0, "low_reviews": 0, "duplicate": 0, "kept": 0}

                for item in results[:max_results_per_keyword]:
                    if not isinstance(item, dict): continue

                    name = _clean_text(item.get("title") or item.get("name") or "")
                    if not name or len(name) < 2: continue

                    phone_raw = _clean_text(item.get("phone") or item.get("phone_number") or "")
                    website = _clean_text(item.get("website") or item.get("link") or "")
                    address = _clean_text(item.get("address") or item.get("street_address") or "")
                    coords = item.get("gps_coordinates") or {}
                    location = f"{coords['latitude']}, {coords['longitude']}" if coords.get("latitude") and coords.get("longitude") else ""
                    rating = _to_float(item.get("rating") or 0)
                    review_count = _to_int(item.get("reviews") or item.get("review_count") or 0)
                    category = _category_to_str(item.get("type") or item.get("types") or item.get("category"))

                    if require_phone and not phone_raw.strip(): stats["no_phone"] += 1; continue
                    if require_website and not website.strip(): stats["no_website"] += 1; continue
                    if min_rating > 0 and rating < min_rating: stats["low_rating"] += 1; continue
                    if min_reviews > 0 and review_count < min_reviews: stats["low_reviews"] += 1; continue

                    phone_formatted = _format_phone_e164(phone_raw, phone_country_prefix)

                    if phone_formatted and _phone_is_valid(phone_formatted):
                        dedupe_key = f"phone:{phone_formatted}"
                    else:
                        dedupe_key = f"name:{name.lower().strip()}"

                    if dedupe_key in seen: stats["duplicate"] += 1; continue
                    seen.add(dedupe_key)

                    # Dynamic Intent Score (Generic Global B2B/B2C)
                    intent = 20
                    if phone_formatted and _phone_is_valid(phone_formatted): intent += 30
                    if website: intent += 20
                    if review_count > 10: intent += 15
                    if review_count > 50: intent += 10
                    if rating >= 4.0: intent += 5

                    # Optional Enrichment
                    email = _scrape_email_from_website(website) if scrape_emails else ""

                    all_leads.append({
                        "name": name,
                        "phone": phone_raw,
                        "phone_formatted": phone_formatted,
                        "email": email,
                        "website": website,
                        "address": address,
                        "location": location,
                        "category": category,
                        "source": "maps_business",
                        "keyword": kw,
                        "rating": rating,
                        "review_count": review_count,
                        "review_snippet": _clean_text(item.get("description") or item.get("snippet") or "", 200),
                        "destination_visited": "", "review_date": "", "hotel_reviewed": "",
                        "intent_score": intent, "quality_score": "", "segment": "",
                        "last_verified": _today(),
                    })
                    stats["kept"] += 1

                print(f"  📋 '{kw}' filter stats: {stats}")
                if request_delay_seconds > 0: time.sleep(request_delay_seconds)

            except requests.exceptions.Timeout:
                print(f"  ⚠️  Timeout: '{kw}'")
            except Exception as e:
                print(f"  ⚠️  Error '{kw}': {e}")

        return all_leads

    def _extract_reviewers(
        self, api_key: str, destination: str, max_reviewers: int = 100,
        recency_days: int = 90, min_activity: int = 5,
        api_endpoint: str = SERPAPI_ENDPOINT, request_timeout: int = 30,
        hl: str = "en" # Allow localized reviewer mining
    ) -> List[Dict[str, Any]]:
        """Extract PEOPLE who recently reviewed hotels/attractions globally."""
        reviewers: List[Dict[str, Any]] = []
        seen_users: set = set()
        place_searches = [
            ("hotels", f"hotels in {destination}"),
            ("attractions", f"tourist attractions in {destination}"),
        ]

        try:
            for label, query in place_searches:
                if len(reviewers) >= max_reviewers: break
                print(f"  👤 [maps_reviewers] Finding {label}: '{destination}'")
                try:
                    r = requests.get(
                        api_endpoint,
                        params={"q": query, "engine": "google_maps", "type": "search", "api_key": api_key, "hl": hl, "num": 10},
                        timeout=request_timeout,
                    )
                    if r.status_code != 200: continue
                    payload = r.json()
                except Exception as e: continue

                if payload.get("error"): continue
                places = _get_local_results(payload)
                place_limit = 6 if label == "hotels" else 3

                for place in places[:place_limit]:
                    if len(reviewers) >= max_reviewers: break
                    if not isinstance(place, dict): continue

                    place_title = place.get("title") or place.get("name") or "Unknown"
                    id_params, id_name = _place_identifier_params(place)
                    if not id_params: continue

                    try:
                        rr = requests.get(
                            api_endpoint,
                            params={"engine": "google_maps_reviews", "api_key": api_key, "sort_by": "newestFirst", "hl": hl, **id_params},
                            timeout=request_timeout,
                        )
                        if rr.status_code != 200: continue
                        rev_payload = rr.json()
                    except Exception: continue
                    if rev_payload.get("error"): continue

                    reviews = _get_reviews_from_payload(rev_payload)
                    stats = {"old": 0, "no_user": 0, "low_activity": 0, "bad_name": 0, "duplicate": 0, "kept": 0}

                    for review in reviews:
                        if len(reviewers) >= max_reviewers: break
                        if not isinstance(review, dict): continue

                        review_date = review.get("date", "")
                        if not _parse_review_date(review_date, recency_days): stats["old"] += 1; continue

                        user = review.get("user") or review.get("user_info") or review.get("author") or {}
                        if isinstance(user, str): user = {"name": user}
                        if not isinstance(user, dict) or not user: stats["no_user"] += 1; continue

                        user_reviews = _get_user_review_count(user)
                        if user_reviews < min_activity: stats["low_activity"] += 1; continue

                        name = _clean_text(user.get("name") or user.get("username") or "")
                        if len(name) < 2: stats["bad_name"] += 1; continue

                        user_location = _clean_text(user.get("location") or "")
                        profile_key = user.get("link") or user.get("profile_link") or user.get("contributor_id")
                        dedupe_key = f"profile:{profile_key}" if profile_key else f"name:{name.lower()}|loc:{user_location.lower()}"
                        if dedupe_key in seen_users: stats["duplicate"] += 1; continue
                        seen_users.add(dedupe_key)

                        snippet = review.get("snippet") or review.get("text") or ""
                        reviewers.append({
                            "name": name, "phone": "", "phone_formatted": "", "email": "", "website": "",
                            "address": _clean_text(place.get("address") or ""), "location": user_location,
                            "category": "Traveler", "source": "google_maps_reviewer", "keyword": destination,
                            "rating": review.get("rating") or 0, "review_count": user_reviews,
                            "review_snippet": _clean_text(snippet, 200),
                            "destination_visited": destination, "review_date": review_date,
                            "hotel_reviewed": _clean_text(place_title),
                            "intent_score": 70, "quality_score": "", "segment": "", "last_verified": _today(),
                        })
                        stats["kept"] += 1

                    print(f"      📊 Review stats: {stats}")
        except Exception as e:
            print(f"  ⚠️  Reviewer mining error '{destination}': {e}")

        return reviewers

    # ─────────────────────────────────────────────────────────────────────
    # Main entrypoint
    # ─────────────────────────────────────────────────────────────────────

    def _run(
        self, topic: str, keywords: List[str], output_dir: str, sources: List[str] = None,
        credentials_file: str = "", api_endpoint: str = SERPAPI_ENDPOINT, engine: str = "google_maps",
        search_type: str = "search", hl: str = "en", request_timeout: int = 30,
        max_results_per_keyword: int = 20, skip_if_cached: bool = True,
        require_phone: bool = True, require_website: bool = False, min_rating: float = 0.0,
        min_reviews: int = 0, phone_country_prefix: str = "+1", request_delay_seconds: float = 1.0,
        scrape_emails: bool = False, reviewer_recency_days: int = 90, reviewer_min_activity: int = 5,
        csv_file: str = ""
    ) -> str:

        # ── Sanitize inputs ───────────────────────────────────────────────
        api_endpoint   = str(api_endpoint or SERPAPI_ENDPOINT).strip()
        engine         = str(engine or "google_maps").strip()
        search_type    = str(search_type or "search").strip()
        hl             = str(hl or "en").strip()  # Dynamic language
        credentials_file = str(credentials_file or "").strip()
        csv_file       = str(csv_file or "").strip()
        sources        = [str(s).strip().lower() for s in (sources or ["maps"]) if s]
        keywords       = [str(kw).strip() for kw in (keywords or []) if kw]
        phone_country_prefix = str(phone_country_prefix or "+1").strip() # Dynamic prefix
        if not phone_country_prefix.startswith("+"):
            phone_country_prefix = "+" + phone_country_prefix

        # ── Output path ───────────────────────────────────────────────────
        out_dir = Path(output_dir) / "raw"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_raw.csv"

        if skip_if_cached and _csv_has_data_rows(out_file):
            return f"⏭️  Skipped (cached): {out_file.name}"

        for src in sources:
            if src not in SUPPORTED_SOURCES:
                print(f"  ⚠️  Unknown source ignored: '{src}'")

        needs_api = any(s in sources for s in ["maps", "maps_reviewers"])
        api_key = _load_api_key(credentials_file) if needs_api else ""
        if needs_api and not api_key:
            return f"❌ No api_key found in: '{credentials_file}'."

        mode_label = " + ".join(sources)
        print(f"\n  🚀 LeadDataCollect | mode: [{mode_label}] | lang: [{hl}] | prefix: [{phone_country_prefix}]")
        print(f"  🔑 Keywords ({len(keywords)}): {keywords}")

        all_leads: List[Dict[str, Any]] = []

        # ═════════════════════════════════════════════════════════════════
        # SOURCE: csv
        # ═════════════════════════════════════════════════════════════════
        if "csv" in sources and csv_file:
            p = Path(csv_file).expanduser()
            if p.exists():
                try:
                    with open(p, newline="", encoding="utf-8") as f:
                        reader = csv.DictReader(f)
                        count = 0
                        for row in reader:
                            if not isinstance(row, dict): continue
                            lead = {field: row.get(field, "") for field in CSV_FIELDS}
                            if not _clean_text(lead.get("name")): continue
                            if not lead.get("source"): lead["source"] = "csv"
                            if not lead.get("last_verified"): lead["last_verified"] = _today()
                            if not lead.get("phone_formatted") and lead.get("phone"):
                                lead["phone_formatted"] = _format_phone_e164(lead["phone"], phone_country_prefix)
                            all_leads.append(lead)
                            count += 1
                    print(f"  📄 CSV → {count} leads loaded")
                except Exception as e:
                    print(f"  ⚠️  CSV load failed: {e}")

        # ═════════════════════════════════════════════════════════════════
        # SOURCE: maps  (Global Business leads)
        # ═════════════════════════════════════════════════════════════════
        if "maps" in sources:
            biz_leads = self._collect_maps_businesses(
                api_key=api_key, keywords=keywords, api_endpoint=api_endpoint, engine=engine,
                search_type=search_type, hl=hl, request_timeout=request_timeout,
                max_results_per_keyword=max_results_per_keyword, require_phone=require_phone,
                require_website=require_website, min_rating=min_rating, min_reviews=min_reviews,
                phone_country_prefix=phone_country_prefix, request_delay_seconds=request_delay_seconds,
                scrape_emails=scrape_emails
            )
            print(f"  ✅ [maps] {len(biz_leads)} business leads")
            all_leads.extend(biz_leads)

        # ═════════════════════════════════════════════════════════════════
        # SOURCE: maps_reviewers  (Global Traveler leads)
        # ═════════════════════════════════════════════════════════════════
        if "maps_reviewers" in sources:
            max_per_kw = max(50, max_results_per_keyword * 2)
            total_travelers = 0
            for kw in keywords:
                travelers = self._extract_reviewers(
                    api_key=api_key, destination=kw, max_reviewers=max_per_kw,
                    recency_days=reviewer_recency_days, min_activity=reviewer_min_activity,
                    api_endpoint=api_endpoint, request_timeout=request_timeout, hl=hl
                )
                print(f"  ✅ [maps_reviewers] '{kw}' → {len(travelers)} travelers")
                all_leads.extend(travelers)
                total_travelers += len(travelers)
            print(f"  ✅ [maps_reviewers] Total: {total_travelers}")

        # ═════════════════════════════════════════════════════════════════
        # Write output
        # ═════════════════════════════════════════════════════════════════
        if not all_leads:
            _write_leads_csv(out_file, [])
            hint = ""
            if "maps" in sources and require_phone:
                hint = " Tip: set require_phone=false to relax filter."
            return f"⚠️  No leads collected.{hint}"

        _write_leads_csv(out_file, all_leads)

        biz_n      = sum(1 for l in all_leads if l.get("source") == "maps_business")
        trav_n     = sum(1 for l in all_leads if l.get("source") == "google_maps_reviewer")
        csv_n      = sum(1 for l in all_leads if str(l.get("source","")).lower() == "csv")
        phone_n    = sum(1 for l in all_leads if _phone_is_valid(l.get("phone_formatted","") or l.get("phone","")))
        website_n  = sum(1 for l in all_leads if l.get("website"))

        return (
            f"✓ Collected {len(all_leads)} leads → {out_file.name}\n"
            f"  🏢 Businesses (maps):       {biz_n}\n"
            f"  👤 Travelers (reviewers):   {trav_n}\n"
            f"  📄 CSV fallback:            {csv_n}\n"
            f"  📞 With phone:              {phone_n}\n"
            f"  🌐 With website:            {website_n}"
        )
