"""
leaddata_normalize.py — Normalize and Deduplicate Leads (CF2 Tool)

Reads: {output_dir}/raw/leads_raw.csv
Writes: {output_dir}/normalized/leads_clean.csv

CRITICAL: Preserves intent_score and keyword columns for downstream scoring.
"""
import logging
from pathlib import Path
from typing import Type, List
import csv
import re
import hashlib
import unicodedata
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

logger = logging.getLogger(__name__)

# FIXED SCHEMA: Added all scoring fields so they survive normalize
SCHEMA = [
    "name", "phone", "phone_formatted", "email", "website", "address",
    "location", "category", "source", "keyword",
    "rating", "review_count", "review_snippet",
    "destination_visited", "review_date", "hotel_reviewed",
    "intent_score", "quality_score", "segment", "last_verified"
]

def _norm_phone(p: str, country_default: str = "") -> str:
    if not p: return ""
    c = re.sub(r'[^\d+]', '', p.strip())
    if not c: return ""
    if c.startswith('+'): return c
    if country_default and country_default.startswith('+'): return country_default + c
    return '+' + c

def _norm_url(u: str, force_https: bool = True) -> str:
    if not u: return ""
    u = u.strip()
    if u.startswith(('http://', 'https://')): return u
    return ('https://' if force_https else 'http://') + u

def _norm_text(t: str, strip_unicode: bool = True) -> str:
    if not t: return ""
    t = t.strip()
    if strip_unicode: t = unicodedata.normalize('NFD', t)
    return re.sub(r'\s+', ' ', t)

def _dedup_key(rec: dict, fields: List[str]) -> str:
    parts = []
    for f in fields:
        v = (rec.get(f, "") or "").lower().strip()
        if f == "phone": v = _norm_phone(v).lstrip('+')
        parts.append(v)
    s = '|'.join(parts)
    if not s.strip():
        return hashlib.md5((rec.get("name", "") or "").lower().encode()).hexdigest()[:16]
    return hashlib.md5(s.encode()).hexdigest()[:16]

class LeadDataNormalizeInput(BaseModel):
    output_dir: str = Field(...)
    deduplicate_on: List[str] = Field(default=["website"])
    phone_country_default: str = Field(default="")
    lowercase_email: bool = Field(default=True)
    force_https: bool = Field(default=True)
    strip_unicode: bool = Field(default=True)
    min_name_length: int = Field(default=2)

class LeadDataNormalizeTool(BaseTool):
    name: str = "leaddata_normalize"
    description: str = "Normalize and deduplicate leads. Output: normalized/leads_clean.csv"
    args_schema: Type[BaseModel] = LeadDataNormalizeInput

    def _run(
        self,
        output_dir: str,
        deduplicate_on: List[str] = None,
        phone_country_default: str = "",
        lowercase_email: bool = True,
        force_https: bool = True,
        strip_unicode: bool = True,
        min_name_length: int = 2
    ) -> str:

        if deduplicate_on is None:
            deduplicate_on = ["website"]

        in_file = Path(output_dir) / "raw" / "leads_raw.csv"
        out_dir = Path(output_dir) / "normalized"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_clean.csv"

        if not in_file.exists():
            logger.error(f"Input missing: {in_file}")
            return f"❌ Input missing: {in_file}"

        with open(in_file, 'r', encoding='utf-8') as f:
            raw = list(csv.DictReader(f))

        ts = datetime.now(timezone.utc).isoformat()
        normalized = []

        for r in raw:
            name = _norm_text(r.get("name", "") or r.get("title", ""), strip_unicode)
            if len(name) < min_name_length:
                continue

            email = (r.get("email", "") or "").strip()
            if lowercase_email:
                email = email.lower()

            # FIXED: Preserve all fields needed for scoring
            normalized.append({
                "name": name,
                "phone": _norm_phone(r.get("phone", ""), phone_country_default),
                "phone_formatted": r.get("phone_formatted", ""),
                "email": email,
                "website": _norm_url(r.get("website", "") or r.get("link", ""), force_https),
                "address": _norm_text(r.get("address", ""), strip_unicode),
                "location": _norm_text(r.get("location", ""), strip_unicode),
                "category": _norm_text(r.get("category", ""), strip_unicode),
                "source": r.get("source", "import"),
                "keyword": r.get("keyword", ""),
                "rating": r.get("rating", 0),
                "review_count": r.get("review_count", 0),
                "review_snippet": r.get("review_snippet", ""),
                "destination_visited": r.get("destination_visited", ""),
                "review_date": r.get("review_date", ""),
                "hotel_reviewed": r.get("hotel_reviewed", ""),
                "intent_score": r.get("intent_score", 0),
                "quality_score": "",
                "segment": "",
                "last_verified": ts,
            })

        # Deduplicate
        seen, unique = set(), []
        for rec in normalized:
            k = _dedup_key(rec, deduplicate_on)
            if k not in seen:
                seen.add(k)
                unique.append(rec)

        removed = len(normalized) - len(unique)

        try:
            with open(out_file, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=SCHEMA, extrasaction='ignore')
                w.writeheader()
                w.writerows(unique)
        except Exception as e:
            logger.error(f"Failed to write normalized CSV: {e}")
            return f"❌ Failed to write output: {e}"

        logger.info(f"✓ Normalized {len(unique)} | Dedup removed {removed} → {out_file.name}")
        return f"✓ Normalized {len(unique)} | Dedup removed {removed} → {out_file.name}"
