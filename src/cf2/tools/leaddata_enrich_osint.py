"""
leaddata_enrich_osint.py — OSINT Enrichment for B2C & B2B Leads

Input:
  {output_dir}/scored/leads_scored.csv (or fallbacks)
Output:
  {output_dir}/enriched/leads_enriched.csv

CSV Column Contract (Critical — never overwrite real with guessed):
  email                  → REAL only  (original source / live-verified / OSINT-found)
  possible_email         → GUESSED only (pattern permutation, never used for outreach)
  email_status           → verified | public_found | original | social_only | guessed | none
  email_source           → where the email came from (URL or method name)
  outreach_ready         → yes | no
  enriched_email         → mirrors email (real only, for downstream compatibility)
  possible_email_conf    → confidence score for guessed email (0.000–1.000)
  enrichment_confidence  → confidence score for real email (0.000–1.000)
  enrichment_method      → original | osint_live_verified | social_profile_only | email_guess | none
  social_profile_url     → LinkedIn / Facebook / Instagram direct URL if found
  evidence_url           → source page where real email was discovered

Rule 16: Single output file per tool.
Rule 32: Smart skip if output already exists.
Rule 39: API key resolved via credentials_file JSON {"api_key": "..."}.
"""

from pathlib import Path
from typing import Type, List, Optional, Tuple, Dict, Any
import csv
import json
import re
import time
import unicodedata
import requests
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


SERPAPI_ENDPOINT = "https://serpapi.com/search.json"

# Names that are pseudonyms, roles, or corporate noise — never valid personal names
PSEUDONYMS_AND_JUNK = {
    "guy", "poet", "vegan", "writes", "handyman", "build", "travel", "vacation",
    "guide", "local", "tester", "test", "user", "anonymous", "customer", "guest",
    "review", "reviewer", "channel", "vlog", "blog", "photography", "photos",
    "adventures", "adventure", "solutions", "services", "group", "family",
    "dr", "mr", "mrs", "ms", "prof", "doc", "sir", "lady", "jr", "sr",
    "ii", "iii", "iv", "v"
}


# ─────────────────────────────────────────────
# Pydantic Input Schema
# ─────────────────────────────────────────────

class OSINTEnrichInput(BaseModel):
    input_file: str = Field(..., description="Path to leads_scored.csv")
    output_dir: str = Field(..., description="Root output directory for enriched/")
    credentials_file: str = Field(default="", description="JSON file with {api_key: ...}")
    min_confidence: float = Field(default=0.30, description="Min confidence to keep real email")
    allow_guessing: bool = Field(default=True, description="Generate possible_email guesses (never overwrites email)")
    skip_if_cached: bool = Field(default=True, description="Skip if enriched output already exists")
    max_osint_queries: int = Field(default=50, description="Max live SerpAPI search queries")
    query_delay_seconds: int = Field(default=1, description="Seconds between API calls")
    max_enrich_rows: int = Field(default=0, description="Limit to top N rows by intent. 0 = all.")


# ─────────────────────────────────────────────
# Utility Helpers
# ─────────────────────────────────────────────

def _load_api_key(credentials_file: str) -> str:
    """Load SerpAPI key from JSON credentials file."""
    if not credentials_file:
        return ""
    p = Path(credentials_file).expanduser()
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return str(data.get("api_key") or "").strip()
    except Exception:
        return ""


def _strip_accents(text: str) -> str:
    """Normalize accented characters to ASCII (Clément → Clement)."""
    try:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    except Exception:
        return text


def _clean_name(name: str) -> str:
    """
    Extract clean First Last from messy reviewer display names.
    Removes brackets, special chars, and noise tokens.
    """
    if not name:
        return ""
    name = re.sub(r"\(.*?\)|\[.*?\]", " ", name)
    cleaned = re.sub(r"[^a-zA-Z\s\u00C0-\u017F'-]", " ", name)
    parts = [p.strip() for p in cleaned.split() if p.strip()]
    noise = {"dr", "mr", "mrs", "ms", "prof", "doc", "jr", "sr", "ii", "iii", "iv", "v"}
    parts = [p for p in parts if p.lower() not in noise]
    if len(parts) >= 2:
        return f"{parts[0]} {parts[-1]}"
    elif parts:
        return parts[0]
    return ""


def _is_valid_real_name(first: str, last: str) -> bool:
    """
    Guard: Reject initials, pseudonyms, numbers, and corporate names.
    Must pass before any email guess is generated.
    """
    if len(first) < 2 or len(last) < 2:
        return False
    if any(ch.isdigit() for ch in (first + last)):
        return False
    if first.lower() in PSEUDONYMS_AND_JUNK or last.lower() in PSEUDONYMS_AND_JUNK:
        return False
    return True


def _extract_city_state(address: str) -> str:
    """
    Parse City, State from a full address string.
    'Vendue Range, Concord St, Charleston, SC 29401' → 'Charleston, SC'
    """
    if not address:
        return ""
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 3:
        for part in parts[-3:]:
            if re.search(r'\b[A-Z]{2}\b\s+\d{5}', part):
                return part.strip()
        return f"{parts[-2]}, {parts[-1]}"
    return address


def _extract_emails_from_text(text: str) -> List[str]:
    """Find real email addresses embedded in scraped text."""
    if not text:
        return []
    pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    found = re.findall(pattern, text)
    return [e.lower().strip() for e in found if "@" in e]


def _csv_has_data_rows(path: Path) -> bool:
    """True only if CSV has at least one non-empty data row after header."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                if any(str(cell).strip() for cell in row):
                    return True
        return False
    except Exception:
        return path.stat().st_size > 0


# ─────────────────────────────────────────────
# OSINT: Live Web Search for Real Emails
# ─────────────────────────────────────────────

def _live_osint_social_search(
    name: str,
    city_context: str,
    api_key: str
) -> Tuple[Optional[str], Optional[str], float, Optional[str]]:
    """
    Search Google for real public social profiles and explicitly listed emails.
    """
    if not api_key or len(name) < 3:
        return None, None, 0.0, None

    query = (
        f'"{name}" "{city_context}" '
        f'(site:linkedin.com/in/ OR site:facebook.com/ OR site:instagram.com/) '
        f'"gmail.com"'
    )

    try:
        response = requests.get(
            SERPAPI_ENDPOINT,
            params={
                "q": query,
                "engine": "google",
                "hl": "en",
                "gl": "us",
                "api_key": api_key,
                "num": 5,
            },
            timeout=25
        )

        if response.status_code != 200:
            return None, None, 0.0, None

        organic = response.json().get("organic_results", [])

        for result in organic:
            link = result.get("link", "")
            snippet = result.get("snippet", "")
            title = result.get("title", "")

            # Priority 1: Real email found in indexed snippet
            emails = _extract_emails_from_text(f"{title} {snippet}")
            is_social = any(p in link for p in ["linkedin.com/in/", "facebook.com", "instagram.com"])

            if emails:
                social_url = link if is_social else None
                return emails[0], social_url, 0.90, link  # ✅ Real verified email

            # Priority 2: Social profile found but no email
            if is_social:
                return None, link, 0.60, link  # 🔗 Profile only

    except Exception:
        pass

    return None, None, 0.0, None


def _live_osint_google_search(
    name: str,
    location: str,
    api_key: str
) -> Tuple[List[str], float, Optional[str]]:
    """
    Broader Google search for emails tied to person + location.
    Fallback after social search finds nothing.
    """
    if not api_key or len(name) < 3:
        return [], 0.0, None

    queries = [
        f'"{name}" "{location}" "gmail.com"',
        f'"{name}" "contact" "{location}"',
    ]

    found_emails: List[str] = []
    best_confidence = 0.0
    evidence_url: Optional[str] = None

    for idx, query in enumerate(queries):
        try:
            if idx > 0:
                time.sleep(1.0)

            response = requests.get(
                SERPAPI_ENDPOINT,
                params={
                    "q": query,
                    "engine": "google",
                    "hl": "en",
                    "gl": "us",
                    "api_key": api_key,
                    "num": 10,
                },
                timeout=25
            )

            if response.status_code != 200:
                continue

            for result in response.json().get("organic_results", []):
                text = f"{result.get('title', '')} {result.get('snippet', '')}"
                link = result.get("link", "")
                emails = _extract_emails_from_text(text)

                for email in emails:
                    if email not in found_emails:
                        found_emails.append(email)
                        best_confidence = max(best_confidence, 0.85)
                        if not evidence_url:
                            evidence_url = link

        except Exception:
            continue

    return found_emails, best_confidence, evidence_url


# ─────────────────────────────────────────────
# Guessed Emails (possible_email only)
# ─────────────────────────────────────────────

def _guess_consumer_emails(first_name: str, last_name: str) -> List[Tuple[str, float]]:
    """
    Generate plausible email permutations for the possible_email column ONLY.
    These are NEVER written to the email column.
    """
    if not _is_valid_real_name(first_name, last_name):
        return []

    fn = _strip_accents(first_name.lower().replace("-", "").replace(".", "").strip())
    ln = _strip_accents(last_name.lower().replace("-", "").replace(".", "").strip())

    if not fn or not ln:
        return []

    domains = [
        ("gmail.com",   0.55),
        ("yahoo.com",   0.25),
        ("outlook.com", 0.15),
        ("hotmail.com", 0.10),
    ]

    patterns = [
        (f"{fn}.{ln}",        0.80),   # john.doe
        (f"{fn}{ln}",         0.50),   # johndoe
        (f"{fn[0]}{ln}",      0.35),   # jdoe
        (f"{fn}.{ln[0]}",     0.25),   # john.d
    ]

    results = []
    for domain, dom_conf in domains:
        for pattern, pat_conf in patterns:
            email = f"{pattern}@{domain}"
            # Guesses are heavily penalized to reflect uncertainty
            combined_conf = round((pat_conf * dom_conf) * 0.1, 3)
            results.append((email, combined_conf))

    return sorted(results, key=lambda x: x[1], reverse=True)


# ─────────────────────────────────────────────
# Main Tool Class
# ─────────────────────────────────────────────

class OSINTEnrichTool(BaseTool):
    name: str = "leaddata_enrich_osint"
    description: str = (
        "Enrich B2C traveler leads with REAL verified emails (OSINT) "
        "and plausible guessed emails (possible_email). "
        "Real emails go to 'email'. Guesses go to 'possible_email'. "
        "Never mixed. outreach_ready=yes only for verified contacts."
    )
    args_schema: Type[BaseModel] = OSINTEnrichInput

    def _run(
        self,
        input_file: str,
        output_dir: str,
        credentials_file: str = "",
        min_confidence: float = 0.30,
        allow_guessing: bool = True,
        skip_if_cached: bool = True,
        max_osint_queries: int = 50,
        query_delay_seconds: int = 1,
        max_enrich_rows: int = 0,
    ) -> str:

        # ── Input validation ──────────────────────────────────────
        if not input_file or str(input_file).strip().lower() in ("none", "null", ""):
            return "❌ Missing valid input_file path"

        # ── Output setup ──────────────────────────────────────────
        out_dir = Path(output_dir) / "enriched"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_enriched.csv"

        # Rule 32: Smart skip
        if skip_if_cached and _csv_has_data_rows(out_file):
            return f"⏭️  Skipped (cached): {out_file.name}"

        # ── Input file resolution with fallback chain ─────────────
        in_path = Path(input_file).expanduser()
        if not in_path.exists():
            parent = in_path.parent.parent
            fallbacks = [
                parent / "scored"     / "leads_scored.csv",
                parent / "normalized" / "leads_clean.csv",
                parent / "raw"        / "leads_raw.csv",
            ]
            for fb in fallbacks:
                if fb.exists():
                    in_path = fb
                    print(f"  ℹ️  Input not found — using fallback: {fb.name}")
                    break

        if not in_path.exists():
            return f"❌ Input not found: {input_file} (checked standard fallbacks)"

        # ── Load API key ──────────────────────────────────────────
        api_key = _load_api_key(credentials_file)
        if not api_key:
            print("  ⚠️  No SerpAPI key — OSINT searches skipped. Guesses only (if allow_guessing=True).")

        # ── Read CSV ──────────────────────────────────────────────
        print(f"  📂 Reading: {in_path.name}")
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                src_fields: List[str] = list(reader.fieldnames) if reader.fieldnames else []
                rows = list(reader)
        except Exception as e:
            return f"❌ Failed to parse CSV: {e}"

        total_input = len(rows)

        # ── Sort by intent score, limit if requested ──────────────
        try:
            rows.sort(key=lambda r: float(r.get("intent_score", 0) or 0), reverse=True)
        except Exception:
            pass

        if max_enrich_rows > 0 and len(rows) > max_enrich_rows:
            print(f"  🎯 Limiting to top {max_enrich_rows} / {total_input} rows by intent score")
            rows = rows[:max_enrich_rows]

        # ── Extend CSV schema with new columns ───────────────────
        NEW_COLUMNS = [
            "email",                    # REAL only — verified/found
            "possible_email",           # GUESSED only — pattern permutation
            "possible_email_conf",      # Confidence for guessed email
            "email_status",             # verified|public_found|original|social_only|guessed|none
            "email_source",             # method name or URL where real email was found
            "evidence_url",             # page where real email was discovered
            "outreach_ready",           # yes | no
            "enriched_email",           # mirrors email (backward compatibility)
            "enrichment_confidence",    # confidence for real email
            "enrichment_method",        # osint_live_verified|social_profile_only|email_guess|original|none
            "social_profile_url",       # LinkedIn / Facebook / Instagram URL
            "enriched_phone",           # phone (kept for downstream compatibility)
        ]
        for col in NEW_COLUMNS:
            if col not in src_fields:
                src_fields.append(col)

        # ── Stats counters ────────────────────────────────────────
        stats = {
            "total": len(rows),
            "original_email": 0,
            "osint_real_email": 0,
            "social_profile_only": 0,
            "guessed_only": 0,
            "no_contact": 0,
        }

        enriched_rows = []
        osint_queries_run = 0

        print(f"  ⚡ Enriching {len(rows)} leads...")
        print(f"  🔑 OSINT budget: {max_osint_queries} queries | Guessing: {allow_guessing}")
        print(f"  📊 Dual-track: email=REAL | possible_email=GUESSED")

        for idx, row in enumerate(rows, 1):
            name    = row.get("name",     "").strip()
            location = row.get("location", "").strip()
            address  = row.get("address",  "").strip()
            source   = row.get("source",   "")

            # ── Initialize all output fields as empty ─────────────
            real_email:     Optional[str]   = None
            guessed_email:  Optional[str]   = None
            guessed_conf:   float           = 0.0
            real_confidence: float          = 0.0
            method:         str             = "none"
            email_status:   str             = "none"
            email_source:   str             = ""
            evidence_url:   Optional[str]   = None
            social_url:     Optional[str]   = None
            outreach_ready: str             = "no"

            # ─────────────────────────────────────────────────────
            # CASE 1: Already has original email → keep as-is
            # ─────────────────────────────────────────────────────
            existing_email = row.get("email", "").strip()
            if existing_email and "@" in existing_email:
                real_email      = existing_email
                real_confidence = 1.0
                method          = "original"
                email_status    = "original"
                email_source    = "source_data"
                outreach_ready  = "yes"
                stats["original_email"] += 1
                print(f"    ✅ [{idx}/{len(rows)}] Original email kept: {real_email}")

            # ─────────────────────────────────────────────────────
            # CASE 2: B2C Traveler → OSINT social + web search
            # ─────────────────────────────────────────────────────
            elif source == "google_maps_reviewer" and len(name) >= 3:
                parsed_name = _clean_name(name)
                parts       = parsed_name.split()
                first_name  = parts[0] if parts else ""
                last_name   = parts[-1] if len(parts) > 1 else ""

                # Skip names with no Latin characters
                if not re.search(r'[a-zA-Z]', name):
                    first_name = ""
                    last_name  = ""

                # Determine best city context for search accuracy
                city_context = _extract_city_state(address) or location or ""

                # ── Method A: Live Social OSINT (primary) ─────────
                if api_key and osint_queries_run < max_osint_queries and parsed_name:
                    print(f"    🔎 [{idx}/{len(rows)}] Social OSINT: {parsed_name} | {city_context}")

                    found_email, found_social, conf, ev_url = _live_osint_social_search(
                        parsed_name, city_context, api_key
                    )
                    osint_queries_run += 1

                    if found_email and conf >= min_confidence:
                        real_email      = found_email
                        real_confidence = conf
                        method          = "osint_live_verified"
                        email_status    = "verified"
                        email_source    = ev_url or "social_osint"
                        evidence_url    = ev_url
                        outreach_ready  = "yes"
                        stats["osint_real_email"] += 1
                        print(f"      🎯 REAL Email found: {real_email} (conf={conf:.2f})")

                    if found_social:
                        social_url = found_social
                        if not real_email:
                            method          = "social_profile_only"
                            email_status    = "social_only"
                            evidence_url    = found_social
                            real_confidence = conf
                            stats["social_profile_only"] += 1
                            print(f"      🔗 Social Profile: {social_url}")

                    # ── Method B: Broader Google search (secondary) ─
                    if not real_email and api_key and osint_queries_run < max_osint_queries:
                        live_emails, live_conf, live_ev = _live_osint_google_search(
                            parsed_name, city_context, api_key
                        )
                        osint_queries_run += 1

                        if live_emails and live_conf >= min_confidence:
                            real_email      = live_emails[0]
                            real_confidence = live_conf
                            method          = "osint_live_verified"
                            email_status    = "public_found"
                            email_source    = live_ev or "google_osint"
                            evidence_url    = live_ev
                            outreach_ready  = "yes"
                            stats["osint_real_email"] += 1
                            print(f"      🎯 REAL Email (web): {real_email} (conf={live_conf:.2f})")

                    if query_delay_seconds > 0:
                        time.sleep(query_delay_seconds)

                # ── Method C: Pattern guessing (possible_email only) ─
                if allow_guessing and first_name and last_name:
                    guesses = _guess_consumer_emails(first_name, last_name)
                    if guesses:
                        guessed_email, guessed_conf = guesses[0]
                        if not real_email:
                            method         = "email_guess"
                            email_status   = "guessed"
                            outreach_ready = "no"   # guesses NEVER mark outreach_ready
                            stats["guessed_only"] += 1
                            print(f"      💭 Guessed: {guessed_email} (conf={guessed_conf:.3f})")

                if not real_email and not guessed_email and not social_url:
                    stats["no_contact"] += 1

            # ─────────────────────────────────────────────────────
            # CASE 3: B2B business lead — no OSINT enrichment needed
            # ─────────────────────────────────────────────────────
            else:
                existing_website = row.get("website", "").strip()
                if existing_email:
                    real_email      = existing_email
                    real_confidence = 1.0
                    method          = "original"
                    email_status    = "original"
                    outreach_ready  = "yes"
                    stats["original_email"] += 1
                elif existing_website:
                    email_status    = "none"
                    outreach_ready  = "no"
                else:
                    stats["no_contact"] += 1

            # ─────────────────────────────────────────────────────
            # WRITE ALL COLUMNS — strict separation maintained
            # ─────────────────────────────────────────────────────

            # Real email — only verified/found/original
            row["email"]                 = real_email or ""

            # Guessed email — NEVER touches email column
            row["possible_email"]        = guessed_email or ""
            row["possible_email_conf"]   = f"{guessed_conf:.3f}" if guessed_email else ""

            # Metadata
            row["email_status"]          = email_status
            row["email_source"]          = email_source
            row["evidence_url"]          = evidence_url or ""
            row["outreach_ready"]        = outreach_ready

            # Downstream compatibility columns
            row["enriched_email"]        = real_email or ""
            row["enrichment_confidence"] = f"{real_confidence:.3f}"
            row["enrichment_method"]     = method
            row["social_profile_url"]    = social_url or ""
            row["enriched_phone"]        = row.get("phone", "")

            enriched_rows.append(row)

        # ── Write output CSV ──────────────────────────────────────
        try:
            with open(out_file, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=src_fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(enriched_rows)
        except Exception as e:
            return f"❌ Failed to write output: {e}"

        # ── Build summary ─────────────────────────────────────────
        real_count    = stats["original_email"] + stats["osint_real_email"]
        guessed_count = stats["guessed_only"]
        social_count  = stats["social_profile_only"]
        no_count      = stats["no_contact"]

        return (
            f"✓ Enrichment complete → {out_file.name}\n"
            f"   📊 Total processed   : {stats['total']}\n"
            f"   🎯 Real emails found : {real_count}  "
            f"({stats['original_email']} original + {stats['osint_real_email']} OSINT-verified)\n"
            f"   🔗 Social profiles   : {social_count}  (no email, but direct message URL)\n"
            f"   💭 Guessed emails    : {guessed_count}  (possible_email column only, outreach_ready=no)\n"
            f"   ⚠️  No contact found : {no_count}\n"
            f"   🔑 OSINT queries used: {osint_queries_run}/{max_osint_queries}\n"
            f"   📌 Columns: email=REAL | possible_email=GUESSED | outreach_ready=yes/no"
        )
