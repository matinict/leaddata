"""
leaddata_score.py — Dynamic Score & Segment Tool (Rule 16: single output)

Reads: {output_dir}/normalized/leads_clean.csv
Writes: {output_dir}/scored/leads_scored.csv

Enhanced: Automatically normalizes ANY scoring rubric passed from YAML.
(e.g., if YAML says "intent_score": 40, it scales the 0-100 intent score to a 0-40 weight).
"""
import logging
from pathlib import Path
from typing import Type, Dict, Any
import csv
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

# Initialize logger
logger = logging.getLogger(__name__)

# Fallback rubric if YAML doesn't provide one
DEFAULT_RUBRIC = {
    "phone": 40,
    "email": 30,
    "website": 20,
    "intent_score": 10,
}

# Output schema ensures intent_score and keyword are preserved for downstream tools
SCHEMA_OUT = [
    "name", "phone", "email", "website", "address",
    "location", "category", "source", "keyword", "intent_score",
    "quality_score", "segment", "last_verified"
]

def _score(rec: dict, rubric: dict) -> int:
    total_score = 0
    is_intent_lead = rec.get("source", "") in ["intent_osint", "reddit_planner"]

    for key, weight in rubric.items():
        val = rec.get(key)

        # Handle numeric columns (like intent_score: 85)
        if isinstance(val, (int, float)):
            max_baseline = 100 if "score" in key.lower() else 10
            normalized_val = min(val / max_baseline, 1.0)
            total_score += int(normalized_val * weight)

        # Handle text/boolean columns (like phone, email)
        elif isinstance(val, str):
            if val.strip():
                total_score += weight

        elif bool(val):
            total_score += weight

    # ⚠️ CRITICAL FIX: If this is an intent lead but has 0 intent score,
    # it means it's garbage (e.g., "What is glamping?"). Kill the score.
    if is_intent_lead:
        try:
            intent_val = int(rec.get("intent_score", 0))
            if intent_val == 0:
                return 0 # Force to Cold
        except (ValueError, TypeError):
            pass

    return min(total_score, 100)

def _segment(score: int, t: dict) -> str:
    if score >= t.get("hot", 70): return "hot"
    if score >= t.get("warm", 40): return "warm"
    return "cold"

class LeadDataScoreInput(BaseModel):
    output_dir: str = Field(...)
    score_enabled: bool = Field(default=True)
    scoring_rubric: Dict[str, int] = Field(default_factory=dict)
    thresholds: Dict[str, int] = Field(default_factory=lambda: {
        "hot": 60, "warm": 30, "cold": 0
    })
    sort_by_score_desc: bool = Field(default=True)

class LeadDataScoreTool(BaseTool):
    name: str = "leaddata_score"
    description: str = "Score and segment leads dynamically based on YAML rubric. Output: scored/leads_scored.csv"
    args_schema: Type[BaseModel] = LeadDataScoreInput

    def _run(
        self,
        output_dir: str,
        score_enabled: bool = True,
        scoring_rubric: Dict[str, int] = None,
        thresholds: Dict[str, int] = None,
        sort_by_score_desc: bool = True
    ) -> str:

        # Use YAML rubric if provided, else fallback to default
        rubric = scoring_rubric if scoring_rubric else DEFAULT_RUBRIC
        if thresholds is None:
            thresholds = {"hot": 60, "warm": 30, "cold": 0}

        in_file = Path(output_dir) / "normalized" / "leads_clean.csv"
        out_dir = Path(output_dir) / "scored"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "leads_scored.csv"

        if not in_file.exists():
            logger.error(f"Input missing: {in_file}")
            return f"❌ Input missing: {in_file}"

        # Read input data
        try:
            with open(in_file, 'r', encoding='utf-8') as f:
                records = list(csv.DictReader(f))
        except Exception as e:
            logger.error(f"Failed to read {in_file}: {e}")
            return f"❌ Failed to read CSV: {e}"

        if not records:
            logger.warning("No records found to score.")
            return "⚠️ No records found to score."

        logger.info(f"Scoring {len(records)} records using rubric: {list(rubric.keys())}")

        counts = {"hot": 0, "warm": 0, "cold": 0, "skipped": 0}

        for r in records:
            if not score_enabled:
                score = 0
            else:
                score = _score(r, rubric)

            r["quality_score"] = score
            r["segment"] = _segment(score, thresholds)
            counts[r["segment"]] += 1

            # Ensure intent_score is preserved (default to 0 if missing from normalize step)
            if "intent_score" not in r or not r["intent_score"]:
                r["intent_score"] = 0

        # Sort by quality
        if sort_by_score_desc:
            records.sort(key=lambda x: int(x.get("quality_score", 0)), reverse=True)

        # Write output
        try:
            with open(out_file, 'w', newline='', encoding='utf-8') as f:
                # Use extrasaction='ignore' so any extra columns from intent/raw don't crash the writer
                w = csv.DictWriter(f, fieldnames=SCHEMA_OUT, extrasaction='ignore')
                w.writeheader()
                w.writerows(records)
        except Exception as e:
            logger.error(f"Failed to write {out_file}: {e}")
            return f"❌ Failed to write output: {e}"

        logger.info(f"Scored {len(records)} | 🔥{counts['hot']} 🔶{counts['warm']} ❄️{counts['cold']}")
        return (
            f"✓ Scored {len(records)} | "
            f"🔥{counts['hot']} 🔶{counts['warm']} ❄️{counts['cold']} → {out_file.name}"
        )
