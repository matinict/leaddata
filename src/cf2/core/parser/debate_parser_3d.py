"""
core/parser/debate_parser_3d.py — Robust 3D Debate Block Parser

Responsibility: Parse pro/con/mod markdown files into keyed blocks.
Handles short debates, mini-debates, and abbreviation variants.
Pure text processing — no file I/O.

3-Judge Panel Support:
  decide.md contains three ## sections:

    ## SUMMARY   → block_id: sum  → voice role: judge_m  (en-CA-LiamNeural)
    ## ANALYSIS  → block_id: aly  → voice role: judge_f  (en-CA-ClaraNeural)
    ## DECISION  → block_id: win  → voice role: decide   (en-US-ChristopherNeural)

  Legacy two-section format (ANALYSIS + DECISION) is still supported via fallback.
  Single-block legacy is also handled.

Block voice routing:
    BLOCK_VOICE_MAP = {
        "sum":"judge_m",   # Male Judge    → en-CA-LiamNeural
        "aly": "judge_f",   # Female Judge  → en-CA-ClaraNeural
        "win": "decide",    # Chief Judge   → en-US-ChristopherNeural
    }
"""

import re
from typing import List, Tuple, Dict
from pathlib import Path


# ── Type alias ────────────────────────────────────────────────────────────────
Block = Tuple[str, str, str]   # (role, block_id, text)


# ── Voice routing map ─────────────────────────────────────────────────────────
BLOCK_VOICE_MAP: Dict[str, str] = {
    "sum":"judge_m",   # Male Judge    → en-CA-LiamNeural
    "aly": "judge_f",   # Female Judge  → en-CA-ClaraNeural
    "win": "decide",    # Chief Judge   → en-US-ChristopherNeural
}


# ── Compiled patterns ─────────────────────────────────────────────────────────
_PRO_PATTERN = re.compile(
    r"(?=(?:^|\n)\s*(?:Proposition|Prop|PROPOSITION|PROP|Argument|Arg|ARG|A\d+)\s*\d*[:\s]"
    r"|(?:^|\n)\s*OPENING\s*STATEMENT?\s*:?(?:\n|$))",
    re.MULTILINE | re.IGNORECASE,
)
_CON_PATTERN = re.compile(
    r"(?=(?:^|\n)\s*(?:Opposition|Opp|OPPOSITION|OPP|Counter-Argument|Counter-Arg|C-Arg|CA|Con|C\d+)\s*\d*[:\s]"
    r"|(?:^|\n)\s*OPENING\s*STATEMENT?\s*:?(?:\n|$))",
    re.MULTILINE | re.IGNORECASE,
)
_HEADER_RE = re.compile(
    r"^(?:Proposition|Prop|Opposition|Opp|Argument|Arg|Counter-Argument|Counter-Arg"
    r"|C-Arg|CA|Con|Opening|Conclusion|Final|Verdict|Analysis|Decision|Summary)[\s\-]*\d*[:\s]*",
    re.IGNORECASE,
)
_SEMANTIC_IDX_RE = re.compile(
    r"^(?:Proposition|Prop|Opposition|Opp|Argument|Arg|Counter-Argument|Counter-Arg"
    r"|C-Arg|CA|Con|Opening|Conclusion|Final|Verdict|Analysis|Decision|Summary)[\s\-]*(\d+)",
    re.IGNORECASE,
)

# ── Panel section header patterns ─────────────────────────────────────────────
_PANEL_SUMMARY_RE  = re.compile(r"^SUMMARY\s*$",  re.IGNORECASE | re.MULTILINE)
_PANEL_ANALYSIS_RE = re.compile(r"^ANALYSIS\s*$", re.IGNORECASE | re.MULTILINE)
_PANEL_DECISION_RE = re.compile(r"^DECISION\s*$", re.IGNORECASE | re.MULTILINE)

# ── Legacy section fallback patterns ─────────────────────────────────────────
_LEGACY_ANALYSIS_WORDS = ("analysis",)
_LEGACY_DECISION_WORDS = ("decision", "verdict", "final", "conclusion")


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Strip block header label from first line."""
    if not text:
        return ""
    lines = text.strip().split("\n")
    m = _HEADER_RE.match(lines[0])
    if m:
        rest = lines[0][m.end():].strip()
        tail = ("\n" + "\n".join(lines[1:])) if len(lines) > 1 else ""
        return (rest + tail).strip() if rest else "\n".join(lines[1:]).strip()
    return text.strip()


def _block_id(chunk: str, prefix: str, fallback: int) -> str:
    """Derive semantic block_id from first line, e.g. 'p1', 'c2'."""
    first = chunk.strip().split("\n")[0] if chunk.strip() else ""
    m = _SEMANTIC_IDX_RE.match(first.strip())
    return f"{prefix}{m.group(1)}" if m else f"{prefix}{fallback}"


def _strip_section_header(text: str, *headers: str) -> str:
    """Remove ## HEADER and bare HEADER lines from a block."""
    result = text
    for hdr in headers:
        result = re.sub(rf"^##\s*{re.escape(hdr)}\s*\n?", "", result,
                        flags=re.IGNORECASE | re.MULTILINE)
        result = re.sub(rf"^{re.escape(hdr)}\s*\n?", "", result,
                        flags=re.IGNORECASE | re.MULTILINE)
    return result.strip()


def _detect_panel_format(mod_text: str) -> bool:
    """Return True if mod_text has ## SUMMARY, ## ANALYSIS, ## DECISION."""
    return (
        bool(_PANEL_SUMMARY_RE.search(mod_text)) and
        bool(_PANEL_ANALYSIS_RE.search(mod_text)) and
        bool(_PANEL_DECISION_RE.search(mod_text))
    )


# ─────────────────────────────────────────────────────────────────────────────
# Moderator block parser
# ─────────────────────────────────────────────────────────────────────────────

def _add_mod_blocks(mod_text: str, blocks: List[Block]) -> None:
    """
    Parse moderator/decide text and append (decide, block_id, text) tuples.

    Block IDs produced:
      Panel format    : sum, aly, win
      Legacy 2-part   : aly, win
      Legacy 1-part   : win  OR  aly
    """
    if not mod_text.strip():
        return

    # ── Format 1: 3-judge panel ──────────────────────────────────────────────
    if _detect_panel_format(mod_text):
        _parse_panel_format(mod_text, blocks)
        return

    # ── Format 2: Legacy two-section ─────────────────────────────────────────
    lower        = mod_text.lower()
    idx_analysis = _find_first(lower, _LEGACY_ANALYSIS_WORDS)
    idx_decision = _find_first(lower, _LEGACY_DECISION_WORDS)

    if idx_analysis != -1 and idx_decision != -1 and idx_analysis < idx_decision:
        analysis_txt = _strip_section_header(
            mod_text[idx_analysis:idx_decision], "analysis"
        )
        verdict_txt = _strip_section_header(
            mod_text[idx_decision:], "decision", "verdict", "final", "conclusion"
        )
        if analysis_txt:
            blocks.append(("decide", "aly", analysis_txt))
        if verdict_txt:
            blocks.append(("decide", "win", verdict_txt))
        return

    # ── Format 3: Legacy single block ────────────────────────────────────────
    clean = _clean(mod_text)
    if clean:
        key = "win" if any(w in lower for w in _LEGACY_DECISION_WORDS) else "aly"
        blocks.append(("decide", key, clean))


def _parse_panel_format(mod_text: str, blocks: List[Block]) -> None:
    """
    Extract three judge blocks from panel-format mod_text.

    ## SUMMARY  → block_id: sum  (Female Judge)
    ## ANALYSIS → block_id: aly  (Male Judge)
    ## DECISION → block_id: win  (Chief Judge)
    """
    m_summary  = _PANEL_SUMMARY_RE.search(mod_text)
    m_analysis = _PANEL_ANALYSIS_RE.search(mod_text)
    m_decision = _PANEL_DECISION_RE.search(mod_text)

    if not (m_summary and m_analysis and m_decision):
        return

    summary_raw  = mod_text[m_summary.end()  : m_analysis.start()].strip()
    analysis_raw = mod_text[m_analysis.end() : m_decision.start()].strip()
    verdict_raw  = mod_text[m_decision.end()                      :].strip()

    if summary_raw:
        blocks.append(("decide", "sum", summary_raw))
    if analysis_raw:
        blocks.append(("decide", "aly", analysis_raw))
    if verdict_raw:
        blocks.append(("decide", "win", verdict_raw))


def _find_first(text: str, words: Tuple[str, ...]) -> int:
    """Return the index of the first occurrence of any word in text, or -1."""
    positions = [text.find(w) for w in words if text.find(w) != -1]
    return min(positions) if positions else -1


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def parse(pro_text: str, con_text: str, mod_text: str) -> List[Block]:
    """
    Parse three debate sections into ordered, keyed blocks.

    Returns:
        List of (role, block_id, text) where:
          role     ∈ {propose, oppose, decide}
          block_id ∈ {p0, p1, …, c0, c1, …, sum, aly, win}

    Voice routing — use BLOCK_VOICE_MAP:
          sum →judge_m  (en-CA-LiamNeural)
          aly → judge_f  (en-CA-ClaraNeural)
          win → decide   (en-US-ChristopherNeural)
    """
    blocks: List[Block] = []

    pro_split = _PRO_PATTERN.split(pro_text)
    con_split = _CON_PATTERN.split(con_text)

    pro_counter = con_counter = 0

    for i in range(max(len(pro_split), len(con_split))):
        if i < len(pro_split) and pro_split[i].strip():
            txt = _clean(pro_split[i])
            if txt:
                blocks.append(("propose", _block_id(pro_split[i], "p", pro_counter), txt))
                pro_counter += 1

        if i < len(con_split) and con_split[i].strip():
            txt = _clean(con_split[i])
            if txt:
                blocks.append(("oppose", _block_id(con_split[i], "c", con_counter), txt))
                con_counter += 1

    if mod_text.strip():
        _add_mod_blocks(mod_text, blocks)

    return blocks


def build_block_map(blocks: List[Block]) -> Dict[Tuple[str, str], str]:
    """Convert block list → (role, block_id) lookup dict."""
    return {(role, bid): text for role, bid, text in blocks}


def resolve_voice_key(block_id: str, role: str) -> str:
    """
    Resolve which voice key to use for a given block.

    BLOCK_VOICE_MAP overrides raw role for sum/aly/win.
    All other blocks use the role itself as the voice key.

    Returns voice key for lookup in edge_tts_voices config.
    """
    return BLOCK_VOICE_MAP.get(block_id, role)


def compress_file(src: Path, max_chars: int = 1500) -> str:
    """
    Return a compressed version of src text (for Shorts -m variant).
    Does NOT write file — caller decides where to save.
    """
    text = src.read_text(encoding="utf-8")
    if len(text) <= max_chars:
        return text
    cut = text.rfind(".", 0, max_chars - 100)
    if cut == -1:
        cut = max_chars - 100
    return text[: cut + 1] + "\n...(truncated)..."
