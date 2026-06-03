"""
unit_leaddata.py — Enhanced 4-category router
"""
import logging
import importlib
from pathlib import Path
from cf2.meta import mark_subtask
from cf2.core.paths import RUNTIME_PATHS
from cf2.utils.leaddata_geo_resolver import resolve_global_context

from cf2.tools.leaddata_normalize import LeadDataNormalizeTool
from cf2.tools.leaddata_score import LeadDataScoreTool
from cf2.tools.leaddata_enrich_osint import OSINTEnrichTool
from cf2.tools.leaddata_export import LeadDataExportTool

logger = logging.getLogger(__name__)

TOOL_REGISTRY = {
    "google_maps": {"module": "cf2.tools.leaddata_collect", "class": "LeadDataCollectTool", "args": {"sources": ["maps"]}},
    "maps_reviewers": {"module": "cf2.tools.leaddata_collect", "class": "LeadDataCollectTool", "args": {"sources": ["maps_reviewers"]}},
    "linkedin_company": {"module": "cf2.tools.leaddata_linkedin", "class": "LinkedInScraperTool", "args": {}},
    "reddit_travel": {"module": "cf2.tools.leaddata_reddit", "class": "RedditTravelScraperTool", "args": {}},
    "reddit_business": {"module": "cf2.tools.leaddata_intent", "class": "LeadDataIntentTool", "args": {"force_reddit": True}},
    "quora": {"module": "cf2.tools.leaddata_intent", "class": "LeadDataIntentTool", "args": {"force_quora": True}},
    "google_trends": {"module": "cf2.tools.leaddata_news", "class": "GoogleTrendsTool", "args": {}},
}

def _get_auto_config(topic: str) -> dict:
    """Enhanced 4-category source selection - returns full config"""
    t = topic.lower()

    business_words = ["agency", "consultant", "lawyer", "company", "broker", "contractor", "clinic", "firm", "office", "realtor", "accountant"]
    intent_words = ["need", "looking for", "how to", "best", "financing", "loan", "vacation", "immigration", "buy", "moving", "pr", "visa", "all inclusive", "trip", "resort"]

    config = {"location_sources": [], "directory_sources": [], "community_sources": [], "trend_sources": [], "scoring_rubric": {}, "mode": "contact"}

    if any(w in t for w in business_words):
        config["mode"] = "CONTACT"
        config["location_sources"] = ["google_maps", "maps_reviewers"]
        config["directory_sources"] = ["linkedin_company"]
        config["scoring_rubric"] = {"phone": 40, "email": 30, "website": 20, "review_count": 10}
        return config

    if any(w in t for w in intent_words):
        config["mode"] = "INTENT"
        config["community_sources"] = ["reddit_travel", "reddit_business", "quora"]
        config["location_sources"] = ["maps_reviewers"]
        config["trend_sources"] = ["google_trends"]
        config["scoring_rubric"] = {"intent_score": 60, "review_count": 20, "website": 20}
        return config

    config["mode"] = "CONTACT"
    config["location_sources"] = ["google_maps"]
    config["directory_sources"] = ["linkedin_company"]
    config["scoring_rubric"] = {"phone": 45, "email": 35, "website": 20}
    return config

def _parse_keywords(topic: str) -> list:
    return [k.strip() for k in topic.split(",") if k.strip()]

def _run_step(workspace: Path, unit_name: str, step_name: str, tool_class: type, kwargs: dict, critical: bool = False) -> str:
    try:
        logger.info(f"⚙️ [{step_name}] Starting...")
        result = tool_class()._run(**kwargs)
        logger.info(f"✅ [{step_name}] {result}")
        mark_subtask(workspace, unit_name, step_name, "done")
        return "done"
    except Exception as e:
        logger.warning(f"⚠️ [{step_name}] Failed: {e}")
        if critical:
            raise RuntimeError(f"Critical step [{step_name}] failed: {e}")
        return "failed"

def run(topic: str, workspace: Path, inputs: dict, force: bool = False) -> str:
    try:
        workspace = Path(workspace)
        leaddata_dir = workspace / "leaddata"
        leaddata_dir.mkdir(parents=True, exist_ok=True)
        unit_name = "Unit-LeadData"

        cfg = inputs.get("leaddata_config", {})
        if not cfg.get("enabled", True):
            return "disabled"

        keywords = _parse_keywords(topic)
        geo = resolve_global_context(topic, cfg)
        out_dir = str(leaddata_dir)

        creds_file = cfg.get("credentials_file", "")
        if creds_file and not Path(creds_file).is_absolute():
            creds_file = str(RUNTIME_PATHS["secrets"] / Path(creds_file).name)

        base_kwargs = {
            "topic": topic,
            "keywords": keywords,
            "output_dir": out_dir,
            "credentials_file": creds_file,
            "skip_if_cached": cfg.get("skip_if_cached", True)
        }

        # Enhanced intelligent router
        if cfg.get("auto_select_sources", False):
            auto = _get_auto_config(topic)
            logger.info(f"🧠 Mode detected: {auto['mode']}")

            # Only set if not already provided
            if not cfg.get("location_sources"):
                cfg["location_sources"] = auto["location_sources"]
            if not cfg.get("directory_sources"):
                cfg["directory_sources"] = auto["directory_sources"]
            if not cfg.get("community_sources"):
                cfg["community_sources"] = auto["community_sources"]
            if not cfg.get("trend_sources"):
                cfg["trend_sources"] = auto["trend_sources"]

            score_cfg = cfg.setdefault("score_config", {})
            if not score_cfg.get("scoring_rubric"):
                score_cfg["scoring_rubric"] = auto["scoring_rubric"]

            logger.info(f"🎯 {auto['mode']}: {cfg['location_sources'] + cfg['directory_sources'] + cfg['community_sources'] + cfg['trend_sources']}")

        # Phase 1
        logger.info("🚀 Phase 1: Source Ingestion")
        requested_sources = (
            cfg.get("location_sources", []) +
            cfg.get("directory_sources", []) +
            cfg.get("community_sources", []) +
            cfg.get("trend_sources", [])
        )
        logger.info(f"  Sources: {requested_sources}")

        tool_overrides = cfg.get("tool_overrides", {})
        source_counts = {}

        for source_name in requested_sources:
            reg = TOOL_REGISTRY.get(source_name)
            if not reg:
                logger.warning(f"⚠️ Unknown source: {source_name}")
                continue
            try:
                module = importlib.import_module(reg["module"])
                tool_class = getattr(module, reg["class"])
                final_kwargs = {**base_kwargs, **reg.get("args", {}), **tool_overrides.get(source_name, {})}

                varnames = tool_class._run.__code__.co_varnames
                if "phone_country_prefix" in varnames:
                    final_kwargs["phone_country_prefix"] = tool_overrides.get(source_name, {}).get("phone_country_prefix") or geo["prefix"]
                if "hl" in varnames:
                    final_kwargs["hl"] = tool_overrides.get(source_name, {}).get("hl") or geo["hl"]

                status = _run_step(workspace, unit_name, source_name.upper(), tool_class, final_kwargs)
                source_counts[source_name] = status
            except Exception as e:
                logger.error(f"❌ [{source_name.upper()}] {e}")
                source_counts[source_name] = "failed"

        # Phase 1 summary
        raw_file = leaddata_dir / "raw" / "leads_raw.csv"
        raw_count = 0
        if raw_file.exists():
            import csv as _csv
            with open(raw_file, 'r', encoding='utf-8') as f:
                raw_count = sum(1 for _ in _csv.DictReader(f))

        if raw_count > 0:
            logger.info(f"📊 Phase 1 Complete: {raw_count} raw leads")
            for src, status in source_counts.items():
                logger.info(f"  - {src}: {status}")
        else:
            logger.warning("⚠ Phase 1: NO leads collected")

        # Phase 2
        logger.info("🧠 Phase 2: Processing")
        norm_cfg = cfg.get("normalize_config", {})
        _run_step(workspace, unit_name, "Normalize", LeadDataNormalizeTool, {
            "output_dir": out_dir,
            "deduplicate_on": norm_cfg.get("deduplicate_on", ["website"]),
            "phone_country_default": norm_cfg.get("phone_country_default") or geo["prefix"],
            "lowercase_email": norm_cfg.get("lowercase_email", True),
            "force_https": norm_cfg.get("force_https", True),
            "strip_unicode": norm_cfg.get("strip_unicode", True),
            "min_name_length": norm_cfg.get("min_name_length", 2),
        }, critical=True)

        score_cfg = cfg.get("score_config", {})
        _run_step(workspace, unit_name, "Score", LeadDataScoreTool, {
            "output_dir": out_dir,
            "score_enabled": score_cfg.get("score_enabled", True),
            "scoring_rubric": score_cfg.get("scoring_rubric", {"phone": 45, "email": 35, "website": 20}),
            "thresholds": score_cfg.get("segment_thresholds", {"hot": 60, "warm": 30, "cold": 0}),
            "sort_by_score_desc": score_cfg.get("sort_by_score_desc", True),
        }, critical=True)

        if cfg.get("enrich_enabled", False):
            enrich_cfg = cfg.get("enrich_config", {})
            _run_step(workspace, unit_name, "Enrich", OSINTEnrichTool, {
                "input_file": str(leaddata_dir / "scored" / "leads_scored.csv"),
                "output_dir": out_dir,
                "credentials_file": creds_file,
                "min_confidence": enrich_cfg.get("min_confidence", 0.30),
                "allow_guessing": enrich_cfg.get("allow_guessing", False),
                "max_osint_queries": enrich_cfg.get("max_osint_queries", 15),
                "query_delay_seconds": enrich_cfg.get("query_delay_seconds", 1),
                "max_enrich_rows": enrich_cfg.get("max_enrich_rows", 0),
                "skip_if_cached": enrich_cfg.get("skip_if_cached", True),
            })

        export_cfg = cfg.get("export_config", {})
        _run_step(workspace, unit_name, "Export", LeadDataExportTool, {
            "output_dir": out_dir,
            "formats": export_cfg.get("formats", ["csv", "json"]),
            "generate_stats": export_cfg.get("generate_stats", True),
            "stats_file": export_cfg.get("stats_file", "lead_stats.json"),
            "include_segments_breakdown": export_cfg.get("include_segments_breakdown", True),
        })

        logger.info(f"✅ Done: {leaddata_dir}")
        return "done"

    except Exception as e:
        logger.error(f"❌ Unit-LeadData failed: {e}")
        return "failed"
