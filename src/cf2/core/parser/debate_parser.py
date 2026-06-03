"""
Debate Parser — Debate-specific content extraction
Extends MarkdownParser with pro/con/moderator interleaving logic.
Handles debate markdown structure and block interleaving.

3-Judge Panel Support (v2):
  decide.md now contains three ## sections:
    ## SUMMARY  → judge_f  (Female Judge — en-CA-ClaraNeural)
    ## ANALYSIS → judge_m  (Male Judge   — en-CA-LiamNeural)
    ## DECISION → decide   (Chief Judge  — en-US-ChristopherNeural)

  Legacy single-block decide.md files are still supported via fallback.
"""

import re
from typing import List, Tuple, Dict

from cf2.core.parser.md_parser import MarkdownParser


class DebateParser:
    """
    Specialized parser for debate markdown files.

    Debate structure (3-judge, current):
        ## Propose
        Pro argument here

        ## Oppose
        Con argument here

        VERDICT: {topic}

        ## SUMMARY
        PROPOSITION: ...
        OPPOSITION: ...

        ## ANALYSIS
        Comparative logic assessment...

        ## DECISION
        PROPOSITION/OPPOSITION WINS. Reason.

    Debate structure (legacy, single-block):
        ## Propose / ## Oppose / ## Decide

    Responsibilities:
    - Extract propose / oppose / judge_f / judge_m / decide sections
    - Interleave blocks based on mode
    - Generate spoken text (no markdown)
    """

    # ── Role key constants ────────────────────────────────────────────────────
    ROLE_PROPOSE  = "propose"
    ROLE_OPPOSE   = "oppose"
    ROLE_JUDGE_M  = "judge_m"   # Male Judge  → SUMMARY section
    ROLE_JUDGE_F  = "judge_f"   # Female Judge    → ANALYSIS section
    ROLE_DECIDE   = "decide"    # Chief Judge   → DECISION section

    ALL_ROLES = [ROLE_PROPOSE, ROLE_OPPOSE, ROLE_JUDGE_F, ROLE_JUDGE_M, ROLE_DECIDE]

    # ── Section header alias maps ─────────────────────────────────────────────
    _PROPOSE_ALIASES = {"propose", "pro", "for", "argument 1", "pro_argument", "proposition"}
    _OPPOSE_ALIASES  = {"oppose", "con", "against", "argument 2", "con_argument", "opposition"}

    # 3-judge panel: content-named headers
    _SUMMARY_ALIASES  = {"summary"}                           # → judge_m
    _ANALYSIS_ALIASES = {"analysis"}                        # → judge_f
    _DECISION_ALIASES = {"decision"}                         # → decide (Chief)

    # Legacy single-block decide fallback
    _LEGACY_DECIDE_ALIASES = {"decide", "moderator", "conclusion", "verdict"}

    # ─────────────────────────────────────────────────────────────────────────
    # Core extraction
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def extract_roles(text: str) -> Dict[str, str]:
        """
        Extract propose / oppose / judge_m / judge_f / decide sections
        from a debate markdown file.

        Supports two formats:
          1. 3-judge panel  (## SUMMARY / ## ANALYSIS / ## DECISION)
          2. Legacy single  (## decide / ## moderator / ## conclusion)

        Returns:
            Dict with keys: propose, oppose, judge_m,judge_f,  decide
            Missing sections are returned as empty strings.
        """
        sections = MarkdownParser.extract_sections(text)
        roles: Dict[str, str] = {}

        for key, content in sections.items():
            if key in DebateParser._PROPOSE_ALIASES:
                roles[DebateParser.ROLE_PROPOSE] = content

            elif key in DebateParser._OPPOSE_ALIASES:
                roles[DebateParser.ROLE_OPPOSE] = content

            # ── 3-judge panel headers (content-named) ────────────────────────
            elif key in DebateParser._SUMMARY_ALIASES:
                roles[DebateParser.ROLE_JUDGE_M] = content   # Male   → LiamNeural

            elif key in DebateParser._ANALYSIS_ALIASES:
                roles[DebateParser.ROLE_JUDGE_F] = content   # Female → ClaraNeural

            elif key in DebateParser._DECISION_ALIASES:
                roles[DebateParser.ROLE_DECIDE] = content    # Chief  → ChristopherNeural

            # ── Legacy fallback: old single-block decide ──────────────────────
            elif key in DebateParser._LEGACY_DECIDE_ALIASES:
                # Only apply if 3-judge sections were NOT already found
                if (DebateParser.ROLE_JUDGE_F not in roles and
                        DebateParser.ROLE_JUDGE_M not in roles):
                    roles[DebateParser.ROLE_DECIDE] = content

        # Fill any missing roles with empty strings
        for role in DebateParser.ALL_ROLES:
            if role not in roles:
                roles[role] = ""

        return roles

    @staticmethod
    def extract_roles_spoken(text: str) -> Dict[str, str]:
        """
        Extract all roles and convert each to spoken text (strip markdown).

        Returns:
            Dict with same keys as extract_roles(), values clean for TTS.
        """
        roles = DebateParser.extract_roles(text)
        return {
            role: MarkdownParser.extract_spoken_text(content)
            for role, content in roles.items()
        }

    @staticmethod
    def has_panel_format(text: str) -> bool:
        """
        Return True if text uses the 3-judge panel format
        (contains ## SUMMARY, ## ANALYSIS, ## DECISION).
        Useful for callers that need to branch on format.
        """
        lower = text.lower()
        return (
            "## summary"  in lower and
            "## analysis" in lower and
            "## decision" in lower
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Argument splitting
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def split_into_arguments(text: str, role: str) -> List[str]:
        """
        Split a role's content into individual argument chunks.

        Heuristics (in priority order):
          1. Split by "Argument X:" / "Point X:" markers
          2. Fallback: treat as a single argument

        Args:
            text: Role content text
            role: Role key (propose, oppose,  judge_m, judge_f,decide)

        Returns:
            List of argument strings (never empty strings inside)
        """
        if not text.strip():
            return []

        argument_pattern = re.compile(
            r'^(?:Argument\s+\d+|Point\s+\d+)[:\.\s]',
            re.MULTILINE | re.IGNORECASE,
        )

        if argument_pattern.search(text):
            parts = argument_pattern.split(text)
            return [p.strip() for p in parts if p.strip()]

        return [text.strip()]

    # ─────────────────────────────────────────────────────────────────────────
    # Interleaving
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def interleave_blocks(
        propose_text: str,
        oppose_text: str,
        decide_text: str,
        interleave_mode: str = "balanced",
        judge_f_text: str = "",
        judge_m_text: str = "",
    ) -> List[Tuple[str, str]]:
        """
        Interleave propose / oppose / judge panel blocks into ordered sequence.

        Modes:
          "balanced"   — Alternate pro/con, then panel (default)
          "sequential" — All pro → all con → panel
          "rebuttal"   — Alternating pro/con pairs → panel
          "panel"      — Alternate pro/con, then judge_f → judge_m → decide

        Args:
            propose_text:   PRO side content
            oppose_text:    CON side content
            decide_text:    Chief Judge DECISION content
            interleave_mode: One of the modes above
            judge_f_text:   Female Judge SUMMARY content (3-judge panel)
            judge_m_text:   Male Judge ANALYSIS content (3-judge panel)

        Returns:
            List of (role, text) tuples in playback order.
        """
        mode = interleave_mode.lower()

        pro_args = DebateParser.split_into_arguments(propose_text, "propose")
        con_args = DebateParser.split_into_arguments(oppose_text, "oppose")

        result: List[Tuple[str, str]] = []

        # ── Build debate body (pro/con interleave) ────────────────────────────
        def _interleave_pro_con() -> List[Tuple[str, str]]:
            body = []
            max_args = max(len(pro_args), len(con_args), 1)
            for i in range(max_args):
                if i < len(pro_args):
                    body.append((DebateParser.ROLE_PROPOSE, pro_args[i]))
                if i < len(con_args):
                    body.append((DebateParser.ROLE_OPPOSE, con_args[i]))
            return body

        # ── Append judge panel ────────────────────────────────────────────────
        def _append_panel(r: List[Tuple[str, str]]) -> None:
            if judge_f_text.strip():
                r.append((DebateParser.ROLE_JUDGE_M, judge_m_text.strip()))
            if judge_m_text.strip():
                r.append((DebateParser.ROLE_JUDGE_F, judge_f_text.strip()))
            if decide_text.strip():
                r.append((DebateParser.ROLE_DECIDE, decide_text.strip()))

        # ── Legacy decide append (no panel roles) ────────────────────────────
        def _append_decide(r: List[Tuple[str, str]]) -> None:
            if decide_text.strip():
                r.append((DebateParser.ROLE_DECIDE, decide_text.strip()))

        if mode == "sequential":
            for arg in pro_args:
                result.append((DebateParser.ROLE_PROPOSE, arg))
            for arg in con_args:
                result.append((DebateParser.ROLE_OPPOSE, arg))
            if judge_f_text or judge_m_text:
                _append_panel(result)
            else:
                _append_decide(result)

        elif mode == "rebuttal":
            max_args = max(len(pro_args), len(con_args), 1)
            for i in range(max_args):
                if i < len(pro_args):
                    result.append((DebateParser.ROLE_PROPOSE, pro_args[i]))
                if i < len(con_args):
                    result.append((DebateParser.ROLE_OPPOSE, con_args[i]))
            if judge_f_text or judge_m_text:
                _append_panel(result)
            else:
                _append_decide(result)

        elif mode == "panel":
            # Explicit panel mode: always uses judge_f / judge_m / decide
            result.extend(_interleave_pro_con())
            _append_panel(result)

        else:  # "balanced" (default)
            result.extend(_interleave_pro_con())
            if judge_f_text or judge_m_text:
                _append_panel(result)
            else:
                _append_decide(result)

        return result

    @staticmethod
    def interleave_spoken(
        propose_text: str,
        oppose_text: str,
        decide_text: str,
        interleave_mode: str = "balanced",
        judge_f_text: str = "",
        judge_m_text: str = "",
    ) -> List[Tuple[str, str]]:
        """
        Interleave blocks after converting all content to spoken text (TTS-ready).

        Strips markdown formatting before interleaving.
        """
        pro_spoken     = MarkdownParser.extract_spoken_text(propose_text)
        con_spoken     = MarkdownParser.extract_spoken_text(oppose_text)
        mod_spoken     = MarkdownParser.extract_spoken_text(decide_text)
        judge_m_spoken = MarkdownParser.extract_spoken_text(judge_m_text)
        judge_f_spoken = MarkdownParser.extract_spoken_text(judge_f_text)

        return DebateParser.interleave_blocks(
            pro_spoken, con_spoken, mod_spoken,
            interleave_mode,
            judge_m_spoken,judge_f_spoken, 
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Frame / timing utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def build_lines_map(
        raw_lines: List[Tuple[str, str]],
        duration_per_line: float,
        fps: int = 24,
    ) -> Dict[int, Tuple[str, str]]:
        """
        Build a frame-number → (role, text) mapping for video rendering.

        Args:
            raw_lines:         List of (role, text) tuples
            duration_per_line: Seconds each line occupies
            fps:               Frames per second

        Returns:
            Dict: frame_number → (role, text)
        """
        frames_per_line = int(duration_per_line * fps)
        lines_map: Dict[int, Tuple[str, str]] = {}
        current_frame = 0

        for role, text in raw_lines:
            for offset in range(frames_per_line):
                lines_map[current_frame + offset] = (role, text)
            current_frame += frames_per_line

        return lines_map

    @staticmethod
    def estimate_timing(
        interleaved: List[Tuple[str, str]],
        wpm: int = 150,
    ) -> Dict[str, float]:
        """
        Estimate total spoken duration per role.

        Args:
            interleaved: List of (role, text) tuples
            wpm:         Words per minute (default 150)

        Returns:
            Dict: role → total estimated seconds
        """
        totals: Dict[str, float] = {}
        for role, text in interleaved:
            duration = MarkdownParser.estimate_duration(text, wpm)
            totals[role] = totals.get(role, 0.0) + duration
        return totals
