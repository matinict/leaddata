"""
Debate Definition Tool (OPTIMIZED v8)
Auto-generates debate files for video factory.
All compression config lives in data/label_mappings.json:
debate_labels       -> abbreviation map (longest-match first)
debate_compression  -> aux_strip, article_strip, mobile_caps,
                       hard_cap_ratio, header_prefixes, strip_trailing_to
Smart skip: if all 6 .md files exist, returns immediately.
Full version : compressed to debate_max_chars for HD video.
Mobile version: Shorts-optimised with per-role char caps from JSON.
Triggered by: "debate_definition_enabled": true in data.json

ALL files read/written inside output_dir/debate/ subfolder.
"""
import json
import os
import re
import time
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field

class DebateDefinitionToolInput(BaseModel):
    topic: str = Field(..., description="Full debate topic/motion")
    filename: str = Field(..., description="Base filename slug")
    output_dir: str = Field(..., description="Output subdirectory for debate files")
    propose_text: str = Field(default="", description="Arguments supporting the motion (FOR) — leave empty to read from disk")
    oppose_text: str = Field(default="", description="Arguments against the motion (AGAINST) — leave empty to read from disk")
    decide_text: str = Field(default="", description="Moderator's conclusion/verdict — leave empty to read from disk")
    debate_definition_enabled: bool = Field(default=False, description="Whether to process debate definitions")
    channel: str = Field(default="", description="Channel name for branding — must come from data.json, never hardcoded")
    debate_max_chars: int = Field(default=0, description="Hard cap on each debate argument in characters — must come from data.json")
    lang_suffix: str = Field(default="", description="Language suffix for output .md filenames — must come from data.json")
    use_label_mappings: bool = Field(default=False, description="Apply abbreviation map only to -m.md (Shorts) files")
    force_regenerate: bool = Field(default=False, description="Force rewrite of all .md files even if they already exist")

class DebateDefinitionTool(BaseTool):
    name: str = "DebateDefinition"
    description: str = (
        "Auto-generates debate files for video factory. "
        "All compression config is driven by data/label_mappings.json. "
        "Reads and writes all files from output_dir/debate/ subfolder."
    )
    args_schema: Type[BaseModel] = DebateDefinitionToolInput

    # ── In-process cache — reloads only if file changes ──────────────────────
    _cfg_cache: dict = {}
    _cfg_mtime: float = 0.0

    @classmethod
    def _find_label_mappings(cls) -> str:
        """Walk up from this file until data/label_mappings.json is found."""
        current = os.path.dirname(os.path.abspath(__file__))
        for _ in range(6):
            candidate = os.path.join(current, 'data', 'label_mappings.json')
            if os.path.exists(candidate):
                return candidate
            current = os.path.dirname(current)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'label_mappings.json')

    @classmethod
    def _load_cfg(cls) -> dict:
        """Load label_mappings.json; reload automatically if file is updated."""
        try:
            path = cls._find_label_mappings()
            mtime = os.path.getmtime(path)
            if cls._cfg_cache and mtime == cls._cfg_mtime:
                return cls._cfg_cache
            with open(path, 'r', encoding='utf-8') as f:
                cls._cfg_cache = json.load(f)
            cls._cfg_mtime = mtime
            print(f"[DebateDef] Loaded label_mappings from: {path}")
        except Exception as e:
            print(f"[DebateDef] WARNING label_mappings.json not loaded: {e}")
            cls._cfg_cache = {}
        return cls._cfg_cache

    @classmethod
    def _debate_labels(cls) -> list:
        """debate_labels sorted longest-key first (prevents partial matches).
        Sorting is global across ALL keys before any split — guarantees
        multi-word keys like 'machine learning' (15) beat 'learning' (8)
        regardless of header/body category."""
        labels = cls._load_cfg().get('debate_labels', {})
        return sorted(labels.items(), key=lambda x: len(x[0]), reverse=True)

    @classmethod
    def _compression(cls) -> dict:
        return cls._load_cfg().get('debate_compression', {})

    # ── Main entry point ──────────────────────────────────────────────────────
    def _run(
        self,
        topic: str,
        filename: str,
        output_dir: str,
        propose_text: str,
        oppose_text: str,
        decide_text: str,
        debate_definition_enabled: bool = False,
        channel: str = "",
        debate_max_chars: int = 0,
        lang_suffix: str = "",
        use_label_mappings: bool = False,
        force_regenerate: bool = False,
    ) -> str:

        t0 = time.time()

        if not debate_definition_enabled:
            return "Debate definition skipped (debate_definition_enabled=false)"

        _lang = lang_suffix or self._compression().get('default_lang_suffix', '')
        if not _lang:
            return "ERROR: lang_suffix not provided and 'default_lang_suffix' missing from debate_compression in label_mappings.json"

        if not debate_max_chars:
            debate_max_chars = self._compression().get('default_debate_max_chars', 0)
        if not debate_max_chars:
            return "ERROR: debate_max_chars not provided and 'default_debate_max_chars' missing from debate_compression in label_mappings.json"
        # ── ALL files live in output_dir/debate/ ─────────────────────────────
        _debate_dir = os.path.join(output_dir, "debate")    # ← restore this line
        _md_paths   = {r: os.path.join(_debate_dir, f"{r}.md")
                       for r in ('propose', 'oppose', 'decide')}
        _mobile_paths = {r: os.path.join(_debate_dir, f"{r}-m.md")
                         for r in ('propose', 'oppose', 'decide')}

        # ── SMART SKIP: all 6 files exist AND already within mobile caps ────────
        # WHY the cap-check is required:
        #   Tasks debate_propose_m / debate_oppose_m / debate_decide_m write raw
        #   LLM output directly to -m.md via tasks.yaml `output_file`. That output
        #   is uncompressed. When this tool runs next, all 6 files already exist,
        #   so the old simple `_all_exist` skip fired — mobile_caps were NEVER
        #   applied. Now we only skip when every -m.md is provably within its cap.
        _all_exist = all(
            os.path.exists(p) and os.path.getsize(p) > 0
            for p in list(_md_paths.values()) + list(_mobile_paths.values())
        )

        if _all_exist and not force_regenerate and not use_label_mappings:
            # Read configured caps early so we can validate existing files
            _pre_caps = self._compression().get('mobile_caps', {})
            _cap_limits = {
                'propose': _pre_caps.get('propose'),
                'oppose':  _pre_caps.get('oppose'),
                'decide':  _pre_caps.get('decide'),
            }
            if not all(_cap_limits.values()):
                return "ERROR: mobile_caps.propose/oppose/decide missing from debate_compression in label_mappings.json"
            _over_cap = {}
            for role, path in _mobile_paths.items():
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        _content = f.read()
                    if len(_content) > _cap_limits[role]:
                        _over_cap[role] = (len(_content), _cap_limits[role])
                except Exception:
                    pass  # unreadable → fall through to reprocess

            if not _over_cap:
                # All -m.md files are within caps — genuine skip
                _sizes  = {r: os.path.getsize(p) for r, p in _md_paths.items()}
                _msizes = {r: os.path.getsize(p) for r, p in _mobile_paths.items()}
                print(f"[DebateDef] All 6 debate files exist and within caps — skipping")
                lines = [
                    f"   OK {r}.md ({_sizes[r]} B)  {r}-m.md ({_msizes[r]} B)"
                    for r in ('propose', 'oppose', 'decide')
                ]
                return "Debate files exist — skipping\n" + "\n".join(lines)
            else:
                # At least one -m.md exceeds its cap (LLM wrote it uncompressed)
                for role, (actual, cap) in _over_cap.items():
                    print(f"[DebateDef] {role}-m.md is {actual} chars > cap {cap} — recompressing")

        if _all_exist and use_label_mappings and not force_regenerate:
            print(f"[DebateDef] use_label_mappings=True — regenerating -m.md with abbreviations")
        if _all_exist and force_regenerate:
            print(f"[DebateDef] force_regenerate=True — overwriting all 6 files")

        # ── Load texts — agent-passed or disk fallback ────────────────────────
        all_texts = {
            'propose': self._load_text(propose_text, _debate_dir, 'propose', _lang),
            'oppose':  self._load_text(oppose_text,  _debate_dir, 'oppose',  _lang),
            'decide':  self._load_text(decide_text,  _debate_dir, 'decide',  _lang),
        }
        for role, text in all_texts.items():
            if not text:
                return (
                    f"ERROR: {role}_text is empty and no .md found in {_debate_dir}. "
                    f"Complete all 3 arguments first."
                )

        os.makedirs(_debate_dir, exist_ok=True)

        # ── Mobile caps — must come from label_mappings.json, no fallbacks ─────
        cfg_caps = self._compression().get('mobile_caps', {})
        mobile_caps = {
            'propose': cfg_caps.get('propose'),
            'oppose':  cfg_caps.get('oppose'),
            'decide':  cfg_caps.get('decide'),
        }
        if not all(mobile_caps.values()):
            return "ERROR: mobile_caps.propose/oppose/decide missing from debate_compression in label_mappings.json"

        results = []
        for role, raw in all_texts.items():
            orig_chars = len(raw)

            # Full / HD version — abbreviations always OFF for HD
            cleaned = self._clean_debate_text(raw, debate_max_chars, apply_abbrev=False)
            with open(_md_paths[role], 'w', encoding='utf-8') as f:
                f.write(cleaned)
            print(f"[DebateDef] Saved {_md_paths[role]} ({len(cleaned)} chars)")

            # Mobile / Shorts version — abbreviations ON only when use_label_mappings=True
            # ── NEW: read LLM -m.md if it exists, apply abbrev only ────
            _m_path = _mobile_paths[role]
            if os.path.exists(_m_path) and os.path.getsize(_m_path) > 0:
                with open(_m_path, 'r', encoding='utf-8') as f:
                    _m_raw = f.read().strip()
                mobile = self._make_mobile(_m_raw, mobile_caps[role], apply_abbrev=use_label_mappings)
            else:
                mobile = self._make_mobile(raw, mobile_caps[role], apply_abbrev=use_label_mappings)
            with open(_mobile_paths[role], 'w', encoding='utf-8') as f:
                f.write(mobile)
            print(f"[DebateDef] Saved {_mobile_paths[role]} ({len(mobile)} chars)")

            results.append({
                'role': role, 'original': orig_chars,
                'cleaned': len(cleaned), 'mobile': len(mobile),
            })

        elapsed = time.time() - t0
        summary = f"Debate files generated in {elapsed:.1f}s\n\n"
        for r in results:
            saved = r['original'] - r['cleaned']
            summary += (
                f"{r['role'].upper()}: {r['original']} -> {r['cleaned']} chars "
                f"(saved {saved}) | mobile {r['mobile']} chars\n"
            )
        summary += (
            f"\nFiles: {_debate_dir}/\n"
            f"  Full  : propose.md  oppose.md  decide.md\n"
            f"  Mobile: propose-m.md  oppose-m.md  decide-m.md\n"
            f"-> ready for debate_video_tool"
        )
        print(f"[DebateDef] Complete in {elapsed:.1f}s")
        return summary

    # ── Internal helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _load_text(passed: str, debate_dir: str, role: str, lang: str) -> str:
        """Return passed text if non-empty, else read from debate_dir on disk.
        Tries: {role}.md → {role}_{lang}.md (legacy)."""
        if passed and passed.strip():
            return passed.strip()
        for path in (
            os.path.join(debate_dir, f'{role}.md'),
            os.path.join(debate_dir, f'{role}_{lang}.md'),
        ):
            if os.path.exists(path) and os.path.getsize(path) > 0:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read().strip()
        return ''

    def _clean_debate_text(self, text: str, max_chars: int = 5000, apply_abbrev: bool = False) -> str:
        """Full/HD compression: pre-clean → optionally abbreviate → strip aux → collapse → hard cap.
        apply_abbrev is always False for HD — full names preserved."""
        text = self._pre_clean(text)
        if apply_abbrev:
            text = self._apply_abbreviations(text)
        text = self._strip_aux_and_articles(text)
        text = self._collapse_whitespace(text)
        return self._hard_cap(text, max_chars)

    def _make_mobile(self, text: str, max_chars: int = 2000, apply_abbrev: bool = False) -> str:
        """Shorts compression with STRICT hard cap.
        Guarantees final output NEVER exceeds max_chars."""
        text = self._pre_clean(text)
        if apply_abbrev:
            text = self._apply_abbreviations(text)
        text = self._strip_aux_and_articles(text)
        text = self._collapse_whitespace(text)

        if len(text) <= max_chars:
            return text

        blocks = re.split(r'\n{2,}', text)
        blocks = [b.strip() for b in blocks if b.strip()]
        n = len(blocks)

        if n == 0:
            return self._clean_tail(text[:max_chars])

        separator_cost = (n - 1) * 2
        usable_chars   = max_chars - separator_cost

        if usable_chars <= 0:
            return self._clean_tail(text[:max_chars])

        total_len  = sum(len(b) for b in blocks)
        new_blocks = []

        for blk in blocks:
            share = max(int(len(blk) / total_len * usable_chars), 20)

            if len(blk) <= share:
                new_blocks.append(blk)
                continue

            words = blk.split()
            trimmed_words = []
            for w in words:
                test = " ".join(trimmed_words + [w])
                if len(test) > share:
                    break
                trimmed_words.append(w)

            trimmed = " ".join(trimmed_words)
            trimmed = self._clean_tail(trimmed, min_words=3)
            new_blocks.append(trimmed)

        result = "\n\n".join(new_blocks)

        if len(result) > max_chars:
            result = self._clean_tail(result[:max_chars], min_words=3)

        return result

    def _clean_tail(self, text: str, min_words: int = 3) -> str:
        """Remove orphan trailing fragments after the last clean sentence boundary."""
        text = re.sub(r'[\s,;:\-]+$', '', text)
        for m in reversed(list(re.finditer(r'[.!?]', text))):
            candidate = text[:m.end()].strip()
            if len(candidate.split()) >= min_words and len(candidate) >= len(text) * 0.55:
                return candidate
        m2 = re.search(r'[,;]\s*\S+(\s+\S+)?\s*$', text)
        if m2:
            candidate = text[:m2.start()].strip()
            if len(candidate.split()) >= min_words:
                return candidate
        return text

    @classmethod
    def _regex_patterns(cls) -> list:
        """All regex patterns from label_mappings.json -> debate_regex_patterns."""
        cfg = cls._load_cfg().get('debate_regex_patterns', {})
        patterns = []
        for key, pairs in cfg.items():
            if key.startswith('_'):
                continue
            patterns.extend(pairs)
        return patterns

    @staticmethod
    def _pre_clean(text: str) -> str:
        """Strip known artifact patterns before label map runs."""
        text = re.sub(r'\(\s*(?:None|[0-9]{4})\s*[–\-]\s*(?:None|[0-9]{4})\s*\)\s*', '', text)
        text = re.sub(r'\(\s*[–\-]\s*\)\s*', '', text)
        text = re.sub(r'\bNone\b\s*', '', text)
        text = re.sub(r'(?<!\w)\((?!\S)', '', text)
        text = re.sub(r'(?<!\S)\)(?!\w)', '', text)
        return text

    def _apply_abbreviations(self, text: str) -> str:
        """Apply abbreviations from label_mappings.json.

        Labels are pre-sorted globally longest-first so multi-word keys
        ('OPENING STATEMENT', 'machine learning') always match before
        their shorter sub-strings ('opening', 'learning').

        Pass 1 — HEADER keys (contain at least one uppercase letter):
            Exact case match (no IGNORECASE) — prevents 'OPENING STATEMENT'→'Opening'
            from being re-matched by the body key 'opening'.

        Pass 2 — BODY keys (all-lowercase):
            Word-boundary + IGNORECASE.

        Pass 3 — Regex patterns with capture groups.
        """
        # Global sort longest-first — split AFTER sorting to preserve order within each pass
        labels      = self._debate_labels()
        header_keys = [(s, d) for s, d in labels if s != s.lower()]
        body_keys   = [(s, d) for s, d in labels if s == s.lower()]

        # Pass 1: headers — exact case (no IGNORECASE)
        for src, dst in header_keys:
            if ' ' in src or '-' in src:
                text = re.sub(re.escape(src), dst, text)
            else:
                text = re.sub(r'\b' + re.escape(src) + r'\b', dst, text)

        # Pass 2: body — IGNORECASE, word-boundary safe
        for src, dst in body_keys:
            if ' ' in src or '-' in src:
                text = re.sub(re.escape(src), dst, text, flags=re.IGNORECASE)
            else:
                text = re.sub(r'\b' + re.escape(src) + r'\b', dst, text, flags=re.IGNORECASE)

        # Pass 3: regex patterns with capture groups
        for pattern, replacement in self._regex_patterns():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        return text

    def _strip_aux_and_articles(self, text: str) -> str:
        """Remove aux verbs and articles from debate_compression in label_mappings.json."""
        cfg = self._compression()
        for word in cfg.get('aux_strip', []):
            text = re.sub(r'\b' + re.escape(word) + r'\b\s+', '', text, flags=re.IGNORECASE)
        for word in cfg.get('article_strip', []):
            text = re.sub(r'\b' + re.escape(word) + r'\b\s+', '', text, flags=re.IGNORECASE)
        return text

    def _collapse_whitespace(self, text: str) -> str:
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def _hard_cap(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        ratio = self._compression().get('hard_cap_ratio', 0.67)
        cap   = text[:max_chars]
        cut   = max(cap.rfind('.'), cap.rfind('\n'))
        if cut > int(max_chars * ratio):
            return cap[:cut + 1].strip()
        return cap.strip()

    def _smart_trim(self, text: str, max_chars: int) -> str:
        """Iteratively drop trailing sentences from the longest non-header block.
        header_prefixes must be defined in data/label_mappings.json → debate_compression."""
        prefixes = self._compression().get('header_prefixes', [])
        hdr = re.compile(
            r'^(' + '|'.join(re.escape(p) for p in prefixes) + r')',
            re.IGNORECASE
        )
        blocks = re.split(r'(\n{2,})', text)
        pairs  = []
        i = 0
        while i < len(blocks):
            blk = blocks[i]
            sep = blocks[i + 1] if i + 1 < len(blocks) and not blocks[i + 1].strip() else '\n'
            pairs.append([blk, sep])
            i += 2 if (i + 1 < len(blocks) and not blocks[i + 1].strip()) else 1

        def joined(p):
            return ''.join(b + s for b, s in p).strip()

        for _ in range(200):
            if len(joined(pairs)) <= max_chars:
                break
            li, ll = -1, 0
            for idx, (blk, _s) in enumerate(pairs):
                if not hdr.match(blk.strip()) and len(blk) > ll:
                    ll, li = len(blk), idx
            if li == -1:
                break
            nb = re.sub(r'[^.!?\n]*[.!?]["\']?\s*$', '', pairs[li][0], flags=re.DOTALL).strip()
            if nb == pairs[li][0] or not nb:
                pairs.pop(li)
            else:
                pairs[li][0] = nb

        return self._hard_cap(joined(pairs), max_chars)
