"""
yt_narration_tool.py — CC narration text generation + CC translation.
Generates: output/{dir}/cc_en.txt and YT/{style}/{fmt}/CC/*.txt
Rule: Channel and website from config only. No hardcoded strings.
"""
import os
import glob
import time
from crewai.tools import BaseTool
from typing import Type
from pydantic import BaseModel, Field
from .publisher_yt_shared import LANGUAGES, LANG_NAMES, google_translate, parse_video_formats, get_animation_formats

class YTNarrationToolInput(BaseModel):
    topic: str = Field(..., description="Video topic")
    filename: str = Field(..., description="Base filename slug")
    output_dir: str = Field(..., description="Output directory")
    start_year: int = Field(default=2015)
    end_year: int = Field(default=2026)
    channel: str = Field(..., description="Channel name from config")
    video_formats: list = Field(default=[])
    video_style: list = Field(default=[])
    yt_cc_lang: int = Field(default=3)
    animation_video_formats: list = Field(default=[])
    yt_source_video_id: str = Field(default="")

class YTNarrationTool(BaseTool):
    name: str = "PackagingYtNarration"
    description: str = "Generates CC narration and translations. Config-driven identity."
    args_schema: Type[BaseModel] = YTNarrationToolInput

    def _run(self, topic: str, filename: str, output_dir: str,
             start_year: int = 2015, end_year: int = 2026,
             channel: str = None, video_formats: list = None, video_style: list = None,
             yt_cc_lang: int = 3, animation_video_formats: list = None, yt_source_video_id: str = "") -> str:

        if not channel:
            raise ValueError("Missing 'channel' config. Narration requires channel identity.")

        print(f"[YTNarration] Starting — topic='{topic}' channel='{channel}'")
        t0 = time.time()
        video_formats = parse_video_formats(video_formats, video_style)
        animation_video_formats = get_animation_formats(animation_video_formats, video_formats)
        active_langs = LANGUAGES[:min(int(yt_cc_lang), len(LANGUAGES))]

        os.makedirs(output_dir, exist_ok=True)

        # Generate narration text dynamically
        narration = f"Welcome to @{channel}. Today we explore: {topic}.\n\n"
        narration += f"This debate analyzes both sides using verified data and critical thinking.\n\n"
        narration += f"Subscribe to @{channel} for more educational analysis.\nWebsite: youtube.com/@{channel}"

        cc_path = os.path.join(output_dir, "cc_en.txt")
        with open(cc_path, "w", encoding="utf-8") as f:
            f.write(narration)
        print(f"[YTNarration] Saved: cc_en.txt")
 
        # Translate CC — protect channel brand name
        PLACEHOLDER = "ZXCHANNELZX"

        def _protect(text: str) -> str:
            return (text
                .replace(f"@{channel}", PLACEHOLDER)
                .replace(f"@{channel.lower()}", PLACEHOLDER)
                .replace(channel, PLACEHOLDER)
                .replace(channel.lower(), PLACEHOLDER))

        translated = 0
        for lang in active_langs:
            if lang == "en": continue
            out = os.path.join(output_dir, f"cc_{lang}.txt")
            if not os.path.exists(out):
                try:
                    trans = google_translate(_protect(narration), lang)
                    trans = trans.replace(PLACEHOLDER, channel)
                    with open(out, "w", encoding="utf-8") as f: f.write(trans)
                    translated += 1
                except: pass
