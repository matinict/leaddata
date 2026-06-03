"""
cf2/tools/classroom_script_parser.py
Parse classroom script.md into structured lines.
Each line: [TAG-G] Speaker: text
"""
import re
from dataclasses import dataclass, field
from typing import List, Optional

_PHASE_RE   = re.compile(r"^\[PHASE:(\w+)\]", re.IGNORECASE)
_SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+(\w[\w\s\-]*?):\s+(.+)$")
_QUIZ_RE    = re.compile(r"^\[QUIZ\](.*)", re.IGNORECASE)
_KEY_RE     = re.compile(r"^\[KEY POINTS?\](.*)", re.IGNORECASE)


@dataclass
class ScriptLine:
    phase:    str
    tag:      str        # e.g. T1, S1-F, S2-M
    tag_base: str        # e.g. T1, S1, S2
    speaker:  str
    text:     str
    line_no:  int


@dataclass
class ScriptBlock:
    phase: str
    lines: List[ScriptLine] = field(default_factory=list)
    quiz:  Optional[str]    = None
    keys:  List[str]        = field(default_factory=list)


def parse(raw: str) -> List[ScriptBlock]:
    blocks: List[ScriptBlock] = []
    current_phase = "hook"
    current_block = ScriptBlock(phase=current_phase)

    for i, raw_line in enumerate(raw.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        m = _PHASE_RE.match(line)
        if m:
            if current_block.lines:
                blocks.append(current_block)
            current_phase = m.group(1).lower()
            current_block = ScriptBlock(phase=current_phase)
            continue

        m = _QUIZ_RE.match(line)
        if m:
            current_block.quiz = m.group(1).strip()
            continue

        m = _KEY_RE.match(line)
        if m:
            current_block.keys.append(m.group(1).strip())
            continue

        m = _SPEAKER_RE.match(line)
        if m:
            tag      = m.group(1)
            tag_base = tag.split("-")[0].upper()
            current_block.lines.append(ScriptLine(
                phase    = current_phase,
                tag      = tag,
                tag_base = tag_base,
                speaker  = m.group(2).strip(),
                text     = m.group(3).strip(),
                line_no  = i,
            ))

    if current_block.lines:
        blocks.append(current_block)
    return blocks


def flat_lines(blocks: List[ScriptBlock]) -> List[ScriptLine]:
    return [l for b in blocks for l in b.lines]


def raw_dialogue_lines(raw: str) -> List[str]:
    """Return only raw dialogue lines (no PHASE/QUIZ/KEY lines)."""
    return [
        l.strip() for l in raw.splitlines()
        if l.strip() and _SPEAKER_RE.match(l.strip())
    ]
