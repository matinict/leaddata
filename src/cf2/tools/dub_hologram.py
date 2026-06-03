"""cf2/tools/dub_hologram.py"""
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "hologram", force):
        log("⏭️ hologram skipped"); return True
    holo_cfg = config.get("hologram", {})
    if not holo_cfg.get("enabled", False):
        mark_subtask(workspace, "Unit-Dubbing", "hologram", "done")
        return True
    # placeholder - call your existing hologram service
    from pathlib import Path
    import shutil
    if paths["final"].exists():
        shutil.copy2(paths["final"], paths["holo"])
    mark_subtask(workspace, "Unit-Dubbing", "hologram", "done")
    log("✅ hologram done")
    return True
