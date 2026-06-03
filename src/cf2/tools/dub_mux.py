"""cf2/tools/dub_mux.py"""
from cf2.core.services.ffmpeg_service import FFmpegService
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "merge", force):
        log("⏭️ merge skipped"); return True
    svc = FFmpegService()
    svc.merge_audio_video(video_path=video, audio_path=str(paths["synced"]), output_path=str(paths["final"]))
    mark_subtask(workspace, "Unit-Dubbing", "merge", "done")
    log("✅ merge done")
    return True
