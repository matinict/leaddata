"""
cf2/tools/debate_score_extractor.py — Scoreboard Data Resolver

Migrated from: cf2/core/render/scoreboard/score_extractor.py
Responsibility: Produce a ScoreData dict for the scoreboard overlay.
Strategy: LLM-generated scores.json (from Unit-Data) → heuristic fallback.
Pure logic — reads .md/.json files, returns a dict. No render, no I/O writes.

UPDATED: Dynamically generates 3 judge marks based on debate arguments
"""
from __future__ import annotations
import json, re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

_MAX_TITLE_CHARS   = 42
_MIN_SCORE         = 8
_MAX_SCORE         = 20
_DEFAULT_OPENING   = 15
_DEFAULT_BASELINE  = 12
_PRO_HEAD_RE = re.compile(r"^\s*(?:Argument|Arg)\s*(\d+)\s*[:-]\s*(.+?)$", re.MULTILINE | re.IGNORECASE)
_CON_HEAD_RE = re.compile(r"^\s*(?:Counter[\s-]?Argument|Counter[\s-]?Arg|C[\s-]?Arg|CA)\s*(\d+)\s*[:-]\s*(.+?)$", re.MULTILINE | re.IGNORECASE)
_OPENING_RE = re.compile(r"OPENING\s*STATEMENT?", re.IGNORECASE)

def resolve(
    debate_dir: Path,
    md_suffix: str,
    cfg: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Resolve ScoreData. Lookup order: 1. scores.json (LLM) 2. heuristic fallback."""
    propose_md = debate_dir / f"propose{md_suffix}.md"
    oppose_md  = debate_dir / f"oppose{md_suffix}.md"
    decide_md  = debate_dir / f"decide{md_suffix}.md"

    if not (propose_md.exists() and oppose_md.exists() and decide_md.exists()):
        return None

    scores_json = debate_dir / f"scores{md_suffix}.json"
    llm_data = _load_scores_json(scores_json)
    if llm_data is not None:
        llm_data["source"] = "llm"
        # Ensure judges are present even in LLM data
        if "judges" not in llm_data:
            llm_data["judges"] = _generate_judge_marks(
                llm_data.get("totals", {}).get("pro", 0),
                llm_data.get("totals", {}).get("con", 0)
            )
        return llm_data

    heuristic = _score_heuristic(
        propose_md.read_text(encoding="utf-8"),
        oppose_md.read_text(encoding="utf-8"),
        decide_md.read_text(encoding="utf-8"),
        cfg,
    )
    heuristic["source"] = "heuristic"
    return heuristic

def _load_scores_json(path: Path) -> Optional[Dict[str, Any]]:
    """Load scores from JSON file"""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if "args" not in data or "totals" not in data or "winner" not in data:
        return None
    if data["winner"] not in ("propose", "oppose", "draw"):
        return None

    # Extract judge marks if present, otherwise generate
    if "judges" not in data:
        pro_total = data.get("totals", {}).get("pro", 0)
        con_total = data.get("totals", {}).get("con", 0)
        data["judges"] = _generate_judge_marks(pro_total, con_total)

    return data

def _generate_judge_marks(pro_total: int, con_total: int) -> List[Dict[str, Any]]:
    """
    Generate 3 judge marks on the same 8-20 scale as individual argument scores.
    Each judge gives an *overall* impression score in [MIN..MAX], derived from
    how pro/con totals compare. Not a sum — an individual impression.
    """
    # Normalize totals to a ratio, then map to the 8-20 scale
    total = max(pro_total + con_total, 1)
    pro_ratio = pro_total / total          # e.g., 66/122 = 0.54
    con_ratio = con_total / total          # e.g., 56/122 = 0.46

    # Map ratio to score range: 50/50 → midpoint, heavier side gets higher score
    span = _MAX_SCORE - _MIN_SCORE          # 12
    base_pro = _MIN_SCORE + pro_ratio * span * 2   # winner tilts toward MAX
    base_con = _MIN_SCORE + con_ratio * span * 2

    # Three judges with slight variations (±1 point)
    variations = [
        ("Judge 1 (Male)",    -1, +1),   # slight con bias
        ("Judge 2 (Female)",  +1, -1),   # slight pro bias
        ("Judge 3 (Neutral)",  0,  0),   # neutral
    ]
    judges = []
    for name, pro_delta, con_delta in variations:
        judges.append({
            "name": name,
            "pro": _clamp(int(round(base_pro + pro_delta))),
            "con": _clamp(int(round(base_con + con_delta))),
        })
    return judges

def _score_heuristic(pro_text: str, con_text: str, decide_text: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Generate scores using heuristic analysis of debate arguments"""
    #raw_max   = cfg.get("debate_scoreboard_max_args", 3) if cfg else 3
    #max_args   = int(raw_max) if not isinstance(raw_max, dict) else 3
    raw_max = cfg.get("debate_scoreboard_max_args", 3) if cfg else 3
    max_args = int(raw_max) if not isinstance(raw_max, dict) else 3
    winner_tag = _parse_winner(decide_text)
    pro_args = _extract_arguments(pro_text, _PRO_HEAD_RE, max_args)
    con_args = _extract_arguments(con_text, _CON_HEAD_RE, max_args)
    n_args   = max(len(pro_args), len(con_args), max_args)

    opening = {
        "pro_title": "General", "con_title": "General",
        "pro": _DEFAULT_OPENING + (3 if _OPENING_RE.search(pro_text) else 0),
        "con": _DEFAULT_OPENING + (3 if _OPENING_RE.search(con_text) else 0),
    }
    opening["pro"], opening["con"] = _apply_winner_bias(opening["pro"], opening["con"], winner_tag, weight=1)

    args: List[Dict[str, Any]] = []
    for i in range(n_args):
        p_title, p_body = pro_args[i] if i < len(pro_args) else ("Argument", " ")
        c_title, c_body = con_args[i] if i < len(con_args) else ("Counter-Argument", " ")
        p_score, c_score = _apply_winner_bias(_score_body(p_body), _score_body(c_body), winner_tag, weight=2)
        args.append({
            "pro_title": _trim_title(p_title), "con_title": _trim_title(c_title),
            "pro": _clamp(p_score), "con": _clamp(c_score)
        })

    pro_total = opening["pro"] + sum(a["pro"] for a in args)
    con_total = opening["con"] + sum(a["con"] for a in args)
    if winner_tag == "propose" and pro_total <= con_total:
        pro_total = con_total + 2
    elif winner_tag == "oppose" and con_total <= pro_total:
        con_total = pro_total + 2

    # Generate dynamic judge marks
    judge_marks = _generate_judge_marks(pro_total, con_total)

    return {
        "opening": opening,
        "args": args,
        "totals": {"pro": pro_total, "con": con_total},
        "judges": judge_marks,
        "winner": winner_tag
    }

def _extract_arguments(text: str, pattern: re.Pattern, max_n: int) -> List[Tuple[str, str]]:
    """Extract numbered arguments from markdown text"""
    matches = list(pattern.finditer(text))
    out: List[Tuple[str, str]] = []
    for i, m in enumerate(matches):
        title = m.group(2).strip().rstrip(".:")
        start, end = m.end(), matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((title, text[start:end].strip()))
        if len(out) >= max_n:
            break
    return out

def _score_body(body: str) -> int:
    """Score argument quality based on length, evidence, and structure"""
    if not body:
        return _DEFAULT_BASELINE
    length_bonus = min(4, len(body.split()) // 25)
    evidence_kw  = sum(1 for kw in ("study", "data", "report", "percent", "%", "evidence", "research", "statistic") if kw in body.lower())
    structure    = 1 if body.count(".") >= 2 else 0
    return _DEFAULT_BASELINE + length_bonus + min(evidence_kw, 2) + structure

def _apply_winner_bias(pro: int, con: int, winner: str, weight: int = 1) -> Tuple[int, int]:
    """Apply slight bias towards winning side"""
    if winner == "propose":
        return pro + weight, max(_MIN_SCORE, con)
    if winner == "oppose":
        return max(_MIN_SCORE, pro), con + weight
    return pro, con

def _parse_winner(decide_text: str) -> str:
    """Parse winner from judge decision text"""
    upper = decide_text.upper()
    if "PROPOSITION WINS" in upper:
        return "propose"
    if "OPPOSITION WINS" in upper:
        return "oppose"
    return "draw"

def _trim_title(title: str) -> str:
    """Trim title to max length with ellipsis"""
    title = re.sub(r"\s+", " ", title).strip()
    return title[:_MAX_TITLE_CHARS-1].rstrip() + "…" if len(title) > _MAX_TITLE_CHARS else (title or "Argument")

def _clamp(n: int) -> int:
    """Clamp score to valid range"""
    return max(_MIN_SCORE, min(_MAX_SCORE, int(n)))
