"""cf2/tools/dub_merge_context.py"""
from cf2.core.services.teaching_merge_service import TeachingMergeService
from cf2.meta import mark_subtask, should_skip_dubbing_stage
from pathlib import Path
import shutil

 
def run(video, paths, config, workspace, force=False, log=print):
    script = ""
    ocr = ""

    # ── Read transcript if available ─────────────────────
    if paths["script"].exists():
        script = paths["script"].read_text(
            encoding="utf-8",
            errors="ignore",
        ).strip()

    # ── OCR is optional ──────────────────────────────────
    if paths["screen_ocr"].exists():
        ocr = paths["screen_ocr"].read_text(
            encoding="utf-8",
            errors="ignore",
        ).strip()
    else:
        log("ℹ️ screen_ocr.txt missing — continuing without OCR")

    # ── Merge intelligently ──────────────────────────────
    merged_parts = []

    if script:
        merged_parts.append(script)

    if ocr:
        merged_parts.append(ocr)

    merged = "\n\n".join(merged_parts).strip()

    # ── Fallback safety ──────────────────────────────────
    if not merged:
        log("❌ merge_context failed: no transcript or OCR text available")
        return False

    paths["enhanced_script"].write_text(
        merged,
        encoding="utf-8",
    )

    log(f"✅ merge_context: {len(merged)} chars")
    return True
