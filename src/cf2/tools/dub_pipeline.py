"""
cf2/tools/dub_pipeline.py — mirrors classroom_pipeline.py
"""
from typing import List, Dict, Any

def build(source_lang: str, target_lang: str, has_ocr: bool, has_translate: bool, tts_engine: str, clip_config: dict) -> List[Dict[str, Any]]:
    pipe = []
    pipe.append({"type": "stage", "key": "transcribe", "role": "stt"})
    if has_ocr:
        pipe.append({"type": "stage", "key": "screen_ocr", "role": "vision"})
    pipe.append({"type": "stage", "key": "merge_context", "role": "prep"})
    if has_translate and source_lang != target_lang:
        pipe.append({"type": "stage", "key": "translate", "role": "llm", "from": source_lang, "to": target_lang})
    pipe.append({"type": "stage", "key": "synthesize", "role": "tts", "engine": tts_engine})
    pipe.append({"type": "stage", "key": "sync", "role": "align"})
    pipe.append({"type": "stage", "key": "merge", "role": "mux"})
    pipe.append({"type": "stage", "key": "hologram", "role": "fx"})
    pipe.append({"type": "stage", "key": "crop", "role": "format"})
    return pipe
