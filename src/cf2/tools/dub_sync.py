"""cf2/tools/dub_sync.py"""
from cf2.core.services.audio_service import AudioService
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "sync", force):
        log("⏭️ sync skipped"); return True
        
    svc = AudioService()
    
    # 1. Get the target duration from the original video
    target_duration = svc.get_duration(video)
    
    # 2. Stretch/compress the dubbed audio to match the video duration
    svc.apply_atempo(
        audio_path=str(paths["dubbed"]), 
        output_path=str(paths["synced"]), 
        target_duration=target_duration
    )
    
    mark_subtask(workspace, "Unit-Dubbing", "sync", "done")
    log("✅ sync done")
    return True
