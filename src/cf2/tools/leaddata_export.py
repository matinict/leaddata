"""
leaddata_export.py — Export & Stats Tool (Rule 16: single output)

Reads:  {output_dir}/scored/leads_scored.csv
Writes:
  - {output_dir}/scored/leads_scored.json (if json in formats)
  - {output_dir}/insights/{stats_file}    (if generate_stats)
"""
from pathlib import Path
from typing import Type, List
import csv
import json
from collections import defaultdict
from pydantic import BaseModel, Field
from crewai.tools import BaseTool


class LeadDataExportInput(BaseModel):
    output_dir: str = Field(...)
    formats: List[str] = Field(default=["csv", "json"])
    generate_stats: bool = Field(default=True)
    stats_file: str = Field(default="lead_stats.json")
    include_segments_breakdown: bool = Field(default=True)


class LeadDataExportTool(BaseTool):
    name: str = "leaddata_export"
    description: str = "Export final leads + generate stats."
    args_schema: Type[BaseModel] = LeadDataExportInput

    def _run(self, output_dir: str,
             formats: List[str] = None,
             generate_stats: bool = True,
             stats_file: str = "lead_stats.json",
             include_segments_breakdown: bool = True) -> str:

        if formats is None:
            formats = ["csv", "json"]

        scored_csv = Path(output_dir) / "scored" / "leads_scored.csv"
        if not scored_csv.exists():
            return f"❌ Input missing: {scored_csv}"

        with open(scored_csv, 'r', encoding='utf-8') as f:
            records = list(csv.DictReader(f))

        # JSON export
        if "json" in formats:
            json_file = Path(output_dir) / "scored" / "leads_scored.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(records, f, indent=2, ensure_ascii=False)

        # Stats
        if not generate_stats:
            return f"✓ Exported {len(records)} (stats skipped)"

        segments = defaultdict(int)
        scores = []
        for r in records:
            segments[r.get("segment", "unscored")] += 1
            try:
                scores.append(int(r.get("quality_score", 0)))
            except (ValueError, TypeError):
                pass

        stats = {
            "total": len(records),
            "with_phone":   sum(1 for r in records if r.get("phone")),
            "with_email":   sum(1 for r in records if r.get("email")),
            "with_website": sum(1 for r in records if r.get("website")),
            "avg_quality_score": round(sum(scores) / len(scores), 1) if scores else 0,
        }
        if include_segments_breakdown:
            stats["segments"] = dict(segments)

        insights_dir = Path(output_dir) / "insights"
        insights_dir.mkdir(parents=True, exist_ok=True)
        stats_path = insights_dir / stats_file
        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)

        return (f"✓ Exported {len(records)} | "
                f"avg={stats['avg_quality_score']} → {stats_path.name}")
