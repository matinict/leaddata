"""
core/compress/decide_compressor.py
Deterministic compressor: decide.md (multi-sentence) → decide-m.md (1-sentence per section)

HD format has:
  - PROPOSITION: 2-3 sentences
  - OPPOSITION: 2-3 sentences
  - ANALYSIS: 2-3 sentences
  - DECISION: winner + 1-2 sentences

Mobile format outputs:
  - PROPOSITION: 1st sentence only
  - OPPOSITION: 1st sentence only
  - ANALYSIS: 1st sentence only
  - DECISION: winner + 1st sentence reason
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Optional


# ── Constants ──────────────────────────────────────────────────────────────

DEFAULT_CHAR_CAP = 800
VERDICT_LINE_PREFIX = "VERDICT:"


# ── Regex ──────────────────────────────────────────────────────────────────

_VERDICT_LINE_RE = re.compile(
    r"(?im)^\s*VERDICT\s*:\s*(.+?)$"
)

_PROPOSITION_RE = re.compile(
    r"(?im)^\s*PROPOSITION\s*:\s*(.+?)(?=\n\s*(?:OPPOSITION\s*:|$))",
    re.DOTALL,
)

_OPPOSITION_RE = re.compile(
    r"(?im)^\s*OPPOSITION\s*:\s*(.+?)(?=\n\s*(?:ANALYSIS|$))",
    re.DOTALL,
)

_ANALYSIS_RE = re.compile(
    r"(?im)^\s*ANALYSIS\s*\n+(.+?)(?=\n\s*DECISION)",
    re.DOTALL,
)

_DECISION_WINNER_RE = re.compile(
    r"(?im)^\s*DECISION\s*\n+\s*(\w+)\s+WINS\.?\s*(.*?)(?=\Z)",
    re.DOTALL,
)


# ── Public API ─────────────────────────────────────────────────────────────

def compress(hd_path: Path, mobile_path: Path, max_chars: int = DEFAULT_CHAR_CAP) -> bool:
    """
    Parse multi-sentence HD format and extract first sentence per section for mobile.
    """
    if not hd_path.exists():
        print(f"  ❌ Cannot compress — missing: {hd_path}")
        return False

    hd_text = hd_path.read_text(encoding="utf-8")
    parts = _parse_hd(hd_text)

    if not parts:
        print(f"  ❌ Could not parse decide.md")
        return False

    # Handle DRAW edge case
    if parts["winner"] == "DRAW":
        parts["winner"] = "OPPOSITION"
        print(f"  ℹ️ DRAW mapped → OPPOSITION")

    # Extract first sentence, then truncate aggressively to fit 800 char budget
    prop_first = _truncate_to_clauses(_first_sentence(parts["proposition"]), max_len=45)
    oppo_first = _truncate_to_clauses(_first_sentence(parts["opposition"]), max_len=45)
    analysis_first = _truncate_to_clauses(_first_sentence(parts["analysis"]), max_len=55)
    reason_first = _truncate_to_clauses(_first_sentence(parts["reason"]), max_len=60)

    # Build mobile version (1-sentence per section)
    mobile_text = _build_mobile(
        topic=parts["topic"],
        proposition=prop_first,
        opposition=oppo_first,
        analysis=analysis_first,
        winner=parts["winner"],
        reason=reason_first,
    )

    mobile_path.write_text(mobile_text, encoding="utf-8")

    char_count = len(mobile_text)
    print(f"  ✅ Compressed → {char_count} chars ({parts['winner']} WINS)")

    if char_count > max_chars:
        print(f"  ⚠️  Warning: {char_count} chars exceeds max {max_chars}")

    return True


# ── Parsing ────────────────────────────────────────────────────────────────

def _parse_hd(text: str) -> Optional[Dict[str, str]]:
    """
    Extract VERDICT, PROPOSITION, OPPOSITION, ANALYSIS, DECISION from HD format.
    Sections may contain multiple sentences.
    """
    verdict_match = _VERDICT_LINE_RE.search(text)
    if not verdict_match:
        return None

    topic = verdict_match.group(1).strip()

    # Extract sections (may be multi-sentence)
    prop_match = _PROPOSITION_RE.search(text)
    oppo_match = _OPPOSITION_RE.search(text)
    analysis_match = _ANALYSIS_RE.search(text)
    decision_match = _DECISION_WINNER_RE.search(text)

    if not decision_match:
        return None

    return {
        "topic": topic,
        "proposition": _clean(prop_match.group(1)) if prop_match else "",
        "opposition": _clean(oppo_match.group(1)) if oppo_match else "",
        "analysis": _clean(analysis_match.group(1)) if analysis_match else "",
        "winner": decision_match.group(1).upper(),
        "reason": _clean(decision_match.group(2)),
    }


# ── Sentence Extraction ────────────────────────────────────────────────────

def _sentences(text: str) -> list[str]:
    """
    Split text into sentences, protecting abbreviations.
    """
    if not text:
        return []

    # Temporarily replace protected abbreviations
    protected = re.sub(
        r"\b(?:U\.S|Dr|Mr|Mrs|Ms|St|Inc|Ltd|e\.g|i\.e|vs|et al)\.",
        lambda m: m.group(0).replace(".", "§"),
        text
    )

    # Split on sentence boundaries (. ! ? followed by space and capital letter)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", protected)

    # Restore abbreviations
    sentences = [p.replace("§", ".").strip() for p in parts if p.strip()]
    return sentences


def _first_sentence(text: str) -> str:
    """Extract the first sentence from potentially multi-sentence text."""
    if not text:
        return ""

    sents = _sentences(text)

    if not sents:
        return text.strip()

    first = sents[0]

    # Ensure it ends with punctuation
    if first and not first.endswith(('.', '!', '?')):
        first += "."

    return first


def _truncate_to_clauses(text: str, max_len: int = 80) -> str:
    """
    Truncate to first clause (before —, –, :, or ;) if too long.
    Remove filler words first. Stricter max_len for Shorts budget.
    """
    if not text:
        return ""

    # Remove common filler words (not structural)
    text = re.sub(
        r'\b(also|furthermore|additionally|increasingly|both)\b\s*',
        '',
        text,
        flags=re.I
    )

    text = _clean(text)

    if len(text) <= max_len:
        return text

    # Find clause markers
    for marker in ("—", "–", ": ", "; "):
        idx = text.find(marker)
        if 15 < idx < len(text):  # Lower threshold
            # Found a clause break, truncate there
            clause = text[:idx].rstrip(" ,")
            if clause.endswith(('.', '!', '?')):
                return clause
            else:
                return clause + "."

    # No natural break found — truncate at word boundary
    if len(text) > max_len:
        truncated = text[:max_len].rsplit(' ', 1)[0]
        if not truncated.endswith(('.', '!', '?')):
            truncated += "."
        return truncated

    return text


# ── Mobile Builder ─────────────────────────────────────────────────────────

def _build_mobile(topic: str, proposition: str, opposition: str,
                  analysis: str, winner: str, reason: str) -> str:
    """
    Build mobile version with 1-sentence per section.
    """
    return (
        f"VERDICT: {topic}\n\n"
        f"SUMMARY\n\n"
        f"PROPOSITION: {proposition}\n\n"
        f"OPPOSITION: {opposition}\n\n"
        f"ANALYSIS\n\n"
        f"{analysis}\n\n"
        f"DECISION\n\n"
        f"{winner} WINS. {reason}\n"
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _clean(s: str) -> str:
    """Remove extra whitespace."""
    return re.sub(r"\s+", " ", s).strip()
