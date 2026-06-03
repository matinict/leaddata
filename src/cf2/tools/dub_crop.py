"""cf2/tools/dub_crop.py"""
from cf2.core.services.crop_service import CropService
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "crop", force):
        log("⏭️ crop skipped"); return True
    fmt_cfg = config.get("video_formats", {})
    if not fmt_cfg:
        mark_subtask(workspace, "Unit-Dubbing", "crop", "done")
        return True
    source = str(paths["holo"] if paths["holo"].exists() else paths["final"])
    svc = CropService(logger=log)
    svc.process_all(source_video=source, video_formats_cfg=fmt_cfg, output_dir=str(paths["dir"]), topic=workspace.name, channel=config.get("channel", "@PlayOwnAi"))
    mark_subtask(workspace, "Unit-Dubbing", "crop", "done")
    log("✅ crop done")
    return True
