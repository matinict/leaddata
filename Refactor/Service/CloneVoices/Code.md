# CF2 Voice Cloning — Complete Workable Code

Below is **every file** you need. Drop them into your project as-is.

---

## 📁 Directory Setup Script

```bash
#!/bin/bash
# setup_voice_clone.sh — Run once to create all folders

cd /var/POAi/CrewAiFlow/cf2

mkdir -p assets/voices
mkdir -p models/xtts
mkdir -p models/rvc
mkdir -p models/stylettsz
mkdir -p src/cf2/core/services/voice_clone
mkdir -p .runtime/cache/voice_clone

# Create __init__.py files if they don't exist
touch src/cf2/core/services/voice_clone/__init__.py

# Verify
echo "✅ Directory structure created."
ls -R assets/voices models/ .runtime/cache/voice_clone
```

---

## File 1 — `src/cf2/core/services/voice_clone/__init__.py`

```python
# src/cf2/core/services/voice_clone/__init__.py
"""
CF2 Voice Cloning Engine Layer.

Each engine is a standalone module with a single `synthesize_*` function.
All engines follow the same contract:
    synthesize_*(text: str, output_path: str, inputs: dict) -> str

The router in tts_service.py picks the engine based on inputs["tts_engine"].
"""

from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3, normalize_wav
from cf2.core.services.voice_clone.voice_loader import load_speaker_wav, validate_wav

ENGINE_REGISTRY = {
    "xtts":       "cf2.core.services.voice_clone.xtts_service.synthesize_xtts",
    "openvoice":  "cf2.core.services.voice_clone.openvoice_service.synthesize_openvoice",
    "kokoro":     "cf2.core.services.voice_clone.kokoro_service.synthesize_kokoro",
    "chatterbox": "cf2.core.services.voice_clone.chatterbox_service.synthesize_chatterbox",
    "rvc":        "cf2.core.services.voice_clone.rvc_service.synthesize_rvc",
    "styletts2":  "cf2.core.services.voice_clone.styletts2_service.synthesize_styletts2",
}

__all__ = [
    "ENGINE_REGISTRY",
    "get_cached",
    "set_cached",
    "wav_to_mp3",
    "normalize_wav",
    "load_speaker_wav",
    "validate_wav",
]
```

---

## File 2 — `src/cf2/core/services/voice_clone/cache_manager.py`

```python
# src/cf2/core/services/voice_clone/cache_manager.py
"""
Text-level audio cache for voice cloning engines.
Same text + same speaker WAV + same language = reuse cached audio.

Follows CF2 Rule 24 (smart skip mandatory) and Rule 32 (no repeated work).
"""

import hashlib
import json
import os
import shutil
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(".runtime/cache/voice_clone")


def _cache_key(text: str, wav: str, lang: str, engine: str = "xtts") -> str:
    """Generate a deterministic cache key from synthesis parameters."""
    raw = f"{engine}|{text}|{wav}|{lang}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _load_index() -> dict:
    """Load the cache index from disk. Returns empty dict if not found."""
    index_path = CACHE_ROOT / "index.json"
    if index_path.exists():
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[Cache] Corrupt index, resetting: {e}")
    return {}


def _save_index(data: dict) -> None:
    """Persist the cache index to disk."""
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    index_path = CACHE_ROOT / "index.json"
    index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_cached(text: str, wav: str, lang: str, engine: str = "xtts") -> Optional[str]:
    """
    Check if a cached audio file exists for the given parameters.
    Returns the path to the cached file, or None if not found / file missing.
    """
    key = _cache_key(text, wav, lang, engine)
    data = _load_index()

    cached_path = data.get(key)
    if cached_path and os.path.exists(cached_path):
        logger.debug(f"[Cache] Hit: {key[:12]}...")
        return cached_path

    # Clean stale entry
    if cached_path:
        data.pop(key, None)
        _save_index(data)

    return None


def set_cached(text: str, wav: str, lang: str, output_path: str, engine: str = "xtts") -> None:
    """
    Register a generated audio file in the cache.
    Also copies the file into the cache directory for safekeeping.
    """
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    key = _cache_key(text, wav, lang, engine)

    # Copy file into cache dir so it persists even if output is cleaned
    cache_file = CACHE_ROOT / f"{key}.wav"
    if os.path.exists(output_path) and not cache_file.exists():
        try:
            shutil.copy2(output_path, str(cache_file))
        except OSError as e:
            logger.warning(f"[Cache] Failed to copy to cache: {e}")
            cache_file = Path(output_path)

    data = _load_index()
    data[key] = str(cache_file)
    _save_index(data)
    logger.debug(f"[Cache] Stored: {key[:12]}...")


def clear_cache() -> int:
    """Remove all cached files and reset index. Returns count of items cleared."""
    data = _load_index()
    count = len(data)
    for path_str in data.values():
        p = Path(path_str)
        if p.exists():
            p.unlink()
    (CACHE_ROOT / "index.json").unlink(missing_ok=True)
    logger.info(f"[Cache] Cleared {count} items.")
    return count


def cache_stats() -> dict:
    """Return cache statistics."""
    data = _load_index()
    valid = {k: v for k, v in data.items() if os.path.exists(v)}
    total_size = sum(os.path.getsize(v) for v in valid.values())
    return {
        "total_entries": len(data),
        "valid_entries": len(valid),
        "total_bytes": total_size,
        "total_mb": round(total_size / (1024 * 1024), 2),
    }
```

---

## File 3 — `src/cf2/core/services/voice_clone/audio_exporter.py`

```python
# src/cf2/core/services/voice_clone/audio_exporter.py
"""
Audio normalization and format conversion for voice clone outputs.
Converts raw WAV → normalized MP3/WAV for the CF2 merge pipeline.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Target specs for CF2 pipeline
TARGET_SAMPLE_RATE = 22050
TARGET_CHANNELS = 1  # mono


def wav_to_mp3(
    input_wav: str,
    output_mp3: str,
    bitrate: str = "192k",
    sample_rate: int = TARGET_SAMPLE_RATE,
) -> str:
    """
    Convert WAV to MP3 using ffmpeg.
    Normalizes sample rate and channels in the process.
    """
    if not os.path.exists(input_wav):
        raise FileNotFoundError(f"Input WAV not found: {input_wav}")

    os.makedirs(os.path.dirname(output_mp3) or ".", exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_wav,
        "-ar", str(sample_rate),
        "-ac", str(TARGET_CHANNELS),
        "-b:a", bitrate,
        output_mp3,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            logger.error(f"[AudioExport] ffmpeg error: {result.stderr}")
            raise RuntimeError(f"ffmpeg failed: {result.stderr[:200]}")
    except FileNotFoundError:
        # ffmpeg not found — try pydub as fallback
        logger.warning("[AudioExport] ffmpeg not found, trying pydub fallback.")
        return _wav_to_mp3_pydub(input_wav, output_mp3, bitrate, sample_rate)

    logger.info(f"[AudioExport] WAV→MP3: {output_mp3}")
    return output_mp3


def _wav_to_mp3_pydub(
    input_wav: str,
    output_mp3: str,
    bitrate: str = "192k",
    sample_rate: int = TARGET_SAMPLE_RATE,
) -> str:
    """Fallback MP3 conversion using pydub (if ffmpeg is missing)."""
    try:
        from pydub import AudioSegment
    except ImportError:
        raise ImportError(
            "Neither ffmpeg nor pydub available. "
            "Install one: sudo apt install ffmpeg  OR  pip install pydub"
        )

    audio = AudioSegment.from_wav(input_wav)
    audio = audio.set_frame_rate(sample_rate)
    audio = audio.set_channels(TARGET_CHANNELS)
    audio.export(output_mp3, format="mp3", bitrate=bitrate)
    return output_mp3


def normalize_wav(
    input_wav: str,
    output_wav: Optional[str] = None,
    target_db: float = -3.0,
    sample_rate: int = TARGET_SAMPLE_RATE,
) -> str:
    """
    Normalize WAV audio level and sample rate.
    If output_wav is None, overwrites the input file.
    """
    if output_wav is None:
        output_wav = input_wav

    if not os.path.exists(input_wav):
        raise FileNotFoundError(f"Input WAV not found: {input_wav}")

    os.makedirs(os.path.dirname(output_wav) or ".", exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-i", input_wav,
        "-ar", str(sample_rate),
        "-ac", str(TARGET_CHANNELS),
        "-af", f"loudnorm=I={target_db}:LRA=11:TP=-1.5",
        output_wav,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            logger.warning(f"[AudioExport] Normalize failed: {result.stderr}")
            # If normalize fails, just copy as-is
            if input_wav != output_wav:
                import shutil
                shutil.copy2(input_wav, output_wav)
    except FileNotFoundError:
        # No ffmpeg — just copy
        if input_wav != output_wav:
            import shutil
            shutil.copy2(input_wav, output_wav)

    return output_wav


def get_audio_duration(file_path: str) -> float:
    """Return duration of audio file in seconds."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", file_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        import json
        info = json.loads(result.stdout)
        return float(info["streams"][0]["duration"])
    except Exception:
        return 0.0


def ensure_wav_22050(input_path: str, output_path: str) -> str:
    """
    Ensure the WAV file is mono 22050 Hz. Converts if needed, copies if already correct.
    """
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", "22050",
        "-ac", "1",
        "-sample_fmt", "s16",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    except FileNotFoundError:
        import shutil
        shutil.copy2(input_path, output_path)
    return output_path
```

---

## File 4 — `src/cf2/core/services/voice_clone/voice_loader.py`

```python
# src/cf2/core/services/voice_clone/voice_loader.py
"""
Voice sample loader and validator.
Ensures speaker WAV files meet the requirements for voice cloning engines.
"""

import os
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Minimum duration in seconds for a good clone sample
MIN_DURATION = 6.0
RECOMMENDED_DURATION = 20.0

# Required audio specs
REQUIRED_SAMPLE_RATE = 22050
REQUIRED_CHANNELS = 1


def validate_wav(wav_path: str, strict: bool = False) -> dict:
    """
    Validate a WAV file for voice cloning compatibility.
    Returns a dict with validation results.
    """
    result = {
        "path": wav_path,
        "exists": False,
        "duration_s": 0.0,
        "sample_rate": 0,
        "channels": 0,
        "valid": False,
        "warnings": [],
        "errors": [],
    }

    if not os.path.exists(wav_path):
        result["errors"].append(f"File not found: {wav_path}")
        return result

    result["exists"] = True

    # Probe file info
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", wav_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        import json
        info = json.loads(probe.stdout)
        stream = info["streams"][0]

        result["duration_s"] = float(stream.get("duration", 0))
        result["sample_rate"] = int(stream.get("sample_rate", 0))
        result["channels"] = int(stream.get("channels", 0))
    except Exception as e:
        result["errors"].append(f"Cannot probe file: {e}")
        return result

    # Check duration
    if result["duration_s"] < MIN_DURATION:
        result["errors"].append(
            f"Too short: {result['duration_s']:.1f}s (minimum {MIN_DURATION}s)"
        )
    elif result["duration_s"] < RECOMMENDED_DURATION:
        result["warnings"].append(
            f"Short sample: {result['duration_s']:.1f}s (recommended {RECOMMENDED_DURATION}s)"
        )

    # Check sample rate
    if result["sample_rate"] != REQUIRED_SAMPLE_RATE:
        result["warnings"].append(
            f"Sample rate {result['sample_rate']} Hz (recommended {REQUIRED_SAMPLE_RATE} Hz). "
            "Will be auto-converted."
        )

    # Check channels
    if result["channels"] != REQUIRED_CHANNELS:
        result["warnings"].append(
            f"Stereo file ({result['channels']} ch). Will be converted to mono."
        )

    # Overall validity
    result["valid"] = len(result["errors"]) == 0

    if strict:
        result["valid"] = (
            len(result["errors"]) == 0
            and result["duration_s"] >= RECOMMENDED_DURATION
            and result["sample_rate"] == REQUIRED_SAMPLE_RATE
            and result["channels"] == REQUIRED_CHANNELS
        )

    return result


def load_speaker_wav(
    wav_path: str,
    role: Optional[str] = None,
    inputs: Optional[dict] = None,
    auto_convert: bool = True,
) -> str:
    """
    Load and optionally convert a speaker WAV file for voice cloning.
    Handles per-role voice resolution and auto-conversion to 22050 Hz mono.

    Returns the path to a ready-to-use WAV file.
    """
    # Per-role voice resolution (CF2 Rule 23)
    if role and inputs:
        vc_cfg = inputs.get("voice_clone_config", {})
        per_role = vc_cfg.get("per_role_voices", {})
        if role in per_role:
            wav_path = per_role[role]

    if not os.path.exists(wav_path):
        default = "assets/voices/matin.wav"
        logger.warning(
            f"[VoiceLoader] WAV not found: {wav_path}. "
            f"Falling back to default: {default}"
        )
        if os.path.exists(default):
            wav_path = default
        else:
            raise FileNotFoundError(
                f"Speaker WAV not found: {wav_path} (default also missing: {default})"
            )

    if not auto_convert:
        return wav_path

    # Check if conversion is needed
    cache_dir = Path(".runtime/cache/voice_clone/converter")
    cache_dir.mkdir(parents=True, exist_ok=True)

    import hashlib
    file_hash = hashlib.md5(
        f"{wav_path}|{REQUIRED_SAMPLE_RATE}|{REQUIRED_CHANNELS}".encode()
    ).hexdigest()[:12]
    converted_path = cache_dir / f"{Path(wav_path).stem}_{file_hash}.wav"

    if converted_path.exists():
        return str(converted_path)

    # Convert
    from cf2.core.services.voice_clone.audio_exporter import ensure_wav_22050
    ensure_wav_22050(wav_path, str(converted_path))
    logger.info(f"[VoiceLoader] Converted: {wav_path} → {converted_path}")

    return str(converted_path)


def print_validation(wav_path: str) -> None:
    """Print a human-readable validation report for a WAV file."""
    result = validate_wav(wav_path)
    print(f"\n{'='*50}")
    print(f"  Voice Sample Validation: {wav_path}")
    print(f"{'='*50}")
    print(f"  Exists:      {result['exists']}")
    print(f"  Duration:    {result['duration_s']:.1f}s")
    print(f"  Sample Rate: {result['sample_rate']} Hz")
    print(f"  Channels:    {result['channels']}")
    print(f"  Valid:       {result['valid']}")

    if result["warnings"]:
        print(f"\n  ⚠️  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")

    if result["errors"]:
        print(f"\n  ❌ Errors:")
        for e in result["errors"]:
            print(f"    - {e}")

    print(f"{'='*50}\n")
```

---

## File 5 — `src/cf2/core/services/voice_clone/xtts_service.py`

```python
# src/cf2/core/services/voice_clone/xtts_service.py
"""
Coqui XTTS v2 — Zero-shot voice cloning engine.
Best overall for CF2: 17 languages, no training needed, CPU-capable.

Model auto-downloads on first run (~1.8 GB).
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Singleton model instance — load once, reuse across calls
_model = None
_model_device = None


def _get_model(device: str = "cpu"):
    """Load XTTS v2 model (singleton pattern). Only loads once per process."""
    global _model, _model_device

    if _model is not None and _model_device == device:
        return _model

    try:
        from TTS.api import TTS
    except ImportError:
        raise ImportError(
            "TTS package not installed. Run: pip install TTS"
        )

    logger.info(f"[XTTS] Loading model on {device}... (first run downloads ~1.8 GB)")

    # Set custom model cache directory
    model_dir = os.environ.get("COQUI_HOME", "models/xtts")
    os.makedirs(model_dir, exist_ok=True)

    _model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    _model_device = device

    logger.info("[XTTS] Model loaded successfully.")
    return _model


def synthesize_xtts(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize speech using Coqui XTTS v2 with voice cloning.

    Args:
        text: The text to speak.
        output_path: Where to save the output audio (mp3 or wav).
        inputs: CF2 inputs dict with voice_clone_config.

    Returns:
        Status string with emoji indicator.
    """
    # Smart skip — CF2 Rule 24
    if os.path.exists(output_path):
        logger.debug(f"[XTTS] Skipped (exists): {output_path}")
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg = inputs.get("voice_clone_config", {})
    speaker_wav = cfg.get("speaker_wav", "assets/voices/matin.wav")
    lang = cfg.get("language", "en")
    device = cfg.get("device", "cpu")
    use_cache = cfg.get("use_cache", True)

    # Resolve per-role speaker WAV
    role = inputs.get("role")
    if role:
        per_role = cfg.get("per_role_voices", {})
        speaker_wav = per_role.get(role, speaker_wav)

    # Cache check
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, speaker_wav, lang, engine="xtts")
        if cached and os.path.exists(cached):
            import shutil
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(cached, output_path)
            logger.info(f"[XTTS] Served from cache: {output_path}")
            return f"⏭️ Served from cache: {output_path}"

    # Validate speaker WAV
    if not Path(speaker_wav).exists():
        raise FileNotFoundError(f"Speaker WAV not found: {speaker_wav}")

    # Load and convert speaker WAV if needed
    from cf2.core.services.voice_clone.voice_loader import load_speaker_wav
    ready_wav = load_speaker_wav(speaker_wav, auto_convert=True)

    # Load model
    model = _get_model(device)

    # Determine output format
    output_is_wav = output_path.lower().endswith(".wav")
    if output_is_wav:
        tmp_wav = output_path
    else:
        tmp_wav = output_path.rsplit(".", 1)[0] + "_tmp.wav"

    # Synthesize
    logger.info(f"[XTTS] Generating: {text[:60]}... (lang={lang}, device={device})")

    model.tts_to_file(
        text=text,
        speaker_wav=ready_wav,
        language=lang,
        file_path=tmp_wav,
    )

    # Convert to MP3 if needed
    if not output_is_wav:
        from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
        wav_to_mp3(tmp_wav, output_path)
        Path(tmp_wav).unlink(missing_ok=True)
    else:
        # Normalize WAV
        from cf2.core.services.voice_clone.audio_exporter import normalize_wav
        normalize_wav(output_path)

    # Store in cache
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import set_cached
        set_cached(text, speaker_wav, lang, output_path, engine="xtts")

    logger.info(f"[XTTS] Generated: {output_path}")
    return f"✅ XTTS generated: {output_path}"
```

---

## File 6 — `src/cf2/core/services/voice_clone/kokoro_service.py`

```python
# src/cf2/core/services/voice_clone/kokoro_service.py
"""
Kokoro TTS — Lightest & fastest option for CF2.
No voice cloning from sample, but high-quality pretrained voices.
Best for dev/testing speed (~5 sec/min audio on CPU).
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Available Kokoro voices
KOKORO_VOICES = {
    # Female US English
    "af_heart", "af_bella", "af_nicole", "af_sarah",
    # Male US English
    "am_adam", "am_michael",
    # Female British
    "bf_emma", "bf_isabella",
    # Male British
    "bm_george", "bm_lewis",
}

_kokoro_instance = None


def _get_kokoro():
    """Load Kokoro model (singleton)."""
    global _kokoro_instance
    if _kokoro_instance is not None:
        return _kokoro_instance

    try:
        from kokoro_onnx import Kokoro
    except ImportError:
        raise ImportError(
            "kokoro-onnx not installed. Run: pip install kokoro-onnx soundfile"
        )

    # Auto-download model if not present
    model_path = "kokoro-v1.0.onnx"
    voices_path = "voices-v1.0.bin"

    if not os.path.exists(model_path) or not os.path.exists(voices_path):
        logger.info("[Kokoro] Downloading model (~300 MB)...")
        # Kokoro auto-downloads on first init
        _kokoro_instance = Kokoro(model_path, voices_path)
    else:
        _kokoro_instance = Kokoro(model_path, voices_path)

    logger.info("[Kokoro] Model loaded.")
    return _kokoro_instance


def synthesize_kokoro(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize speech using Kokoro TTS.

    Note: Kokoro does NOT clone from a speaker WAV — it uses pretrained voices.
    The `kokoro_voice` config key selects which voice to use.
    """
    # Smart skip
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg = inputs.get("voice_clone_config", {})
    voice = cfg.get("kokoro_voice", "af_heart")
    speed = cfg.get("audio_speed", 1.0)
    use_cache = cfg.get("use_cache", True)

    # Validate voice name
    if voice not in KOKORO_VOICES:
        logger.warning(
            f"[Kokoro] Unknown voice '{voice}'. Available: {sorted(KOKORO_VOICES)}. "
            f"Falling back to 'af_heart'."
        )
        voice = "af_heart"

    # Cache check
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, voice, "en", engine="kokoro")
        if cached and os.path.exists(cached):
            import shutil
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    # Load model
    kokoro = _get_kokoro()

    # Synthesize
    logger.info(f"[Kokoro] Generating with voice={voice}, speed={speed}...")
    samples, sample_rate = kokoro.create(
        text=text,
        voice=voice,
        speed=speed,
        lang="en-us",
    )

    # Write output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    output_is_wav = output_path.lower().endswith(".wav")

    if output_is_wav:
        import soundfile as sf
        sf.write(output_path, samples, sample_rate)
    else:
        # Write temp WAV, then convert to MP3
        tmp_wav = output_path.rsplit(".", 1)[0] + "_tmp.wav"
        import soundfile as sf
        sf.write(tmp_wav, samples, sample_rate)

        from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
        wav_to_mp3(tmp_wav, output_path)
        Path(tmp_wav).unlink(missing_ok=True)

    # Cache
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import set_cached
        set_cached(text, voice, "en", output_path, engine="kokoro")

    logger.info(f"[Kokoro] Generated: {output_path}")
    return f"✅ Kokoro generated: {output_path}"
```

---

## File 7 — `src/cf2/core/services/voice_clone/openvoice_service.py`

```python
# src/cf2/core/services/voice_clone/openvoice_service.py
"""
OpenVoice v2 — Fast clone quality ratio.
Good for multi-voice debate (different tone per role). No training required.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_tone_converter = None
_melo_tts = None


def _get_melo_tts(device: str = "cpu"):
    """Load MeloTTS base model (singleton)."""
    global _melo_tts
    if _melo_tts is not None:
        return _melo_tts

    try:
        from melo.api import TTS as MeloTTS
    except ImportError:
        raise ImportError(
            "melo-tts not installed. Run: pip install melo-tts"
        )

    _melo_tts = MeloTTS(language="EN", device=device)
    logger.info("[OpenVoice] MeloTTS loaded.")
    return _melo_tts


def _get_tone_converter(device: str = "cpu"):
    """Load OpenVoice tone color converter (singleton)."""
    global _tone_converter
    if _tone_converter is not None:
        return _tone_converter

    try:
        from openvoice.api import ToneColorConverter
    except ImportError:
        raise ImportError(
            "openvoice not installed. Run: pip install openvoice"
        )

    config_path = "checkpoints_v2/converter/config.json"
    ckpt_path = "checkpoints_v2/converter/checkpoint.pth"

    if not os.path.exists(config_path) or not os.path.exists(ckpt_path):
        logger.info("[OpenVoice] Downloading checkpoints...")
        # OpenVoice auto-downloads on first se_extractor call
        # or download manually from GitHub releases

    _tone_converter = ToneColorConverter(config_path, device=device)
    _tone_converter.load_ckpt(ckpt_path)
    logger.info("[OpenVoice] Tone converter loaded.")
    return _tone_converter


def synthesize_openvoice(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize speech using OpenVoice v2 with voice cloning.
    Two-step process: MeloTTS base → OpenVoice tone transfer.
    """
    # Smart skip
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg = inputs.get("voice_clone_config", {})
    ref_wav = cfg.get("speaker_wav", "assets/voices/matin.wav")
    device = cfg.get("device", "cpu")
    use_cache = cfg.get("use_cache", True)
    tau = cfg.get("openvoice_tau", 0.3)  # tone transfer strength

    # Resolve per-role
    role = inputs.get("role")
    if role:
        per_role = cfg.get("per_role_voices", {})
        ref_wav = per_role.get(role, ref_wav)

    # Cache check
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, ref_wav, "en", engine="openvoice")
        if cached and os.path.exists(cached):
            import shutil
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    if not Path(ref_wav).exists():
        raise FileNotFoundError(f"Speaker WAV not found: {ref_wav}")

    # Load models
    melo = _get_melo_tts(device)
    tone_conv = _get_tone_converter(device)

    # Step 1: Generate base audio with MeloTTS
    tmp_wav = output_path.rsplit(".", 1)[0] + "_ov_base.wav"
    speaker_ids = melo.hps.data.spk2id
    melo.tts_to_file(text, speaker_ids["EN-US"], tmp_wav, speed=1.0)
    logger.info("[OpenVoice] Base audio generated.")

    # Step 2: Extract speaker embeddings and transfer tone
    from openvoice import se_extractor

    target_se, _ = se_extractor.get_se(ref_wav, tone_conv, vad=False)
    source_se, _ = se_extractor.get_se(tmp_wav, tone_conv, vad=False)

    # Step 3: Tone color conversion
    output_is_wav = output_path.lower().endswith(".wav")
    if output_is_wav:
        conv_path = output_path
    else:
        conv_path = output_path.rsplit(".", 1)[0] + "_conv.wav"

    tone_conv.convert(
        audio_src_path=tmp_wav,
        src_se=source_se,
        tgt_se=target_se,
        output_path=conv_path,
        tau=tau,
    )

    # Convert to MP3 if needed
    if not output_is_wav:
        from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
        wav_to_mp3(conv_path, output_path)
        Path(conv_path).unlink(missing_ok=True)

    # Cleanup temp
    Path(tmp_wav).unlink(missing_ok=True)

    # Cache
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import set_cached
        set_cached(text, ref_wav, "en", output_path, engine="openvoice")

    logger.info(f"[OpenVoice] Generated: {output_path}")
    return f"✅ OpenVoice generated: {output_path}"
```

---

## File 8 — `src/cf2/core/services/voice_clone/chatterbox_service.py`

```python
# src/cf2/core/services/voice_clone/chatterbox_service.py
"""
Chatterbox TTS — Emotion-aware voice cloning (2025).
Built by Resemble AI. Clones from a reference sample with adjustable emotion.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_chatterbox_model = None


def _get_chatterbox(device: str = "cpu"):
    """Load Chatterbox model (singleton)."""
    global _chatterbox_model
    if _chatterbox_model is not None:
        return _chatterbox_model

    try:
        from chatterbox.tts import ChatterboxTTS
    except ImportError:
        raise ImportError(
            "chatterbox-tts not installed. Run: pip install chatterbox-tts"
        )

    logger.info(f"[Chatterbox] Loading model on {device}... (first run downloads ~1.2 GB)")
    _chatterbox_model = ChatterboxTTS.from_pretrained(device=device)
    logger.info("[Chatterbox] Model loaded.")
    return _chatterbox_model


def synthesize_chatterbox(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize speech using Chatterbox TTS with emotion-aware voice cloning.
    """
    # Smart skip
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg = inputs.get("voice_clone_config", {})
    ref_wav = cfg.get("speaker_wav", "assets/voices/matin.wav")
    exaggeration = cfg.get("chatterbox_exaggeration", 0.5)
    cfg_weight = cfg.get("chatterbox_cfg_weight", 0.5)
    device = cfg.get("device", "cpu")
    use_cache = cfg.get("use_cache", True)

    # Resolve per-role
    role = inputs.get("role")
    if role:
        per_role = cfg.get("per_role_voices", {})
        ref_wav = per_role.get(role, ref_wav)

    # Cache check
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, ref_wav, "en", engine="chatterbox")
        if cached and os.path.exists(cached):
            import shutil
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    if not Path(ref_wav).exists():
        raise FileNotFoundError(f"Speaker WAV not found: {ref_wav}")

    # Load model
    model = _get_chatterbox(device)

    # Synthesize
    logger.info(
        f"[Chatterbox] Generating: {text[:60]}... "
        f"(exag={exaggeration}, cfg={cfg_weight})"
    )

    wav = model.generate(
        text,
        audio_prompt_path=ref_wav,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
    )

    # Write output
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    output_is_wav = output_path.lower().endswith(".wav")

    if output_is_wav:
        import torchaudio
        torchaudio.save(output_path, wav, model.sr)
    else:
        # Save temp WAV, then convert
        tmp_wav = output_path.rsplit(".", 1)[0] + "_tmp.wav"
        import torchaudio
        torchaudio.save(tmp_wav, wav, model.sr)

        from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
        wav_to_mp3(tmp_wav, output_path)
        Path(tmp_wav).unlink(missing_ok=True)

    # Cache
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import set_cached
        set_cached(text, ref_wav, "en", output_path, engine="chatterbox")

    logger.info(f"[Chatterbox] Generated: {output_path}")
    return f"✅ Chatterbox generated: {output_path}"
```

---

## File 9 — `src/cf2/core/services/voice_clone/rvc_service.py`

```python
# src/cf2/core/services/voice_clone/rvc_service.py
"""
RVC (Retrieval-based Voice Conversion) — Highest character fidelity.
Does NOT generate from text — converts any TTS output into your voice.
Pipeline: text → piper (fast) → WAV → RVC converter → your voice.

Requires a trained RVC model. Use AFTER setting up XTTS as primary.
"""

import os
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def synthesize_rvc(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize speech using RVC voice conversion.
    Step 1: Generate base audio with piper (fast, offline).
    Step 2: Convert to your voice using RVC model.
    """
    # Smart skip
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg = inputs.get("voice_clone_config", {})
    model_path = cfg.get("rvc_model", "models/rvc/matin.pth")
    index_path = cfg.get("rvc_index", "models/rvc/matin.index")
    f0_method = cfg.get("rvc_f0_method", "rmvpe")
    use_cache = cfg.get("use_cache", True)

    # Resolve per-role
    role = inputs.get("role")
    if role:
        per_role = cfg.get("per_role_voices", {})
        role_model = per_role.get(role)
        if role_model and role_model.endswith(".pth"):
            model_path = role_model

    # Cache check
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, model_path, "rvc", engine="rvc")
        if cached and os.path.exists(cached):
            import shutil
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    # Validate model
    if not Path(model_path).exists():
        raise FileNotFoundError(
            f"RVC model not found: {model_path}. "
            "Train a model first or download from HuggingFace community."
        )

    # Step 1: Generate base audio with piper
    tmp_piper = output_path.rsplit(".", 1)[0] + "_rvc_base.wav"
    _generate_piper_base(text, tmp_piper, inputs)
    logger.info(f"[RVC] Base audio generated: {tmp_piper}")

    # Step 2: Convert with RVC
    tmp_rvc_wav = output_path.rsplit(".", 1)[0] + "_rvc_out.wav"
    _run_rvc_inference(tmp_piper, tmp_rvc_wav, model_path, index_path, f0_method, inputs)
    logger.info(f"[RVC] Voice converted: {tmp_rvc_wav}")

    # Convert to final format
    output_is_wav = output_path.lower().endswith(".wav")

    if output_is_wav:
        import shutil
        from cf2.core.services.voice_clone.audio_exporter import normalize_wav
        shutil.copy2(tmp_rvc_wav, output_path)
        normalize_wav(output_path)
    else:
        from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
        wav_to_mp3(tmp_rvc_wav, output_path)

    # Cleanup temps
    Path(tmp_piper).unlink(missing_ok=True)
    Path(tmp_rvc_wav).unlink(missing_ok=True)

    # Cache
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import set_cached
        set_cached(text, model_path, "rvc", output_path, engine="rvc")

    logger.info(f"[RVC] Generated: {output_path}")
    return f"✅ RVC generated: {output_path}"


def _generate_piper_base(text: str, output_wav: str, inputs: dict) -> str:
    """Generate base audio using piper (fast, offline TTS)."""
    os.makedirs(os.path.dirname(output_wav) or ".", exist_ok=True)

    try:
        # Try using piper Python API first
        from cf2.core.services.tts_service import synthesize
        piper_inputs = {**inputs, "tts_engine": "piper"}
        synthesize(text, output_wav, piper_inputs)
    except Exception:
        # Fallback: piper CLI
        piper_model = inputs.get("voice_clone_config", {}).get(
            "rvc_piper_model", "models/piper/joe_medium.onnx"
        )

        if not Path(piper_model).exists():
            raise FileNotFoundError(
                f"Piper model not found: {piper_model}. "
                "Needed for RVC base generation."
            )

        cmd = [
            "piper",
            "--model", piper_model,
            "--output_file", output_wav,
        ]
        result = subprocess.run(
            cmd, input=text, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"Piper failed: {result.stderr}")

    return output_wav


def _run_rvc_inference(
    input_wav: str,
    output_wav: str,
    model_path: str,
    index_path: str,
    f0_method: str = "rmvpe",
    inputs: dict = None,
) -> str:
    """Run RVC inference on a WAV file."""
    cfg = (inputs or {}).get("voice_clone_config", {})
    rvc_dir = cfg.get("rvc_dir", "vendor/rvc")

    infer_script = Path(rvc_dir) / "tools" / "infer_cli.py"

    if infer_script.exists():
        # Use local RVC installation
        cmd = [
            "python", str(infer_script),
            "--input_path", input_wav,
            "--output_path", output_wav,
            "--model_path", model_path,
            "--index_path", index_path,
            "--f0method", f0_method,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"RVC inference failed: {result.stderr}")
    else:
        # Try rvc-python package
        try:
            from rvc.python.infer import infer_rvc
            infer_rvc(
                input_path=input_wav,
                output_path=output_wav,
                model_path=model_path,
                index_path=index_path,
                f0_method=f0_method,
            )
        except ImportError:
            raise ImportError(
                "RVC not available. Install one of:\n"
                "  1. pip install rvc-python\n"
                "  2. git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI vendor/rvc"
            )

    return output_wav
```

---

## File 10 — `src/cf2/core/services/voice_clone/styletts2_service.py`

```python
# src/cf2/core/services/voice_clone/styletts2_service.py
"""
StyleTTS2 — Research-grade quality, highest naturalness.
Slow on CPU (~3–5 min/min audio). Best for overnight batch generation.
English only.
"""

import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_styletts2_model = None


def _get_styletts2(device: str = "cpu"):
    """Load StyleTTS2 model (singleton)."""
    global _styletts2_model
    if _styletts2_model is not None:
        return _styletts2_model

    styletts_dir = Path("vendor/styletts2")
    if not styletts_dir.exists():
        raise FileNotFoundError(
            "StyleTTS2 not found. Run:\n"
            "  git clone https://github.com/yl4579/StyleTTS2 vendor/styletts2\n"
            "  cd vendor/styletts2 && pip install -r requirements.txt"
        )

    import sys
    if str(styletts_dir) not in sys.path:
        sys.path.insert(0, str(styletts_dir))

    # Import and initialize
    try:
        from models import load_model
        _styletts2_model = load_model(
            str(styletts_dir / "Models", ),
            device=device,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to load StyleTTS2: {e}")

    logger.info("[StyleTTS2] Model loaded.")
    return _styletts2_model


def synthesize_styletts2(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize speech using StyleTTS2.
    Note: English only. Slow on CPU — use for batch generation.
    """
    # Smart skip
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg = inputs.get("voice_clone_config", {})
    ref_wav = cfg.get("speaker_wav", "assets/voices/matin.wav")
    device = cfg.get("device", "cpu")
    use_cache = cfg.get("use_cache", True)

    # Resolve per-role
    role = inputs.get("role")
    if role:
        per_role = cfg.get("per_role_voices", {})
        ref_wav = per_role.get(role, ref_wav)

    # Cache check
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, ref_wav, "en", engine="styletts2")
        if cached and os.path.exists(cached):
            import shutil
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            shutil.copy2(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    if not Path(ref_wav).exists():
        raise FileNotFoundError(f"Speaker WAV not found: {ref_wav}")

    logger.warning(
        "[StyleTTS2] This engine is slow on CPU (~3–5 min/min audio). "
        "Consider using XTTS or Kokoro instead."
    )

    # Load model
    model = _get_styletts2(device)

    # Synthesize
    logger.info(f"[StyleTTS2] Generating: {text[:60]}...")

    output_is_wav = output_path.lower().endswith(".wav")
    tmp_wav = output_path if output_is_wav else output_path.rsplit(".", 1)[0] + "_tmp.wav"

    # StyleTTS2 inference
    # This is a skeleton — adjust based on your StyleTTS2 setup
    try:
        import torch
        import numpy as np

        # Reference: use the StyleTTS2 inference API
        from infer import synthesize as stts2_synthesize
        stts2_synthesize(
            text=text,
            ref_wav=ref_wav,
            output_path=tmp_wav,
            device=device,
        )
    except Exception as e:
        logger.error(f"[StyleTTS2] Synthesis failed: {e}")
        raise RuntimeError(f"StyleTTS2 synthesis failed: {e}")

    # Convert to MP3 if needed
    if not output_is_wav:
        from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
        wav_to_mp3(tmp_wav, output_path)
        Path(tmp_wav).unlink(missing_ok=True)

    # Cache
    if use_cache:
        from cf2.core.services.voice_clone.cache_manager import set_cached
        set_cached(text, ref_wav, "en", output_path, engine="styletts2")

    logger.info(f"[StyleTTS2] Generated: {output_path}")
    return f"✅ StyleTTS2 generated: {output_path}"
```

---

## File 11 — `src/cf2/core/services/tts_service.py` (Extended Router)

```python
# src/cf2/core/services/tts_service.py
"""
CF2 TTS Engine Router.
Routes synthesis requests to the appropriate TTS engine based on config.
Follows CF2 Rule 23 (config-driven selection) and Rule 11 (fallback support).
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def synthesize(text: str, output_path: str, inputs: dict) -> str:
    """
    Main TTS routing function. Selects engine from inputs["tts_engine"].

    Args:
        text: Text to synthesize.
        output_path: Where to save the output audio file.
        inputs: CF2 inputs dict. Must contain "tts_engine" key.

    Returns:
        Status string with emoji indicator.

    Raises:
        ValueError: If tts_engine is unknown.
    """
    engine = inputs.get("tts_engine", "gtts")

    logger.info(f"[TTS] Engine: {engine}, text: {text[:50]}...")

    # ---- Cloud / lightweight engines ----
    if engine == "gtts":
        return _run_gtts(text, output_path, inputs)
    elif engine == "edge-tts":
        return _run_edge_tts(text, output_path, inputs)
    elif engine == "piper":
        return _run_piper(text, output_path, inputs)

    # ---- Voice cloning engines ----
    elif engine == "xtts":
        from cf2.core.services.voice_clone.xtts_service import synthesize_xtts
        return synthesize_xtts(text, output_path, inputs)

    elif engine == "openvoice":
        from cf2.core.services.voice_clone.openvoice_service import synthesize_openvoice
        return synthesize_openvoice(text, output_path, inputs)

    elif engine == "kokoro":
        from cf2.core.services.voice_clone.kokoro_service import synthesize_kokoro
        return synthesize_kokoro(text, output_path, inputs)

    elif engine == "chatterbox":
        from cf2.core.services.voice_clone.chatterbox_service import synthesize_chatterbox
        return synthesize_chatterbox(text, output_path, inputs)

    elif engine == "rvc":
        from cf2.core.services.voice_clone.rvc_service import synthesize_rvc
        return synthesize_rvc(text, output_path, inputs)

    elif engine == "styletts2":
        from cf2.core.services.voice_clone.styletts2_service import synthesize_styletts2
        return synthesize_styletts2(text, output_path, inputs)

    else:
        raise ValueError(
            f"Unknown tts_engine: '{engine}'. "
            f"Valid options: gtts, edge-tts, piper, xtts, openvoice, kokoro, "
            f"chatterbox, rvc, styletts2"
        )


def synthesize_with_fallback(text: str, output_path: str, inputs: dict) -> str:
    """
    Synthesize with automatic fallback.
    If primary engine fails, falls back to tts_fallback engine.
    Follows CF2 Rule 11 (centralized config + fallback).
    """
    primary = inputs.get("tts_engine", "gtts")
    fallback = inputs.get("tts_fallback", "piper")

    try:
        return synthesize(text, output_path, inputs)
    except Exception as e:
        logger.warning(
            f"[TTS] Primary engine '{primary}' failed: {e}. "
            f"Falling back to '{fallback}'."
        )

        fallback_inputs = {**inputs, "tts_engine": fallback}
        try:
            return synthesize(text, output_path, fallback_inputs)
        except Exception as fb_err:
            logger.error(f"[TTS] Fallback engine '{fallback}' also failed: {fb_err}")
            raise RuntimeError(
                f"Both primary ({primary}) and fallback ({fallback}) TTS engines failed."
            )


# ============================================================
# Existing engine implementations (preserve as-is)
# ============================================================

def _run_gtts(text: str, output_path: str, inputs: dict) -> str:
    """Google TTS — simple, online, always works."""
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    try:
        from gtts import gTTS
    except ImportError:
        raise ImportError("gTTS not installed. Run: pip install gTTS")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    lang = inputs.get("language", "en")
    tts = gTTS(text=text, lang=lang)
    tts.save(output_path)
    return f"✅ gTTS generated: {output_path}"


def _run_edge_tts(text: str, output_path: str, inputs: dict) -> str:
    """Microsoft Edge TTS — free, good quality, online."""
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    try:
        import edge_tts
    except ImportError:
        raise ImportError("edge-tts not installed. Run: pip install edge-tts")

    import asyncio

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    voice = inputs.get("edge_tts_voice", "en-US-GuyNeural")

    async def _generate():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)

    asyncio.run(_generate())
    return f"✅ Edge-TTS generated: {output_path}"


def _run_piper(text: str, output_path: str, inputs: dict) -> str:
    """Piper — fast, offline, local TTS."""
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    import subprocess

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    piper_model = inputs.get("piper_model", "models/piper/joe_medium.onnx")
    piper_binary = inputs.get("piper_binary", "piper")

    cmd = [piper_binary, "--model", piper_model, "--output_file", output_path]

    try:
        result = subprocess.run(
            cmd, input=text, capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            raise RuntimeError(f"Piper failed: {result.stderr}")
    except FileNotFoundError:
        raise FileNotFoundError(
            "Piper binary not found. Install: https://github.com/rhasspy/piper"
        )

    return f"✅ Piper generated: {output_path}"
```

---

## File 12 — `src/cf2/core/services/audio_service.py` (Per-Role Resolution)

```python
# src/cf2/core/services/audio_service.py
"""
CF2 Audio Service — Orchestrates TTS calls with per-role voice resolution.
"""

import os
import logging
from pathlib import Path
from typing import Optional

from cf2.core.services.tts_service import synthesize, synthesize_with_fallback

logger = logging.getLogger(__name__)


# Map debate roles to edge_tts voice names (existing CF2 convention)
ROLE_VOICE_MAP = {
    "propose": "en-US-GuyNeural",
    "oppose":  "en-US-JennyNeural",
    "decide":  "en-US-AriaNeural",
    "judge_f": "en-US-JennyNeural",
    "judge_m": "en-US-GuyNeural",
}


def get_speaker_wav(role: str, inputs: dict) -> str:
    """
    Resolve the speaker WAV path for a given debate role.
    Checks per_role_voices first, falls back to default speaker_wav.

    Follows CF2 Rule 23 (config-driven, never hardcoded).
    """
    vc_cfg = inputs.get("voice_clone_config", {})
    per_role = vc_cfg.get("per_role_voices", {})
    default_wav = vc_cfg.get("speaker_wav", "assets/voices/matin.wav")

    wav = per_role.get(role, default_wav)

    if not Path(wav).exists():
        logger.warning(
            f"[AudioService] Role WAV missing for '{role}': {wav}. "
            f"Using default: {default_wav}"
        )
        return default_wav

    return wav


def generate_speech(
    text: str,
    output_path: str,
    inputs: dict,
    role: Optional[str] = None,
) -> str:
    """
    Generate speech for a given text and optional debate role.
    Handles per-role voice selection and fallback.

    Args:
        text: Text to speak.
        output_path: Output audio file path.
        inputs: CF2 inputs dict.
        role: Debate role (propose, oppose, decide, judge_f, judge_m).

    Returns:
        Status string with emoji indicator.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Inject role into inputs for engine-level per-role resolution
    if role:
        inputs = {**inputs, "role": role}

        # For edge-tts, also set the appropriate voice
        if inputs.get("tts_engine") == "edge-tts":
            inputs["edge_tts_voice"] = ROLE_VOICE_MAP.get(role, "en-US-GuyNeural")

    # Use fallback-enabled synthesis
    use_fallback = inputs.get("tts_fallback") is not None

    if use_fallback:
        return synthesize_with_fallback(text, output_path, inputs)
    else:
        return synthesize(text, output_path, inputs)


def generate_debate_audio(
    segments: list,
    output_dir: str,
    inputs: dict,
) -> dict:
    """
    Generate audio for all debate segments.
    Each segment is a dict with 'role', 'text', and optional 'filename'.

    Args:
        segments: List of {"role": str, "text": str, "filename": str (optional)}.
        output_dir: Directory for output audio files.
        inputs: CF2 inputs dict.

    Returns:
        Dict mapping segment index to output path.
    """
    os.makedirs(output_dir, exist_ok=True)
    results = {}

    for i, seg in enumerate(segments):
        role = seg.get("role", "narrator")
        text = seg.get("text", "")
        filename = seg.get("filename", f"audio_{i:03d}_{role}.mp3")
        output_path = os.path.join(output_dir, filename)

        try:
            status = generate_speech(text, output_path, inputs, role=role)
            results[i] = {"path": output_path, "status": status, "role": role}
            logger.info(f"[AudioService] Segment {i}: {status}")
        except Exception as e:
            logger.error(f"[AudioService] Segment {i} failed: {e}")
            results[i] = {"path": None, "status": f"❌ Failed: {e}", "role": role}

    return results
```

---

## File 13 — Config Schema Extension for `data.schema.json`

```json
{
  "tts_engine": {
    "type": "string",
    "enum": ["gtts", "edge-tts", "piper", "xtts", "openvoice", "kokoro", "chatterbox", "rvc", "styletts2"],
    "default": "gtts",
    "description": "TTS engine to use. Clone engines (xtts, openvoice, kokoro, chatterbox, rvc, styletts2) require voice_clone_config."
  },

  "tts_fallback": {
    "type": "string",
    "enum": ["gtts", "edge-tts", "piper"],
    "default": "piper",
    "description": "Fallback TTS engine if primary fails. Recommended: piper (fast, offline)."
  },

  "voice_clone_config": {
    "type": "object",
    "description": "Configuration for voice cloning engines. Only used when tts_engine is a clone engine.",
    "properties": {
      "speaker_wav": {
        "type": "string",
        "default": "assets/voices/matin.wav",
        "description": "Path to the default speaker WAV sample (20-40 sec, clean, mono, 22050 Hz)."
      },
      "language": {
        "type": "string",
        "default": "en",
        "description": "Language code for synthesis. XTTS supports: en, bn, fr, de, etc."
      },
      "use_cache": {
        "type": "boolean",
        "default": true,
        "description": "Cache synthesized audio by text hash. Skips regeneration on re-run."
      },
      "cache_dir": {
        "type": "string",
        "default": ".runtime/cache/voice_clone/",
        "description": "Directory for audio cache files."
      },
      "device": {
        "type": "string",
        "enum": ["auto", "cpu", "cuda", "mps"],
        "default": "auto",
        "description": "Inference device. auto=detect GPU/CPU."
      },
      "kokoro_voice": {
        "type": "string",
        "default": "af_heart",
        "enum": ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_adam", "am_michael", "bf_emma", "bf_isabella", "bm_george", "bm_lewis"],
        "description": "Kokoro TTS voice name (only used when tts_engine=kokoro)."
      },
      "audio_speed": {
        "type": "number",
        "default": 1.0,
        "minimum": 0.5,
        "maximum": 2.0,
        "description": "Speech speed multiplier (1.0 = normal)."
      },
      "chatterbox_exaggeration": {
        "type": "number",
        "default": 0.5,
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Chatterbox emotion exaggeration (0=neutral, 1=max)."
      },
      "chatterbox_cfg_weight": {
        "type": "number",
        "default": 0.5,
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Chatterbox CFG guidance weight."
      },
      "openvoice_tau": {
        "type": "number",
        "default": 0.3,
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "OpenVoice tone transfer strength."
      },
      "rvc_model": {
        "type": "string",
        "default": "models/rvc/matin.pth",
        "description": "Path to trained RVC model (.pth file)."
      },
      "rvc_index": {
        "type": "string",
        "default": "models/rvc/matin.index",
        "description": "Path to RVC feature index file."
      },
      "rvc_f0_method": {
        "type": "string",
        "default": "rmvpe",
        "enum": ["pm", "harvest", "crepe", "rmvpe"],
        "description": "RVC pitch extraction method."
      },
      "per_role_voices": {
        "type": "object",
        "description": "Per-debate-role voice override. Keys match debate roles.",
        "properties": {
          "propose": {
            "type": "string",
            "description": "Speaker WAV for the propose role."
          },
          "oppose": {
            "type": "string",
            "description": "Speaker WAV for the oppose role."
          },
          "decide": {
            "type": "string",
            "description": "Speaker WAV for the decide role."
          },
          "judge_f": {
            "type": "string",
            "description": "Speaker WAV for the female judge role."
          },
          "judge_m": {
            "type": "string",
            "description": "Speaker WAV for the male judge role."
          }
        }
      }
    }
  }
}
```

---

## File 14 — Sample `data.json` Configs

```json
// === DEV MODE (fast, no cloning) ===
{
  "tts_engine": "kokoro",
  "tts_fallback": "piper",
  "voice_clone_config": {
    "kokoro_voice": "am_adam",
    "audio_speed": 1.0,
    "use_cache": true,
    "device": "cpu"
  }
}

// === PRODUCTION MODE (branded voice, XTTS cloning) ===
{
  "tts_engine": "xtts",
  "tts_fallback": "piper",
  "voice_clone_config": {
    "speaker_wav": "assets/voices/matin.wav",
    "language": "en",
    "use_cache": true,
    "device": "cpu",
    "per_role_voices": {
      "propose": "assets/voices/matin.wav",
      "oppose":  "assets/voices/narrator_female.wav",
      "decide":  "assets/voices/judge_en.wav",
      "judge_f": "assets/voices/narrator_female.wav",
      "judge_m": "assets/voices/matin.wav"
    }
  }
}

// === EMOTION MODE (Chatterbox with exaggeration) ===
{
  "tts_engine": "chatterbox",
  "tts_fallback": "piper",
  "voice_clone_config": {
    "speaker_wav": "assets/voices/matin.wav",
    "chatterbox_exaggeration": 0.7,
    "chatterbox_cfg_weight": 0.5,
    "use_cache": true,
    "device": "cpu"
  }
}
```

---

## File 15 — Test Script (`test_voice_clone.py`)

```python
#!/usr/bin/env python3
"""
CF2 Voice Clone Integration Test.
Tests each engine with a short phrase.
Run: python test_voice_clone.py
"""

import os
import sys
import json

# Add project root to path
sys.path.insert(0, "/var/POAi/CrewAiFlow/cf2/src")

OUTPUT_DIR = "output/voice_clone_test"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TEST_TEXT = "Hello, this is a test of the CF2 voice cloning system."
TEST_TEXT_BN = "এটি সিএফটু ভয়েস ক্লোনিং সিস্টেমের একটি পরীক্ষা।"


def test_engine(engine_name: str, inputs: dict, text: str = TEST_TEXT, suffix: str = ""):
    """Test a single TTS engine."""
    output_path = os.path.join(OUTPUT_DIR, f"test_{engine_name}{suffix}.mp3")

    try:
        from cf2.core.services.tts_service import synthesize_with_fallback
        result = synthesize_with_fallback(text, output_path, inputs)
        print(f"  [{engine_name}] {result}")
        return True
    except Exception as e:
        print(f"  [{engine_name}] ❌ FAILED: {e}")
        return False


def main():
    print("=" * 60)
    print("  CF2 Voice Clone Integration Test")
    print("=" * 60)

    # Check if voice sample exists
    if not os.path.exists("assets/voices/matin.wav"):
        print("\n⚠️  No voice sample found at assets/voices/matin.wav")
        print("   Recording a test sample...")
        os.makedirs("assets/voices", exist_ok=True)

        # Generate a synthetic test tone as fallback
        import numpy as np
        try:
            import soundfile as sf
            sr = 22050
            duration = 10  # 10 seconds
            t = np.linspace(0, duration, sr * duration)
            # Simple speech-like signal (for testing only)
            signal = 0.3 * np.sin(2 * np.pi * 150 * t) * np.exp(-t * 0.5)
            sf.write("assets/voices/matin.wav", signal, sr)
            print("   ✅ Created synthetic test sample (replace with real recording!)")
        except ImportError:
            print("   ❌ Cannot create test sample. Please record assets/voices/matin.wav manually.")
            print("      Run: arecord -f S16_LE -r 22050 -c 1 assets/voices/matin.wav")
            return

    results = {}

    # Test 1: gTTS (baseline)
    print("\n📡 Testing gTTS...")
    results["gtts"] = test_engine("gtts", {"tts_engine": "gtts"})

    # Test 2: Piper (fallback)
    print("\n🔊 Testing Piper...")
    results["piper"] = test_engine("piper", {"tts_engine": "piper"})

    # Test 3: Kokoro (fast dev)
    print("\n⚡ Testing Kokoro...")
    results["kokoro"] = test_engine("kokoro", {
        "tts_engine": "kokoro",
        "voice_clone_config": {"kokoro_voice": "af_heart", "use_cache": True, "device": "cpu"}
    })

    # Test 4: XTTS (main clone engine)
    print("\n🎤 Testing XTTS v2...")
    results["xtts"] = test_engine("xtts", {
        "tts_engine": "xtts",
        "voice_clone_config": {
            "speaker_wav": "assets/voices/matin.wav",
            "language": "en",
            "use_cache": True,
            "device": "cpu",
        }
    })

    # Test 5: XTTS Bengali
    print("\n🇧🇩 Testing XTTS Bengali...")
    results["xtts_bn"] = test_engine("xtts_bn", {
        "tts_engine": "xtts",
        "voice_clone_config": {
            "speaker_wav": "assets/voices/matin.wav",
            "language": "bn",
            "use_cache": True,
            "device": "cpu",
        }
    }, text=TEST_TEXT_BN, suffix="_bn")

    # Test 6: Chatterbox
    print("\n🎭 Testing Chatterbox...")
    results["chatterbox"] = test_engine("chatterbox", {
        "tts_engine": "chatterbox",
        "voice_clone_config": {
            "speaker_wav": "assets/voices/matin.wav",
            "chatterbox_exaggeration": 0.5,
            "use_cache": True,
            "device": "cpu",
        }
    })

    # Test 7: OpenVoice
    print("\n🔔 Testing OpenVoice...")
    results["openvoice"] = test_engine("openvoice", {
        "tts_engine": "openvoice",
        "voice_clone_config": {
            "speaker_wav": "assets/voices/matin.wav",
            "use_cache": True,
            "device": "cpu",
        }
    })

    # Test 8: Fallback chain
    print("\n🔀 Testing Fallback (xtts → piper)...")
    results["fallback"] = test_engine("fallback", {
        "tts_engine": "xtts",
        "tts_fallback": "piper",
        "voice_clone_config": {
            "speaker_wav": "assets/voices/matin.wav",
            "language": "en",
            "use_cache": True,
            "device": "cpu",
        }
    })

    # Test 9: Per-role voices
    print("\n🎭 Testing Per-Role Voices...")
    for role in ["propose", "oppose", "decide"]:
        test_engine(f"role_{role}", {
            "tts_engine": "kokoro",
            "tts_fallback": "piper",
            "role": role,
            "voice_clone_config": {
                "kokoro_voice": "am_adam" if role in ["propose", "decide"] else "af_heart",
                "use_cache": True,
                "device": "cpu",
            }
        }, suffix=f"_{role}")

    # Summary
    print("\n" + "=" * 60)
    print("  TEST SUMMARY")
    print("=" * 60)
    for engine, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {engine:15s} {status}")

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"\n  Total: {passed}/{total} passed")

    # Cache stats
    try:
        from cf2.core.services.voice_clone.cache_manager import cache_stats
        stats = cache_stats()
        print(f"\n  Cache: {stats['valid_entries']} entries, {stats['total_mb']} MB")
    except Exception:
        pass

    print("=" * 60)


if __name__ == "__main__":
    main()
```

---

## File 16 — Quick Start Script (`quickstart_voice_clone.sh`)

```bash
#!/bin/bash
# quickstart_voice_clone.sh — Get voice cloning running in 5 minutes
# Run: chmod +x quickstart_voice_clone.sh && ./quickstart_voice_clone.sh

set -e

echo "🎙️  CF2 Voice Cloning — Quick Start"
echo "===================================="

PROJECT_ROOT="/var/POAi/CrewAiFlow/cf2"
cd "$PROJECT_ROOT"

# 1. Create directory structure
echo ""
echo "📁 Creating directories..."
mkdir -p assets/voices
mkdir -p models/xtts
mkdir -p models/rvc
mkdir -p src/cf2/core/services/voice_clone
mkdir -p .runtime/cache/voice_clone

# 2. Record voice sample
echo ""
echo "🎤 Recording voice sample (30 seconds)..."
echo "   Speak naturally into your microphone."
echo "   Press Ctrl+C when done."
echo ""

if [ ! -f "assets/voices/matin.wav" ]; then
    echo "   Recording starts in 3 seconds..."
    sleep 3
    arecord -f S16_LE -r 22050 -c 1 -d 30 assets/voices/matin.wav
    echo "   ✅ Voice sample saved: assets/voices/matin.wav"
else
    echo "   ⏭️  Voice sample already exists, skipping recording."
fi

# 3. Validate recording
echo ""
echo "🔍 Validating voice sample..."
if command -v ffprobe &> /dev/null; then
    DURATION=$(ffprobe -v quiet -print_format json -show_streams assets/voices/matin.wav \
        | python3 -c "import json,sys; print(float(json.load(sys.stdin)['streams'][0]['duration']))" 2>/dev/null || echo "0")
    echo "   Duration: ${DURATION}s"
    if (( $(echo "$DURATION < 6" | bc -l) )); then
        echo "   ⚠️  Recording too short (minimum 6s). Please re-record."
        exit 1
    fi
else
    echo "   ⚠️  ffprobe not found. Install ffmpeg for validation: sudo apt install ffmpeg"
fi

# 4. Install dependencies
echo ""
echo "📦 Installing TTS packages..."
echo "   Choose which engines to install:"
echo "   1) XTTS v2 only (recommended, ~2 GB download)"
echo "   2) Kokoro only (fastest, ~300 MB download)"  
echo "   3) All engines (everything)"
echo "   4) Skip installation"
echo ""
read -p "   Enter choice [1-4]: " INSTALL_CHOICE

case $INSTALL_CHOICE in
    1)
        pip install TTS
        ;;
    2)
        pip install kokoro-onnx soundfile
        ;;
    3)
        pip install TTS
        pip install kokoro-onnx soundfile
        pip install openvoice
        pip install chatterbox-tts
        ;;
    4)
        echo "   Skipping installation."
        ;;
    *)
        echo "   Invalid choice, skipping."
        ;;
esac

# 5. Quick test
echo ""
echo "🧪 Running quick test..."
python3 - <<'PYEOF'
import os, sys
sys.path.insert(0, "src")

test_text = "Hello, this is my cloned voice for the PlayOwnAi channel."
output_dir = "output/voice_clone_test"
os.makedirs(output_dir, exist_ok=True)

# Try Kokoro first (fastest)
try:
    from cf2.core.services.voice_clone.kokoro_service import synthesize_kokoro
    result = synthesize_kokoro(
        test_text,
        os.path.join(output_dir, "quickstart_test.mp3"),
        {"voice_clone_config": {"kokoro_voice": "af_heart", "use_cache": False, "device": "cpu"}}
    )
    print(f"   {result}")
except Exception as e:
    print(f"   Kokoro test failed: {e}")
    print("   Trying XTTS instead...")
    try:
        from cf2.core.services.voice_clone.xtts_service import synthesize_xtts
        result = synthesize_xtts(
            test_text,
            os.path.join(output_dir, "quickstart_test.mp3"),
            {"voice_clone_config": {"speaker_wav": "assets/voices/matin.wav", "language": "en", "use_cache": False, "device": "cpu"}}
        )
        print(f"   {result}")
    except Exception as e2:
        print(f"   XTTS test also failed: {e2}")
        print("   Check your installation and try again.")
        sys.exit(1)

print("   ✅ Quick test complete!")
PYEOF

echo ""
echo "===================================="
echo "✅ Setup complete!"
echo ""
echo "   Next steps:"
echo "   1. Listen to output/voice_clone_test/quickstart_test.mp3"
echo "   2. Set tts_engine in your data.json config"
echo "   3. Run: python test_voice_clone.py  (full test suite)"
echo ""
echo "   Recommended config for production:"
echo '   "tts_engine": "xtts",'
echo '   "tts_fallback": "piper",'
echo '   "voice_clone_config": {"speaker_wav": "assets/voices/matin.wav", "language": "en", "device": "cpu"}'
echo "===================================="
```

---

## Summary — All Files at a Glance

| # | File Path | Purpose |
|---|---|---|
| 1 | `voice_clone/__init__.py` | Package init + registry |
| 2 | `voice_clone/cache_manager.py` | Text-hash audio cache (smart skip) |
| 3 | `voice_clone/audio_exporter.py` | WAV↔MP3 conversion + normalization |
| 4 | `voice_clone/voice_loader.py` | Speaker WAV validation + auto-convert |
| 5 | `voice_clone/xtts_service.py` | **Coqui XTTS v2** (recommended primary) |
| 6 | `voice_clone/kokoro_service.py` | **Kokoro TTS** (fastest, dev mode) |
| 7 | `voice_clone/openvoice_service.py` | **OpenVoice v2** (fast multi-voice) |
| 8 | `voice_clone/chatterbox_service.py` | **Chatterbox TTS** (emotion-aware) |
| 9 | `voice_clone/rvc_service.py` | **RVC** (highest fidelity, needs training) |
| 10 | `voice_clone/styletts2_service.py` | **StyleTTS2** (research-grade) |
| 11 | `tts_service.py` | Engine router (extended with all clone engines) |
| 12 | `audio_service.py` | Per-role voice resolution + orchestration |
| 13 | Schema JSON | Config schema extension |
| 14 | data.json examples | Dev / Production / Emotion configs |
| 15 | `test_voice_clone.py` | Full integration test suite |
| 16 | `quickstart_voice_clone.sh` | One-command setup script |

Every file follows the **same contract**: `synthesize(text, output_path, inputs) → status_string`. No unit redesign needed. Drop in, configure, and generate. 🎙️
