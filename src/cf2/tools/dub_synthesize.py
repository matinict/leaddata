"""cf2/tools/dub_synthesize.py"""
from cf2.core.services.tts_service import TTSService
from cf2.meta import mark_subtask, should_skip_dubbing_stage

def run(video: str, paths: dict, config: dict, workspace, force: bool, log):
    if should_skip_dubbing_stage(workspace, "synthesize", force):
        log("⏭️ synthesize skipped"); return True
        
    script = paths["enhanced_script"] if paths["enhanced_script"].exists() and paths["enhanced_script"].stat().st_size > 100 else paths["script"]
    text = script.read_text(encoding="utf-8", errors="ignore")
    
    svc = TTSService()
    
    engine = config.get("tts_engine", "edge")
    engine_config = config.get("voice_clone_config", {})
    
    svc.generate(
        text=text, 
        output_path=str(paths["dubbed"]), 
        engine=engine, 
        **engine_config
    )
    
    mark_subtask(workspace, "Unit-Dubbing", "synthesize", "done")
    log("✅ synthesize done")
    return True
