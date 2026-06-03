# src/cf2/core/services/xtts_service.py

import os
from pathlib import Path
from TTS.api import TTS

_model: TTS | None = None

def _get_model(device: str = "cpu") -> TTS:
    global _model
    if _model is None:
        _model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return _model

def synthesize_xtts(text: str, output_path: str, inputs: dict) -> str:
    cfg     = inputs.get("voice_clone_config", {})
    wav     = cfg.get("speaker_wav", "assets/voices/matin.wav")
    lang    = cfg.get("language", "en")
    device  = cfg.get("device", "cpu")
    cache   = cfg.get("use_cache", True)

    # Smart skip (CF2 Rule 32)
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    # Cache check
    if cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, wav, lang)
        if cached and os.path.exists(cached):
            import shutil
            shutil.copy(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    if not Path(wav).exists():
        raise FileNotFoundError(f"Speaker WAV not found: {wav}")

    model = _get_model(device)
    tmp_wav = output_path.replace(".mp3", "_tmp.wav")

    model.tts_to_file(
        text=text,
        speaker_wav=wav,
        language=lang,
        file_path=tmp_wav
    )

    from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
    wav_to_mp3(tmp_wav, output_path)
    Path(tmp_wav).unlink(missing_ok=True)

    if cache:
        set_cached(text, wav, lang, output_path)

    return f"✅ XTTS generated: {output_path}"
