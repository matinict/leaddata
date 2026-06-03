"""
unit_packaging.py — Packaging Unit Orchestrator (Debate-Aware)
Handles: CC routing & translation, YouTube metadata generation, AI thumbnail generation.
Rules: 19 (Paths), 23 (Config-driven), 24 (Smart Skip), 27 (Profile Merge)
"""
import os
import shutil
from pathlib import Path
from typing import Dict, Any
import traceback

from cf2.meta import mark_subtask
from cf2.tools.publisher_yt_shared import google_translate, LANGUAGES, parse_video_formats, get_animation_formats

try:
    from cf2.tools.packaging_yt_metadata import YTMetadataTool
    from cf2.tools.packaging_yt_thumbnail import YTThumbnailTool
except ImportError as e:
    print(f"⚠️ Packaging tools import failed: {e}")
    YTMetadataTool = None
    YTThumbnailTool = None

def _log(msg: str):
    """Unified logging helper."""
    print(f"[Unit-Packaging] {msg}")

def run(topic: str, workspace: Path, inputs: Dict[str, Any], force: bool = False) -> str:
    """
    Main entry point for Unit-Packaging.

    Args:
        topic: Video topic string
        workspace: Path to topic workspace (output/{slug}/)
        inputs: Merged config dict from data.json + profile overrides
        force: If True, bypass smart skip checks

    Returns:
        Status string: 'done' | 'skipped' | 'disabled' | 'failed'
    """
    # Rule 23: Check master switch
    if not inputs.get("Unit-Packaging", False):
        _log("⏭️ Unit-Packaging disabled — skipping.")
        mark_subtask(workspace, "Unit-Packaging", "packaging", "disabled")
        return "disabled"

    debate_dir = workspace / "debate"
    if not debate_dir.exists():
        _log("⚠️ No debate/ folder found. Packaging skipped.")
        mark_subtask(workspace, "Unit-Packaging", "packaging", "skipped")
        return "skipped"

    # 📦 Config Extraction (Rule 23: No hardcoding)
    video_formats = inputs.get("video_formats", ["Shorts"])
    pkg_config = inputs.get("packaging_config", {})

    # Extract metadata/CC settings
    yt_cc_lang = int(pkg_config.get("yt_cc_lang", 3))
    yt_md_lang = int(pkg_config.get("yt_md_lang", 9))
    gen_meta = pkg_config.get("generate_youtube_metadata", True)
    gen_th = pkg_config.get("generate_thumbnail", True)

    # 🔑 Route thumbnail config (supports nested or top-level in data.json)
    # Rule 27: Deep-merge profile overrides
    thumbnail_config = inputs.get("thumbnail_config", pkg_config.get("thumbnail_config", {}))

    _log(f"📦 Config → MD_lang={yt_md_lang}, CC_lang={yt_cc_lang}, Thumb_methods={thumbnail_config.get('thumbnail_methods', ['placeholder'])}")

    output_dir = str(debate_dir)
    slug = workspace.name
    channel = inputs.get("channel", "channelName")

    # 🔥 Rule 24: Smart Skip Check (before any work)
    yt_base = debate_dir / "YT"
    if yt_base.exists() and not force:
        done = 0
        for fmt in video_formats:
            md_exists = (yt_base / fmt / "MD" / "en.json").exists()
            th_exists = any((yt_base / fmt / "Th").glob("*.jpg")) or any((yt_base / fmt / "Th").glob("*.png"))
            cc_exists = (yt_base / fmt / "CC" / "en.txt").exists()
            if md_exists and th_exists and cc_exists:
                done += 1
        if done >= len(video_formats):
            _log("⏭️ Smart skip — all packaging outputs already exist.")
            mark_subtask(workspace, "Unit-Packaging", "packaging", "skipped")
            return "skipped"

    mark_subtask(workspace, "Unit-Packaging", "packaging", "running")

    try:
        # 1️⃣ CC Routing & Translation
        _log("📝 Routing debate CC & translating...")
        active_cc_langs = LANGUAGES[:min(yt_cc_lang, len(LANGUAGES))]

        for fmt in video_formats:
            debate_cc = debate_dir / f"{slug}_{fmt}.txt"
            if debate_cc.exists():
                cc_dir = debate_dir / "YT" / fmt / "CC"
                cc_dir.mkdir(parents=True, exist_ok=True)

                # Copy English CC
                dest_en = cc_dir / "en.txt"
                if not dest_en.exists() or force:
                    shutil.copy2(debate_cc, dest_en)
                    _log(f"✅ Copied debate CC → YT/{fmt}/CC/en.txt")

                # Translate to target languages
                if dest_en.exists():
                    en_text = dest_en.read_text(encoding="utf-8").strip()
                    if en_text:
                        for lang in active_cc_langs:
                            if lang == "en":
                                continue
                            out = cc_dir / f"{lang}.txt"
                            if out.exists() and not force:
                                continue
                            try:
                                out.write_text(google_translate(en_text, lang), encoding="utf-8")
                                _log(f"  🌐 Translated CC/{lang}.txt")
                            except Exception as e:
                                _log(f"  ⚠️ CC/{lang} failed: {e}")
            else:
                _log(f"⚠️ No debate source found for {fmt}: {debate_cc.name}")

        # 2️⃣ Metadata Generation (Rule 24 enforced inside tool)
        if gen_meta and YTMetadataTool:
            _log("📦 Generating YouTube metadata...")
            result = YTMetadataTool()._run(
                topic=topic,
                filename=slug,
                output_dir=output_dir,
                channel=channel,
                channel_lower=inputs.get("channel_lower", channel.lower()),
                website=inputs.get("website", f"youtube.com/@{channel}"),
                video_formats=video_formats,
                yt_metadata_lang=yt_md_lang
            )
            _log(f"✅ Metadata complete: {result[:100]}...")

        # 3️⃣ Thumbnail Generation (Config-Routed Fallback Chain)
        if gen_th and YTThumbnailTool:
            _log("🖼️ Generating thumbnails...")
            result = YTThumbnailTool()._run(
                topic=topic,
                filename=slug,
                output_dir=output_dir,
                channel=channel,
                video_formats=video_formats,
                thumbnail_config=thumbnail_config  # 🔑 Routes to openai → comfyui → diffusers → placeholder
            )
            _log(f"✅ Thumbnails complete: {result[:100]}...")

        mark_subtask(workspace, "Unit-Packaging", "packaging", "done")
        return "done"

    except Exception as e:
        _log(f"❌ Packaging error: {e}")
        traceback.print_exc()
        mark_subtask(workspace, "Unit-Packaging", "packaging", "failed")
        raise
