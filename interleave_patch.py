import re

path = "/var/POAi/CrewAiFlow/cf2/src/cf2/tools/debate_video.py"
content = open(path, encoding="utf-8").read()

# ── Patch 1: replace raw assembly + raw_lines parse with interleaved version ──
OLD_RAW = '''                # ── Combine into single narrative ─────────────────────────
                raw = "\\n\\n".join([
                    f"PROPOSITION:\\n{pro_text}",
                    f"OPPOSITION:\\n{con_text}",
                    f"VERDICT:\\n{moderator_text}",
                ])

                # ── Parse lines ─────────────────────────────────────────────
                # short_form flag is passed but logic inside _parse_lines is disabled
                # to ensure FULL content of the source file is used.
                raw_lines = self._parse_lines(raw, short_form=_is_short_form)'''

NEW_RAW = '''                # ── Interleave PRO/CON blocks: Arg1→Counter1→Arg2→Counter2… ──
                raw_lines = self._interleave_blocks(
                    pro_text, con_text, moderator_text,
                    short_form=_is_short_form
                )'''

# ── Patch 2: replace sequential _pro_spoken/_con_spoken with interleaved audio ──
OLD_SPOKEN = '''                # ── Build per-section spoken text ────────────────────────
                # Pass short_form=True but internal filtering is disabled
                _pro_spoken = self._section_to_spoken(pro_text, "propose", channel, short_form=_is_short_form)
                _con_spoken = self._section_to_spoken(con_text, "oppose", channel, short_form=_is_short_form)
                _mod_spoken = self._section_to_spoken(moderator_text, "decide", channel, short_form=_is_short_form)

                # Safety: if MOD parsed to empty, use raw text
                if not _mod_spoken.strip():
                    _mod_spoken = moderator_text.strip() # No cleaning'''

NEW_SPOKEN = '''                # ── Build interleaved spoken text per block ──────────────
                _interleaved_spoken = self._interleave_spoken(
                    pro_text, con_text, short_form=_is_short_form
                )
                _pro_spoken = _interleaved_spoken  # full interleaved PRO+CON audio
                _con_spoken = ""                   # merged into _pro_spoken
                _mod_spoken = self._section_to_spoken(moderator_text, "decide", channel, short_form=_is_short_form)
                if not _mod_spoken.strip():
                    _mod_spoken = moderator_text.strip()'''

if OLD_RAW in content and OLD_SPOKEN in content:
    content = content.replace(OLD_RAW, NEW_RAW)
    content = content.replace(OLD_SPOKEN, NEW_SPOKEN)

    # ── Inject the two new methods before _build_frames_map ──────────────
    INJECT_BEFORE = "    def _build_frames_map("
    NEW_METHODS = '''    def _interleave_blocks(self, pro_text: str, con_text: str, mod_text: str,
                           short_form: bool = False) -> list:
        """
        Parse propose/oppose into argument blocks and interleave:
        PRO-opening → CON-opening → PRO-arg1 → CON-counter1 → … → VERDICT
        """
        pro_blocks = re.split(r'(?=^Argument \\d+:)', pro_text, flags=re.MULTILINE)
        con_blocks = re.split(r'(?=^Counter-Argument \\d+:)', con_text, flags=re.MULTILINE)

        result = []
        max_pairs = max(len(pro_blocks), len(con_blocks))

        for i in range(max_pairs):
            if i < len(pro_blocks) and pro_blocks[i].strip():
                block = f"PROPOSITION:\\n{pro_blocks[i].strip()}"
                result += self._parse_lines(block, short_form=short_form)
            if i < len(con_blocks) and con_blocks[i].strip():
                block = f"OPPOSITION:\\n{con_blocks[i].strip()}"
                result += self._parse_lines(block, short_form=short_form)

        if mod_text.strip():
            result += self._parse_lines(f"VERDICT:\\n{mod_text.strip()}", short_form=short_form)

        return result

    def _interleave_spoken(self, pro_text: str, con_text: str,
                           short_form: bool = False) -> str:
        """
        Build interleaved spoken text: PRO-block0, CON-block0, PRO-block1, CON-block1 …
        Returns single string for TTS — CON voice handled by role tag in _tts_single.
        NOTE: caller passes this as _pro_spoken; _con_spoken is set to empty.
        """
        pro_blocks = re.split(r'(?=^Argument \\d+:)', pro_text, flags=re.MULTILINE)
        con_blocks = re.split(r'(?=^Counter-Argument \\d+:)', con_text, flags=re.MULTILINE)

        parts = []
        max_pairs = max(len(pro_blocks), len(con_blocks))
        for i in range(max_pairs):
            if i < len(pro_blocks) and pro_blocks[i].strip():
                items = self._parse_lines(
                    f"PROPOSITION:\\n{pro_blocks[i].strip()}", short_form=short_form
                )
                parts.append(" ".join(t for t, _ in items if t))
            if i < len(con_blocks) and con_blocks[i].strip():
                items = self._parse_lines(
                    f"OPPOSITION:\\n{con_blocks[i].strip()}", short_form=short_form
                )
                parts.append(" ".join(t for t, _ in items if t))
        return " ".join(p for p in parts if p)

    def _build_frames_map('''

    content = content.replace(INJECT_BEFORE, NEW_METHODS, 1)
    open(path, "w", encoding="utf-8").write(content)
    print("✅ interleave patch applied")
else:
    print("❌ OLD pattern not found — check exact whitespace")
    if OLD_RAW not in content:
        print("  → OLD_RAW missing")
    if OLD_SPOKEN not in content:
        print("  → OLD_SPOKEN missing")
