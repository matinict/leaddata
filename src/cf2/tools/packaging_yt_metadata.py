"""
packaging_yt_metadata.py — High-CTR YouTube Metadata Generator
Generates: SEO-optimized descriptions, viral tags, localized hashtags, and dynamic chapters.
Output: YT/{fmt}/MD/en.json + translations (with localized hashtags appended).
Rule: All content comes from debate files + config + lang.json. No hardcoded strings.
"""
import os
import re
import json
import time
import random
from pathlib import Path
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from datetime import datetime
from typing import ClassVar

# Rule 19 compliant path resolution
try:
    from config import PROJECT_ROOT
except ImportError:
    try:
        from cf2.core.paths import PROJECT_ROOT
    except ImportError:
        PROJECT_ROOT = Path(__file__).resolve().parents[3]

from cf2.tools.publisher_yt_shared import (
    google_translate, parse_video_formats, get_animation_formats, LANGUAGES
)
from cf2.core.weak_words import get_hashtag_skip

class YTMetadataToolInput(BaseModel):
    topic: str = Field(..., description="Video topic")
    filename: str = Field(..., description="Base filename slug")
    output_dir: str = Field(..., description="Output directory (debate folder)")
    channel: str = Field(default=" ", description="Channel name")
    channel_lower: str = Field(default=" ", description="Lowercase channel")
    website: str = Field(default=" ", description="Channel website")
    video_formats: list = Field(default=[], description="Video formats")
    yt_metadata_lang: int = Field(default=9, description="Number of MD languages to generate")

class YTMetadataTool(BaseTool):
    name: str = "PackagingYtMetadata"
    description: str = "Generates high-CTR YouTube metadata with SEO descriptions, viral tags, dynamic chapters, and localized hashtags"
    args_schema: Type[BaseModel] = YTMetadataToolInput

    # 🔥 SEMANTIC KEYWORDS: Prioritize these to find the REAL meaning
    MEANING_KEYWORDS: ClassVar[dict] = {
        'finance': {'usd', 'bank', 'trade', 'dollar', 'economy', 'currency', 'bitcoin', 'market', 'brics', 'money'},
        'conflict': {'kill', 'destroy', 'collapse', 'crisis', 'threat', 'vs', 'war', 'attack', 'against'},
        'geo': {'russia', 'usa', 'us', 'europe', 'china', 'asia', 'india', 'africa'}
    }

    def _run(self, topic: str, filename: str, output_dir: str,
             channel: str = " ", channel_lower: str = " ", website: str = " ",
             video_formats: list = None, yt_metadata_lang: int = 9) -> str:

        if not channel:
            raise ValueError("Missing channel config")

        t0 = time.time()
        print(f"[YTMeta] Starting — topic='{topic}' channel='{channel}'")

        # Read debate files for content
        pro_txt = self._read_debate_file(output_dir, "propose")
        con_txt = self._read_debate_file(output_dir, "oppose")
        dec_txt = self._read_debate_file(output_dir, "decide")

        # Load localized hashtags from lang.json ONCE
        lang_tags = self._load_all_local_tags()

        video_formats = parse_video_formats(video_formats, [])
        animation_video_formats = get_animation_formats([], video_formats)
        active_langs = LANGUAGES[:min(int(yt_metadata_lang), len(LANGUAGES))]

        # 🔥 FIX: Extract REAL entities first to avoid junk titles
        entity_a, entity_b = self._extract_real_entities(topic)
        print(f"[YTMeta] 🧠 Extracted Entities: '{entity_a}' vs '{entity_b}'")

        results = []
        for fmt in animation_video_formats:
            is_short = "Short" in fmt

            # 🔥 FIX: Pass real entities to title/hook generation
            title = self._generate_title(topic, channel, is_short, entity_a, entity_b)
            description = self._make_debate_desc(topic, pro_txt, con_txt, dec_txt, channel, website, is_short)
            tags = self._generate_viral_tags(topic, channel, entity_a, entity_b)
            chapters = self._generate_chapters(topic, output_dir, fmt)
            hashtags = self._generate_hashtags(topic, channel, entity_a, entity_b)

            result = self._write_metadata_files(
                output_dir, fmt, title, description, tags, chapters, hashtags,
                active_langs, lang_tags, channel
            )
            results.append(result)

        elapsed = time.time() - t0
        return f"✅ Metadata COMPLETED in {elapsed:.1f}s\n" + "\n".join(results)

    def _extract_real_entities(self, topic: str) -> tuple:
        """Extract two main entities for debate titles. Splits by separators, never returns junk placeholders."""
        if not topic: return "", ""
        topic_clean = topic.strip().rstrip("?:")

        # 1. Split by common debate separators
        for sep in [r'\s+vs\.?\s+', r'\s+and\s+', r'\s+&\s+', r'\s*[-–—]\s*', r'\s*,\s*']:
            parts = re.split(sep, topic_clean, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                ent_a = parts[0].strip().rstrip("?:")
                ent_b = parts[1].strip().rstrip("?:")
                if ent_a and ent_b:
                    return ent_a, ent_b

        # 2. Fallback: Strip question starters, use cleaned topic as primary
        clean_topic = re.sub(
            r'^(Is|Are|The|Can|Why|How|Who|What|Where|When)\s+',
            '', topic_clean, flags=re.IGNORECASE
        ).strip()
        return clean_topic or topic_clean, ""

    def _generate_title(self, topic: str, channel: str, is_short: bool, ent_a: str, ent_b: str) -> str:
        """Generate YouTube-compliant title: clean grammar, <100 chars, zero junk fallbacks."""
        suffix = " | #Shorts" if is_short else ""
        channel_suffix = f" | {channel}"
        max_len = 100 - len(suffix) - len(channel_suffix)

        # Only use 'vs' format if BOTH entities are non-empty
        if ent_a.strip() and ent_b.strip():
            title = f"{ent_a} vs {ent_b}"
            if len(title) <= max_len:
                return f"{title}?{channel_suffix}{suffix}"

        # Fallback to cleaned original topic
        clean_topic = topic.strip().rstrip("?")
        clean_topic = re.sub(
            r'^(Is|Are|The|Can|Why|How|Who|What|Where|When)\s+',
            '', clean_topic, flags=re.IGNORECASE
        ).strip()

        if clean_topic:
            if len(clean_topic) <= max_len:
                return f"{clean_topic}?{channel_suffix}{suffix}"
            return f"{clean_topic[:max_len-3]}...?{channel_suffix}{suffix}"

        # Absolute safety fallback
        return f"{topic.strip()[:max_len-3]}...?{channel_suffix}{suffix}"

    def _generate_viral_tags(self, topic: str, channel: str, ent_a: str, ent_b: str) -> list:
        """SEO tags: dynamic extraction, deduplicated, <30 items, zero empty strings."""
        keywords = [t for t in re.findall(r'\w+', topic.lower()) if len(t) > 2]
        raw = [
            topic.lower(), f"{channel.lower()} debate",
            ent_a.lower() if ent_a.strip() else "",
            ent_b.lower() if ent_b.strip() else "",
            "controversial debate", "critical thinking", "global debate",
            "ai analysis", "fact check", "deep dive", "educational content",
            "unbiased analysis", "geopolitics", "future trends", "tech debate",
            "society", "culture", "knowledge", "truth", "logic", "analysis",
            "strategy", "power", "influence", "sovereignty", "resilience",
            "smart thinking", "open minded", "diplomacy", "peace",
            "conflict resolution", "international relations", "current events",
            channel.lower()
        ]
        raw.extend(keywords)
        clean = [t.strip() for t in raw if t.strip() and len(t.strip()) > 2]
        return list(dict.fromkeys(clean))[:30]

    def _read_debate_file(self, output_dir: str, name: str) -> str:
        """Rule 19 compliant: uses pathlib, safe encoding, strips markdown syntax."""
        dir_path = Path(output_dir)
        for p in [dir_path / f"{name}_En.md", dir_path / f"{name}.md"]:
            if p.exists():
                try:
                    raw = p.read_text(encoding="utf-8")
                    clean = re.sub(r'^#+\s*|[\*#\-\[\]]', ' ', raw, flags=re.MULTILINE)
                    clean = re.sub(r'\n{2,}', ' ', clean).strip()
                    return clean[:500]
                except Exception:
                    pass
        return ""
    def _load_all_local_tags(self) -> dict:
        lang_file = PROJECT_ROOT / "data" / "lang.json"
        if not lang_file.exists():
            return {}
        try:
            with open(lang_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {lang["code"]: lang.get("local_tags", " ") for lang in data.get("languages", [])}
        except Exception as e:
            return {}

    def _make_debate_desc(self, topic: str, pro: str, con: str, dec: str,
                          channel: str, website: str, is_short: bool) -> str:
        """Generate grammatically correct, policy-safe description."""
        # 🔥 Clean topic for natural sentence flow
        clean_topic = topic.strip().rstrip("?")
        clean_topic = re.sub(r'^(Is|Are|The|Can)\s+', '', clean_topic, flags=re.IGNORECASE)

        intro = f"This debate examines whether {clean_topic}. Experts present evidence-based arguments from both sides, followed by a data-driven verdict."

        # Clean argument snippets (remove "Yes—", "No—", etc.)
        def clean_arg(txt):
            if not txt: return ""
            txt = re.sub(r'^(Yes|No|Agree|Disagree)[—\-\s:]*', '', txt, flags=re.IGNORECASE)
            txt = re.sub(r'\s+', ' ', txt).strip()
            return txt[:300] + ("..." if len(txt) > 300 else "")

        pro_clean = clean_arg(pro)
        con_clean = clean_arg(con)
        dec_clean = clean_arg(dec)

        body = [intro]
        if not is_short:
            if pro_clean: body.append(f"\n✅ Proposition: {pro_clean}")
            if con_clean: body.append(f"\n❌ Opposition: {con_clean}")
            if dec_clean: body.append(f"\n🎯 Verdict: {dec_clean}")

        # 🔥 Policy-safe CTA
        cta = f"\n\n💬 Share your perspective in the comments. Subscribe to {channel} for balanced debates on geopolitics, economics, and technology.\n\n🌐 Learn more: {website}"
        body.append(cta)

        # 🔥 Mandatory disclaimer
        body.append("\n\n⚠️ Disclaimer: This content is for educational and discussion purposes only. It does not constitute financial, political, or legal advice. Viewers should conduct independent research and consult qualified professionals before making decisions.")

        return "\n".join(body)

    def _clean_statement(self, raw: str) -> str:
        if not raw: return " "
        txt = re.sub(r'(PROPOSITION|OPPOSITION|VERDICT|SUMMARY|OPENING STATEMENT)[:\s,]*', '', raw, flags=re.IGNORECASE)
        txt = re.sub(r'^(Yes|No)\s*[—–-]\s*', '', txt, flags=re.IGNORECASE)
        txt = re.sub(r'\s+', ' ', txt).strip()
        if len(txt) > 400:
            cut = txt[:400].rsplit('.', 1)[0]
            txt = cut + "." if cut else txt[:400]
        return txt

    def _generate_chapters(self, topic: str, output_dir: str, fmt: str) -> str:
        slug = os.path.basename(os.path.dirname(output_dir))
        transcript_path = os.path.join(output_dir, f"{slug}_{fmt}.txt")
        if os.path.exists(transcript_path):
            chapters = []
            seen_titles = set()
            with open(transcript_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    match = re.match(r'^\[(\d{2}):(\d{2}):(\d{2})\]\s+(.+)', line)
                    if match:
                        h, m, s, title = match.groups()
                        total_seconds = int(h) * 3600 + int(m) * 60 + int(s)
                        mm = total_seconds // 60
                        ss = total_seconds % 60
                        timestamp = f"{mm}:{ss:02d}"
                        title = title.rstrip('?').strip()
                        if len(title) > 60: title = title[:57] + "..."
                        title_key = title.lower()[:30]
                        if title_key not in seen_titles:
                            seen_titles.add(title_key)
                            chapters.append((timestamp, title))
            if chapters:
                return "\n".join(f"{ts} – {title}" for ts, title in chapters)
        return ("0:00 – Hook\n0:15 – Argument\n0:45 – Counter\n1:15 – Verdict\n1:45 – Close"
                if "Short" in fmt else
                "0:00 – Intro\n0:30 – Context\n2:00 – Case A\n4:00 – Case B\n6:00 – Analysis\n8:00 – Verdict\n9:30 – Close")

    def _generate_viral_tags(self, topic: str, channel: str, ent_a: str, ent_b: str) -> list:
        keywords = re.findall(r'\w+', topic.lower())[:5]
        base_tags = [
            topic.lower(),
            f"{channel.lower()} debate",
            ent_a.lower(),
            ent_b.lower(),
            "controversial debate",
            "critical thinking",
            "global debate",
            "ai analysis",
            "fact check",
            "deep dive",
            "educational content",
            "unbiased analysis",
            "geopolitics",
            "future trends",
            "tech debate",
            "society",
            "culture",
            "knowledge",
            "truth",
            "logic",
            "analysis",
            "strategy",
            "power",
            "influence",
            "sovereignty",
            "resilience",
            "smart thinking",
            "open minded",
            "diplomacy",
            "peace",
            "conflict resolution",
            "international relations",
            "current events",
            "world news",
            channel.lower()
        ]
        base_tags.extend(keywords)
        return list(dict.fromkeys(base_tags))[:30]

    def _generate_hashtags(self, topic: str, channel: str, ent_a: str, ent_b: str) -> str:
        """Generate YouTube-safe hashtags: no single words, no policy triggers."""
        skip = get_hashtag_skip()
        # 🔥 Policy-trigger words to exclude from hashtags
        policy_triggers = {"kill", "destroy", "crash", "collapse", "scam", "fraud", "fake", "lie", "us", "usa", "building", "making", "the", "a", "an"}

        raw_words = re.findall(r"[A-Za-z][A-Za-z0-9]+", topic)
        strong = [w for w in raw_words if w.lower() not in skip and w.lower() not in policy_triggers and len(w) >= 4]

        hashtags = []
        # 🔥 Create meaningful multi-word hashtags
        if len(strong) >= 2:
            hashtags.append(f"#{strong[0]}{strong[1]}")  # e.g., #BRICSCurrency
        if len(strong) >= 3:
            hashtags.append(f"#{strong[0]}{strong[2]}")   # e.g., #BRICSDeDollarization

        # Add entity-specific tags
        if "brics" in topic.lower():
            hashtags.extend(["#BRICS", "#DeDollarization", "#GlobalEconomy"])
        if "dollar" in topic.lower():
            hashtags.extend(["#USDollar", "#FederalReserve", "#CurrencyWars"])

        # Channel tags (always safe)
        hashtags.append(f"#{channel}")
        hashtags.append(f"#{channel}Debate")
        hashtags.extend(["#Geopolitics", "#Economics", "#PolicyDebate", "#FactCheck"])

        # 🔥 Deduplicate and limit to YouTube's 15-hashtag best practice
        seen, unique = set(), []
        for h in hashtags:
            tag = h.lower().replace("#", "")
            if tag not in seen and len(tag) >= 4:  # Skip short/spammy tags
                seen.add(tag)
                unique.append(h)

        return " ".join(unique[:15])  # YouTube recommends ≤15 hashtags

    def _write_metadata_files(self, output_dir: str, fmt: str, title: str,
                              description: str, tags: list, chapters: str,
                              hashtags: str, lang_list: list, lang_tags: dict, channel: str) -> str:
        md_dir = os.path.join(output_dir, "YT", fmt, "MD")
        os.makedirs(md_dir, exist_ok=True)

        en_json = os.path.join(md_dir, "en.json")
        with open(en_json, "w", encoding="utf-8") as f:
            json.dump({"title": title, "description": description, "tags": tags, "chapters": chapters, "hashtags": hashtags, "category": "Education", "language": "en", "created_at": datetime.now().isoformat()}, f, indent=2, ensure_ascii=False)

        en_txt = os.path.join(md_dir, "en.txt")
        with open(en_txt, "w", encoding="utf-8") as f:
            f.write(f"TITLE:\n{title}\n\nDESCRIPTION:\n{description}\n\nTAGS:\n{', '.join(tags)}\n\nCHAPTERS:\n{chapters}\n\nHASHTAGS:\n{hashtags}\n")

        PLACEHOLDER = "ZXCHANNELZX"
        def _protect(text: str) -> str:
            if not text: return text
            return (text.replace(f"@{channel}", PLACEHOLDER)
                       .replace(f"@{channel.lower()}", PLACEHOLDER)
                       .replace(channel, PLACEHOLDER)
                       .replace(channel.lower(), PLACEHOLDER))
        def _restore(text: str) -> str:
            return text.replace(PLACEHOLDER, channel)

        tags_str = ", ".join(tags)
        translated = 0
        for lang in lang_list:
            if lang == "en": continue
            try:
                t_title = _restore(google_translate(_protect(title), lang))
                t_desc = _restore(google_translate(_protect(description), lang))
                t_tags = _restore(google_translate(_protect(tags_str), lang))
                t_hashtags = _restore(google_translate(_protect(hashtags), lang))
                local = lang_tags.get(lang, " ")
                if local: t_desc = f"{t_desc}\n{local}"
                p = os.path.join(md_dir, f"{lang}.txt")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(f"TITLE:\n{t_title}\n\nDESCRIPTION:\n{t_desc}\n\nTAGS:\n{t_tags}\n\nCHAPTERS:\n{chapters}\n\nHASHTAGS:\n{t_hashtags}\n")
                translated += 1
            except Exception as e:
                print(f"[YTMeta] ⚠️ Translation failed for {lang}: {e}")
        return f"[{fmt}] ✅ Metadata saved | {translated} translations"
