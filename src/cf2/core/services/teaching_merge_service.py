"""
teaching_merge_service.py — Merge transcript + screen OCR into teaching narration
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class TeachingMergeService:
    def __init__(
        self,
        agent_name: str = "teaching_merge",
        max_tokens: int = 4000,
        temperature: float = 0.7,
    ):
        self.agent_name  = agent_name
        self.max_tokens  = max_tokens
        self.temperature = temperature

    # ──────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────

    def merge(
        self,
        audio_text: str,
        screen_text: str,
        inputs: Optional[dict] = None,
        output_path: Optional[Path] = None,
        style: str = "educational",
        language: str = "en",
    ) -> str:
        clean_code = self._clean_ocr(screen_text)

        if not clean_code or len(clean_code) < 8:
            merged = audio_text
        else:
            prompt = self._build_prompt(audio_text, clean_code, style, language)
            merged = (
                self._call_llm(prompt, inputs)
                or self._heuristic_merge(audio_text, clean_code)
            )

        if output_path:
            Path(output_path).write_text(merged, encoding="utf-8")

        return merged

    # ──────────────────────────────────────────────────────
    # OCR Cleaning
    # ──────────────────────────────────────────────────────

    def _clean_ocr(self, raw: str) -> str:
        if not raw or raw.startswith("["):
            return ""

        lines = [line.rstrip() for line in raw.splitlines()]

        noise_patterns = [
            r'^C:\\Users\\',
            r'^Desktop\\',
            r'Low_Level_Design.*',
            r'^[Qq]ar\d*\s*=',
            r'^\s*$',
        ]
        filtered = []
        for line in lines:
            if any(re.search(p, line) for p in noise_patterns):
                continue

            # Defense in depth - Remove incomplete OCR fragments
            if (
                line.count("(") != line.count(")")
                or line.count("{") != line.count("}")
                or line.count("[") != line.count("]")
                or line.count('"') % 2 != 0
            ):
                continue

            filtered.append(line)

        # Deduplicate while preserving order
        seen   = set()
        deduped = []
        for line in filtered:
            norm = re.sub(r'\s+', '', line).lower()
            if norm and norm not in seen and len(norm) > 2:
                seen.add(norm)
                deduped.append(line)

        code = "\n".join(deduped)
        code = re.sub(r',(\w)', r', \1', code)

        return code.strip()

    # ──────────────────────────────────────────────────────
    # Prompt Engineering
    # ──────────────────────────────────────────────────────

    def _build_prompt(
        self, audio: str, code: str, style: str, language: str
    ) -> str:
        max_audio = self.max_tokens * 2
        max_code  = self.max_tokens
        audio_safe = audio[:max_audio] + ("..." if len(audio) > max_audio else "")
        code_safe  = code[:max_code]   + ("..." if len(code) > max_code else "")

        return f"""You are an expert programming instructor creating a voiceover script for a coding tutorial video.

GOAL: Enhance the original narration by naturally explaining the code visible on screen.

ORIGINAL AUDIO TRANSCRIPT:
{audio_safe}

CLEANED ON-SCREEN CODE:
{code_safe}

INSTRUCTIONS:
1. Keep the speaker's original flow and tone.
2. When code appears, INSERT a natural teaching explanation:
   - Say "Here we define class Car colon" not just "class Car"
   - Explain __init__: "The init method takes color, make, model, year as parameters"
   - Explain self assignments: "self dot color equals color stores the value"
3. Speak symbols naturally: "colon", "underscore", "dot", "equals"
4. DO NOT read the code verbatim without explanation.
5. DO NOT add new concepts not in the code.
6. Ignore IDE/editor UI artifacts such as: "new *", "1 usage", autocomplete suggestions, editor tooltips, or file tabs.
7. Style: {style} | Language: {language}
8. Keep the enhanced narration under 2x the original transcript length. Do not over-explain.
9. Output ONLY the enhanced narration as continuous spoken text.
   No markdown, no bullet points, no code blocks.

Now produce the enhanced narration:"""

    # ──────────────────────────────────────────────────────
    # LLM Call
    # ──────────────────────────────────────────────────────

    def _call_llm(self, prompt: str, inputs: Optional[dict]) -> Optional[str]:
        """
        Route LLM call through CF2's central gateway with fallback.
        Provides explicit import error logging for missing dependencies.
        """
        try:
            from cf2.core.llm_executor import call_with_fallback
        except ImportError:
            logger.warning("[TeachingMerge] llm_executor not available — using heuristic")
            return None

        try:
            from litellm import completion
        except ImportError:
            logger.warning("[TeachingMerge] litellm not installed — using heuristic")
            return None

        try:
            # Build the call_fn factory required by call_with_fallback
            def call_fn(cfg: dict) -> str:
                response = completion(
                    model=cfg["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=cfg["temperature"],
                    max_tokens=cfg["max_tokens"],
                )
                return response.choices[0].message.content.strip()

            result = call_with_fallback(
                agent_name=self.agent_name,
                inputs=inputs or {},
                call_fn=call_fn,
            )

            return str(result).strip() or None

        except Exception as e:
            logger.warning(f"[TeachingMerge] LLM call failed: {e}")
            return None

    # ──────────────────────────────────────────────────────
    # Heuristic Fallback
    # ──────────────────────────────────────────────────────

    def _heuristic_merge(self, audio: str, code: str) -> str:
        class_match = re.search(r'class\s+(\w+)', code)
        class_name  = class_match.group(1) if class_match else "the class"

        explanation = (
            f"\n\nNow let's look at the code on screen. "
            f"Here we define class {class_name} colon. "
        )

        params_match = re.search(r'def __init__\(self,\s*([^)]+)\)', code)
        if params_match:
            param_list = [p.strip() for p in params_match.group(1).split(',')]

            # Better spoken formatting with Oxford comma for TTS
            if len(param_list) > 1:
                readable = ", ".join(param_list[:-1]) + f", and {param_list[-1]}"
            else:
                readable = param_list[0]

            explanation += (
                f"The init method takes {readable} as parameters. "
                f"Inside, each value is assigned to self dot, "
                f"so each object stores its own copy. "
            )

        # Detect interface/abstract pattern if no __init__ is found
        abstract_methods = re.findall(r'def\s+(\w+)\s*\(self[^)]*\)\s*:', code)
        if abstract_methods and not params_match:
            method_names = ', '.join(abstract_methods[:3])
            explanation += (
                f"This class defines the following methods: {method_names}. "
                f"Each subclass must implement these to define its own behavior. "
            )

        # Detect inheritance
        inherits = re.findall(r'class\s+(\w+)\s*\((\w+)\)', code)
        if inherits:
            for child, parent in inherits[:2]:
                explanation += (
                    f"Class {child} inherits from {parent}, "
                    f"so it gets all of {parent}'s behavior and must implement its own. "
                )

        if re.search(r'^\s*def\s+display', code, re.MULTILINE | re.IGNORECASE):
            explanation += "We also have a display info method to print the details. "

        instances = re.findall(r'(\w+)\s*=\s*\w+\(([^)]+)\)', code)
        if instances:
            explanation += "Then we create objects: "
            for name, args in instances[:2]:
                # Safe keyword replacement that preserves URLs/Dicts
                clean_args = re.sub(
                    r'(\b\w+)\s*:',
                    r'\1 equals ',
                    args
                )
                clean_args = (
                    clean_args.replace('"', "")
                              .replace(",", ", ")
                              .replace("..", ". ")
                )
                explanation += (
                    f"We create object {name} from class {class_name} "
                    f"with {clean_args}. "
                )

        return audio.strip() + explanation


# Backwards compatibility aliases
MergeService        = TeachingMergeService
ContextMergeService = TeachingMergeService
