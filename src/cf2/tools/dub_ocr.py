"""cf2/tools/dub_ocr.py"""
from cf2.core.services.screen_ocr_service import ScreenOCRService
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "screen_ocr", force):
        log("⏭️ screen_ocr skipped"); return True
    cfg = config.get("screen_ocr", {})
    if not cfg.get("enabled", True):
        paths["screen_ocr"].write_text("[OCR_DISABLED]", encoding="utf-8")
        mark_subtask(workspace, "Unit-Dubbing", "screen_ocr", "done")
        return True
    svc = ScreenOCRService(
        base_fps=cfg.get("fps", 0.5),
        confidence_threshold=cfg.get("confidence_threshold", 0.70),
        max_frames=cfg.get("max_frames", 5),
        lang=cfg.get("lang", "en"),
    )
    text = svc.extract(video_path=video, output_dir=paths["dir"], cleanup_frames=cfg.get("cleanup_frames", True))
    paths["screen_ocr"].write_text(text or "[NO_TEXT]", encoding="utf-8")
    mark_subtask(workspace, "Unit-Dubbing", "screen_ocr", "done")
    log(f"✅ ocr: {len(text)} chars")
    return True
