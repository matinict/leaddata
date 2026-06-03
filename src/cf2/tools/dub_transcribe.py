"""cf2/tools/dub_transcribe.py"""
from pathlib import Path
from cf2.core.services.transcript_service import TranscriptService
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "transcribe", force):
        log("⏭️ transcribe skipped"); return True
    svc = TranscriptService(model_size=config.get("whisper_model", "base"))
    text = svc.transcribe(video, paths["script"])
    mark_subtask(workspace, "Unit-Dubbing", "transcribe", "done")
    log(f"✅ transcribe: {len(text)} chars")
    return True
