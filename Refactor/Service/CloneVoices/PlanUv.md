# 🎙️ CF2 Voice Cloning Integration Guide

> **CF2 Engineering Standard — TTS Extension Layer**
> Every rule in this guide aligns with CF2 Rule.md. Voice cloning is a **drop-in TTS engine swap**, not a pipeline redesign.

---

## 📑 INDEX

- [Core Principle](#core-principle)
- [CF2 Integration Architecture](#cf2-integration-architecture)
- [Config Schema Extension](#config-schema-extension)
- [Engine Comparison Matrix](#engine-comparison-matrix)
- [Option 1 — Coqui XTTS v2 (Recommended)](#option-1--coqui-xtts-v2-recommended)
- [Option 2 — RVC (Retrieval-based Voice Conversion)](#option-2--rvc-retrieval-based-voice-conversion)
- [Option 3 — StyleTTS2](#option-3--stylettsz)
- [Option 4 — OpenVoice v2](#option-4--openvoice-v2)
- [Option 5 — Kokoro TTS](#option-5--kokoro-tts)
- [Option 6 — Chatterbox TTS](#option-6--chatterbox-tts)
- [Hybrid Mode — XTTS + Piper Fallback](#hybrid-mode--xtts--piper-fallback)
- [Per-Role Voice Cloning for Debate Pipeline](#per-role-voice-cloning-for-debate-pipeline)
- [File Structure](#file-structure)
- [Smart Skip Integration](#smart-skip-integration)
- [Hardware Guide — HP ZHAN 66 (Ryzen 5 4500U)](#hardware-guide--hp-zhan-66-ryzen-5-4500u)
- [Voice Sample Recording Guide](#voice-sample-recording-guide)
- [Anti-Patterns](#anti-patterns)

---

## 🔥 Core Principle

> **Replace only the TTS layer. Nothing else changes.**

Voice cloning in CF2 is a **TTS engine swap**. The pipeline contract is unchanged:

```
Unit-Debate / Unit-Animation / Unit-Definition
        ↓
  tts_service.py  ←── only this file grows
        ↓
  audio.mp3 / audio.wav
        ↓
  existing merge pipeline (unchanged)
```

Adding `xtts` follows the exact same pattern as `piper` or `edge-tts`. No unit redesign. No new crew agents. No schema breakage.

---

## 🏗️ CF2 Integration Architecture

### Where TTS lives now

```
src/cf2/core/services/
├── audio_service.py      ← orchestrates TTS calls
└── tts_service.py        ← engine router (add new engines here)
```

### Extended structure (add, never replace)

```
src/cf2/core/services/
├── audio_service.py          ← unchanged
├── tts_service.py            ← add elif tts_engine == "xtts" branch
└── voice_clone/              ← NEW: one subfolder per engine
    ├── __init__.py
    ├── xtts_service.py       ← Coqui XTTS v2
    ├── rvc_service.py        ← RVC pipeline
    ├── openvoice_service.py  ← OpenVoice v2
    ├── stylettsz_service.py  ← StyleTTS2
    ├── kokoro_service.py     ← Kokoro TTS
    ├── chatterbox_service.py ← Chatterbox TTS
    ├── voice_loader.py       ← load speaker sample WAV
    ├── audio_exporter.py     ← normalize + export mp3/wav
    └── cache_manager.py      ← smart skip for generated audio
```

### Assets & models

```
assets/
└── voices/
    ├── matin.wav             ← your cloned narrator voice
    ├── narrator_female.wav   ← oppose / judge_f role
    └── judge_en.wav          ← decide / verdict role

models/
├── piper/                    ← existing piper .onnx files (unchanged)
└── xtts/                     ← downloaded on first run
    ├── config.json
    ├── model.pth
    └── vocab.json
```

### tts_service.py routing (existing pattern extended)

```python
# src/cf2/core/services/tts_service.py

def synthesize(text: str, output_path: str, inputs: dict) -> str:
    engine = inputs.get("tts_engine", "gtts")

    if engine == "gtts":
        return _run_gtts(text, output_path, inputs)
    elif engine == "edge-tts":
        return _run_edge_tts(text, output_path, inputs)
    elif engine == "piper":
        return _run_piper(text, output_path, inputs)
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
    else:
        raise ValueError(f"Unknown tts_engine: {engine}")
```

> **CF2 Rule 23 compliance:** engine name comes from `inputs`, never hardcoded.

---

## ⚙️ Config Schema Extension

### New fields to add to `data.schema.json`

```json
"tts_engine": {
  "enum": ["gtts", "edge-tts", "piper", "xtts", "openvoice", "kokoro", "chatterbox"],
  "description": "Add xtts/openvoice/kokoro/chatterbox for local voice cloning."
},

"tts_fallback": {
  "type": "string",
  "description": "Fallback engine if primary fails. Recommended: piper (fast, offline).",
  "enum": ["gtts", "edge-tts", "piper"],
  "default": "piper",
  "example": "piper"
},

"voice_clone_config": {
  "type": "object",
  "description": "Config for all local voice cloning engines. Only read when tts_engine is a clone engine.",
  "properties": {
    "speaker_wav": {
      "type": "string",
      "description": "Path to your cloned voice WAV sample (20–40 sec, clean, mono).",
      "example": "assets/voices/matin.wav"
    },
    "language": {
      "type": "string",
      "description": "Language code for synthesis. XTTS: 'en', 'bn', etc.",
      "default": "en",
      "example": "en"
    },
    "use_cache": {
      "type": "boolean",
      "description": "Cache synthesized audio by text hash. Skips regeneration on re-run.",
      "default": true,
      "example": true
    },
    "cache_dir": {
      "type": "string",
      "description": "Directory for audio cache files.",
      "default": ".runtime/cache/voice_clone/",
      "example": ".runtime/cache/voice_clone/"
    },
    "device": {
      "type": "string",
      "description": "Inference device. auto=detect GPU/CPU automatically.",
      "enum": ["auto", "cpu", "cuda", "mps"],
      "default": "auto",
      "example": "cpu"
    },
    "per_role_voices": {
      "type": "object",
      "description": "Per-debate-role voice override. Keys match edge_tts_voices roles.",
      "properties": {
        "propose": { "type": "string", "example": "assets/voices/matin.wav" },
        "oppose":  { "type": "string", "example": "assets/voices/narrator_female.wav" },
        "decide":  { "type": "string", "example": "assets/voices/judge_en.wav" },
        "judge_f": { "type": "string", "example": "assets/voices/narrator_female.wav" },
        "judge_m": { "type": "string", "example": "assets/voices/matin.wav" }
      }
    }
  }
}
```

### Minimal `data.json` override to activate XTTS

```json
{
  "tts_engine": "xtts",
  "tts_fallback": "piper",
  "voice_clone_config": {
    "speaker_wav": "assets/voices/matin.wav",
    "language": "en",
    "use_cache": true,
    "device": "cpu"
  }
}
```

> **CF2 Rule 29 compliance:** existing keys never removed — new keys appended only.

---

## 📊 Engine Comparison Matrix

| Engine | Clone Quality | Install Complexity | CPU Speed (Ryzen 4500U) | VRAM Required | Multilingual | Best For |
|---|---|---|---|---|---|---|
| **Coqui XTTS v2** | ⭐⭐⭐⭐⭐ | Medium | ~1–3 min/min audio | 0 (CPU ok) | ✅ 17 langs | Main narrator voice |
| **OpenVoice v2** | ⭐⭐⭐⭐ | Medium | ~45 sec/min audio | 0 (CPU ok) | ✅ good | Fast multi-voice |
| **Kokoro TTS** | ⭐⭐⭐⭐ | Easy | ~20 sec/min audio | 0 (CPU ok) | ❌ EN only | Speed + quality balance |
| **Chatterbox TTS** | ⭐⭐⭐⭐ | Easy | ~40 sec/min audio | 0 (CPU ok) | ❌ EN only | Emotional expression |
| **StyleTTS2** | ⭐⭐⭐⭐ | Hard | ~2–4 min/min audio | 2 GB+ | ❌ EN only | Research-grade quality |
| **RVC** | ⭐⭐⭐⭐⭐ | Hard | Needs XTTS first | 0 (CPU ok) | ✅ any | Voice character converter |
| **Piper (existing)** | ⭐⭐⭐ | Already installed | ~5 sec/min audio | 0 | ✅ many | Fallback / dev testing |

> **Recommendation for your HP ZHAN 66 (Ryzen 4500U, 16GB RAM, no NVIDIA GPU):**
> Primary: **Coqui XTTS v2** · Fallback: **Piper** · Fast alternative: **Kokoro TTS**

---

## Option 1 — Coqui XTTS v2 (Recommended)

**Best overall for CF2.** Zero-shot voice cloning from a 6-second sample. No training needed.

### Why it fits CF2

- Runs fully local (no API cost)
- 17 languages including Bengali (`bn`)
- Python API — clean integration into `tts_service.py`
- Outputs WAV directly, normalize to MP3 via existing `audio_exporter.py`
- Model auto-downloads on first run (~1.8 GB)

### Install

```bash
cd /var/POAi/CrewAiFlow/cf2

# Install XTTS v2 via uv optional group
uv sync --extra xtts

# Verify
uv run python -c "from TTS.api import TTS; print('XTTS ready')"
```

> First run downloads model to `~/.local/share/tts/tts_models--multilingual--multi-dataset--xtts_v2/`
> To cache it inside your project folder instead:

```bash
mkdir -p models/xtts
export COQUI_HOME=/var/POAi/CrewAiFlow/cf2/models/xtts
```

### Create `xtts_service.py`

```python
# src/cf2/core/services/voice_clone/xtts_service.py

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
```

### First test

```bash
uv run python - <<'EOF'
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
tts.tts_to_file(
    text="Hello, this is my cloned voice for PlayOwnAi channel.",
    speaker_wav="assets/voices/matin.wav",
    language="en",
    file_path="output/test_clone.wav"
)
print("Done — check output/test_clone.wav")
EOF
```

### Bengali language test

```bash
uv run python - <<'EOF'
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to("cpu")
tts.tts_to_file(
    text="আমার কণ্ঠস্বর ক্লোন করা হয়েছে।",
    speaker_wav="assets/voices/matin.wav",
    language="bn",
    file_path="output/test_clone_bn.wav"
)
EOF
```

---

## Option 2 — RVC (Retrieval-based Voice Conversion)

**Best character fidelity.** Does not generate from text directly — it converts any TTS output into your voice. Use with XTTS or piper as the base TTS, then run RVC on top.

### Architecture in CF2

```
text → piper (fast) → raw_audio.wav → RVC converter → your_voice.wav → mp3
```

### Why this is advanced

- Requires training a small model (~10–15 min of voice data recommended)
- Much more convincing result than zero-shot XTTS
- Works with any base TTS (even fast piper), then transforms it to your voice
- CPU-capable on your machine, but slow (~3–5x real-time)

### Install

```bash
# Option A — rvc-python package via uv
uv add rvc-python

# Option B — clone the lightweight inference fork (recommended)
git clone https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI \
    /var/POAi/CrewAiFlow/cf2/vendor/rvc
uv sync --extra rvc
```

### Pre-trained model download (skip training)

```bash
mkdir -p models/rvc
# Download from Hugging Face (community voices) or train your own
# Place as: models/rvc/matin.pth + models/rvc/matin.index
```

### Create `rvc_service.py`

```python
# src/cf2/core/services/voice_clone/rvc_service.py
# Pattern: generate with piper → convert with RVC

import os
from pathlib import Path

def synthesize_rvc(text: str, output_path: str, inputs: dict) -> str:
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    cfg        = inputs.get("voice_clone_config", {})
    model_path = cfg.get("rvc_model", "models/rvc/matin.pth")
    index_path = cfg.get("rvc_index", "models/rvc/matin.index")

    # Step 1: generate base audio with piper
    tmp_piper = output_path.replace(".mp3", "_rvc_base.wav")
    _generate_piper(text, tmp_piper, inputs)

    # Step 2: convert with RVC
    _run_rvc_inference(tmp_piper, output_path, model_path, index_path)
    Path(tmp_piper).unlink(missing_ok=True)

    return f"✅ RVC converted: {output_path}"

def _run_rvc_inference(input_wav, output_path, model_path, index_path):
    # Integrate with rvc-python or subprocess call
    import subprocess
    subprocess.run([
        "python", "vendor/rvc/tools/infer_cli.py",
        "--input_path", input_wav,
        "--output_path", output_path,
        "--model_path", model_path,
        "--index_path", index_path,
        "--f0method", "rmvpe"
    ], check=True)
```

### When to use RVC

Use RVC when:
- You have trained a voice model on 10+ minutes of your recordings
- You want the highest possible voice similarity
- You accept longer generation time

Do NOT use RVC as your starting point — set up XTTS first, then upgrade to RVC later.

---

## Option 3 — StyleTTS2

**Research-grade quality.** Highest naturalness. Requires more setup.

### Install

```bash
git clone https://github.com/yl4579/StyleTTS2 \
    /var/POAi/CrewAiFlow/cf2/vendor/stylettsz

uv sync --extra stylettsz

# Download pretrained LJSpeech model
mkdir -p models/stylettsz
# Follow model download from: https://huggingface.co/yl4579/StyleTTS2-LibriTTS
```

### Performance on your machine

- ~3–5 min per minute of audio on CPU (Ryzen 4500U)
- Better suited for overnight batch generation
- Not recommended as primary engine for real-time dev

### `stylettsz_service.py` skeleton

```python
# src/cf2/core/services/voice_clone/stylettsz_service.py

import os

def synthesize_stylettsz(text: str, output_path: str, inputs: dict) -> str:
    if os.path.exists(output_path):
        return f"⏭️ Skipped: {output_path}"

    cfg      = inputs.get("voice_clone_config", {})
    ref_wav  = cfg.get("speaker_wav", "assets/voices/matin.wav")
    # StyleTTS2 inference call
    # ... (vendor integration)
    return f"✅ StyleTTS2 generated: {output_path}"
```

---

## Option 4 — OpenVoice v2

**Fastest clone quality ratio.** Good for multi-voice debate (different tone per role). No training required.

### Install

```bash
# Option A — via uv optional group (melo-tts on PyPI)
uv sync --extra openvoice

# Option B — from source for absolute latest version
git clone https://github.com/myshell-ai/OpenVoice \
    /var/POAi/CrewAiFlow/cf2/vendor/openvoice
uv add --editable vendor/openvoice

# Checkpoints auto-download on first run
uv run python -c "import openvoice; print('OpenVoice ready')"
```

### Create `openvoice_service.py`

```python
# src/cf2/core/services/voice_clone/openvoice_service.py

import os
from pathlib import Path

def synthesize_openvoice(text: str, output_path: str, inputs: dict) -> str:
    if os.path.exists(output_path):
        return f"⏭️ Skipped: {output_path}"

    cfg     = inputs.get("voice_clone_config", {})
    ref_wav = cfg.get("speaker_wav", "assets/voices/matin.wav")
    device  = cfg.get("device", "cpu")

    from openvoice import se_extractor
    from openvoice.api import ToneColorConverter
    from melo.api import TTS as MeloTTS

    # Step 1: base TTS with MeloTTS
    tts = MeloTTS(language="EN", device=device)
    tmp_wav = output_path.replace(".mp3", "_ov_base.wav")
    speaker_ids = tts.hps.data.spk2id
    tts.tts_to_file(text, speaker_ids["EN-US"], tmp_wav, speed=1.0)

    # Step 2: tone color transfer
    tone_converter = ToneColorConverter(
        f"checkpoints_v2/converter/config.json", device=device
    )
    tone_converter.load_ckpt("checkpoints_v2/converter/checkpoint.pth")

    target_se, _ = se_extractor.get_se(ref_wav, tone_converter, vad=False)
    source_se    = se_extractor.get_se(tmp_wav, tone_converter, vad=False)[0]

    tone_converter.convert(
        audio_src_path=tmp_wav,
        src_se=source_se,
        tgt_se=target_se,
        output_path=output_path,
        tau=0.3
    )

    Path(tmp_wav).unlink(missing_ok=True)
    return f"✅ OpenVoice generated: {output_path}"
```

### Test

```bash
uv run python - <<'EOF'
from melo.api import TTS
tts = TTS(language="EN", device="cpu")
tts.tts_to_file(
    "Testing OpenVoice on CF2 pipeline.",
    tts.hps.data.spk2id["EN-US"],
    "output/test_openvoice.wav"
)
print("Base audio done. Run tone conversion next.")
EOF
```

---

## Option 5 — Kokoro TTS

**Lightest & fastest option.** No voice cloning from your sample, but high-quality pretrained voices. Best for dev/testing speed.

### Install

```bash
uv sync --extra kokoro

# Model downloads automatically (~300 MB)
```

### Create `kokoro_service.py`

```python
# src/cf2/core/services/voice_clone/kokoro_service.py

import os
import soundfile as sf
import numpy as np

def synthesize_kokoro(text: str, output_path: str, inputs: dict) -> str:
    if os.path.exists(output_path):
        return f"⏭️ Skipped: {output_path}"

    cfg    = inputs.get("voice_clone_config", {})
    voice  = cfg.get("kokoro_voice", "af_heart")  # see voice list below
    speed  = cfg.get("audio_speed", 1.0)

    from kokoro_onnx import Kokoro
    kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
    samples, sample_rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")

    sf.write(output_path, samples, sample_rate)
    return f"✅ Kokoro generated: {output_path}"
```

### Available Kokoro voices

```
af_heart    af_bella    af_nicole    af_sarah     (female US English)
am_adam     am_michael                            (male US English)
bf_emma     bf_isabella                           (female British)
bm_george   bm_lewis                              (male British)
```

### Test

```bash
uv run python - <<'EOF'
from kokoro_onnx import Kokoro
kokoro = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")
samples, sr = kokoro.create("Hello from CF2.", voice="am_adam", speed=1.0, lang="en-us")
import soundfile as sf
sf.write("output/test_kokoro.wav", samples, sr)
print("Done")
EOF
```

---

## Option 6 — Chatterbox TTS

**Newest option (2025).** Emotion-aware voice cloning from a reference sample. Built by Resemble AI.

### Install

```bash
uv sync --extra chatterbox

# Model auto-downloads (~1.2 GB)
```

### Create `chatterbox_service.py`

```python
# src/cf2/core/services/voice_clone/chatterbox_service.py

import os
import torchaudio

def synthesize_chatterbox(text: str, output_path: str, inputs: dict) -> str:
    if os.path.exists(output_path):
        return f"⏭️ Skipped: {output_path}"

    cfg         = inputs.get("voice_clone_config", {})
    ref_wav     = cfg.get("speaker_wav", "assets/voices/matin.wav")
    exaggeration = cfg.get("chatterbox_exaggeration", 0.5)
    cfg_weight  = cfg.get("chatterbox_cfg_weight", 0.5)
    device      = cfg.get("device", "cpu")

    from chatterbox.tts import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained(device=device)

    wav = model.generate(
        text,
        audio_prompt_path=ref_wav,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight
    )

    torchaudio.save(output_path, wav, model.sr)
    return f"✅ Chatterbox generated: {output_path}"
```

### Test

```bash
uv run python - <<'EOF'
from chatterbox.tts import ChatterboxTTS
import torchaudio

model = ChatterboxTTS.from_pretrained(device="cpu")
wav = model.generate(
    "Testing Chatterbox voice cloning on CF2.",
    audio_prompt_path="assets/voices/matin.wav"
)
torchaudio.save("output/test_chatterbox.wav", wav, model.sr)
print("Done — check output/test_chatterbox.wav")
EOF
```

---

## 🔀 Hybrid Mode — XTTS + Piper Fallback

Add fallback logic in `tts_service.py`. Follows CF2 Rule 11 (centralized LLM config + fallback).

```python
# src/cf2/core/services/tts_service.py

def synthesize_with_fallback(text: str, output_path: str, inputs: dict) -> str:
    primary  = inputs.get("tts_engine", "piper")
    fallback = inputs.get("tts_fallback", "piper")

    try:
        return synthesize(text, output_path, inputs)
    except Exception as e:
        import logging
        logging.warning(f"[TTS] Primary engine '{primary}' failed: {e}. Falling back to '{fallback}'.")

        fallback_inputs = {**inputs, "tts_engine": fallback}
        return synthesize(text, output_path, fallback_inputs)
```

### Config

```json
{
  "tts_engine": "xtts",
  "tts_fallback": "piper"
}
```

---

## 🎭 Per-Role Voice Cloning for Debate Pipeline

CF2's debate pipeline has 5 roles (`propose`, `oppose`, `decide`, `judge_f`, `judge_m`). Use per-role voice overrides so each role sounds distinct.

### Config

```json
{
  "tts_engine": "xtts",
  "voice_clone_config": {
    "language": "en",
    "device": "cpu",
    "use_cache": true,
    "per_role_voices": {
      "propose": "assets/voices/matin.wav",
      "oppose":  "assets/voices/narrator_female.wav",
      "decide":  "assets/voices/judge_en.wav",
      "judge_f": "assets/voices/narrator_female.wav",
      "judge_m": "assets/voices/matin.wav"
    }
  }
}
```

### Resolution logic in `audio_service.py`

```python
def get_speaker_wav(role: str, inputs: dict) -> str:
    vc_cfg      = inputs.get("voice_clone_config", {})
    per_role    = vc_cfg.get("per_role_voices", {})
    default_wav = vc_cfg.get("speaker_wav", "assets/voices/matin.wav")

    wav = per_role.get(role, default_wav)

    if not Path(wav).exists():
        logging.warning(f"[TTS] Role WAV missing for '{role}': {wav}. Using default.")
        return default_wav

    return wav
```

---

## 📁 File Structure (Final)

```
/var/POAi/CrewAiFlow/cf2/
├── assets/
│   └── voices/
│       ├── matin.wav              ← YOUR voice sample (record this first)
│       ├── narrator_female.wav
│       └── judge_en.wav
│
├── models/
│   ├── piper/                     ← existing (unchanged)
│   │   ├── joe_medium.onnx
│   │   └── alba_medium.onnx
│   └── xtts/                      ← XTTS model cache
│       ├── config.json
│       ├── model.pth
│       └── vocab.json
│
├── src/cf2/core/services/
│   ├── tts_service.py             ← engine router (extended)
│   ├── audio_service.py           ← unchanged
│   └── voice_clone/               ← NEW
│       ├── __init__.py
│       ├── xtts_service.py
│       ├── rvc_service.py
│       ├── openvoice_service.py
│       ├── stylettsz_service.py
│       ├── kokoro_service.py
│       ├── chatterbox_service.py
│       ├── voice_loader.py
│       ├── audio_exporter.py
│       └── cache_manager.py
│
└── .runtime/cache/
    └── voice_clone/               ← audio cache (never committed)
        └── {hash}.wav
```

---

## ⏭️ Smart Skip Integration

The `cache_manager.py` provides text-level audio caching. Same text + same WAV = reuse cached audio. Follows CF2 Rule 24 (smart skip mandatory) and Rule 32 (no repeated LLM/TTS work).

```python
# src/cf2/core/services/voice_clone/cache_manager.py

import hashlib
import json
from pathlib import Path

CACHE_ROOT = Path(".runtime/cache/voice_clone")

def _key(text: str, wav: str, lang: str) -> str:
    raw = f"{text}|{wav}|{lang}"
    return hashlib.md5(raw.encode()).hexdigest()

def get_cached(text: str, wav: str, lang: str) -> str | None:
    key     = _key(text, wav, lang)
    index   = CACHE_ROOT / "index.json"
    if not index.exists():
        return None
    data = json.loads(index.read_text())
    return data.get(key)

def set_cached(text: str, wav: str, lang: str, output_path: str) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    index = CACHE_ROOT / "index.json"
    data  = json.loads(index.read_text()) if index.exists() else {}
    key   = _key(text, wav, lang)
    data[key] = output_path
    index.write_text(json.dumps(data, indent=2))
```

---

## 💻 Hardware Guide — HP ZHAN 66 (Ryzen 5 4500U, 16 GB RAM)

| Engine | CPU Generation Time | RAM Usage | Practical Use |
|---|---|---|---|
| Kokoro | ~5 sec/min audio | ~800 MB | ✅ Dev & testing |
| OpenVoice v2 | ~45 sec/min audio | ~1.2 GB | ✅ Fast production |
| Chatterbox | ~40 sec/min audio | ~1.5 GB | ✅ Emotional output |
| XTTS v2 | ~90 sec/min audio | ~2.0 GB | ✅ Main production |
| StyleTTS2 | ~240 sec/min audio | ~2.5 GB | ⚠️ Batch only |
| RVC | ~180 sec/min audio | ~1.8 GB | ⚠️ After XTTS base |

### Batch strategy for your machine

For **Shorts narration** (~60–90 sec): XTTS → ~2.5 min generation → fully acceptable.

For **HD debate video** (~8–12 min narration): generate overnight or use Kokoro for speed with XTTS for final.

```json
{
  "_comment": "Dev mode — fast",
  "tts_engine": "kokoro",
  "tts_fallback": "piper"
}

{
  "_comment": "Production mode — branded voice",
  "tts_engine": "xtts",
  "tts_fallback": "piper"
}
```

---

## 🎤 Voice Sample Recording Guide

A clean voice sample is the most important factor in clone quality.

### Requirements

| Parameter | Requirement |
|---|---|
| Duration | 20–40 seconds |
| Format | WAV (not MP3) |
| Sample rate | 22050 Hz or 24000 Hz |
| Channels | Mono |
| Environment | Quiet room, no fan, no echo |
| Content | Natural speaking pace, varied sentences |

### Recording on Ubuntu

```bash
# Option 1: Audacity (GUI)
sudo apt install audacity
# Record → Export → WAV → 22050 Hz → Mono

# Option 2: arecord (CLI)
arecord -f S16_LE -r 22050 -c 1 assets/voices/matin.wav
# Press Ctrl+C to stop after 30–40 seconds

# Option 3: ffmpeg from microphone
ffmpeg -f alsa -i default -ar 22050 -ac 1 assets/voices/matin.wav
# Ctrl+C to stop
```

### What to say (sample script)

> *"Hello, welcome to PlayOwnAi. Today we're exploring some of the most exciting trends in artificial intelligence and technology. The world is changing fast, and staying ahead means understanding the data behind every major shift. Let's dive in."*

That single paragraph gives XTTS enough variation (questions, statements, emphasis) for a high-quality clone.

### Verify your recording

```bash
ffprobe -v quiet -print_format json -show_streams assets/voices/matin.wav \
  | python3 -c "
import json, sys
s = json.load(sys.stdin)['streams'][0]
print(f'Duration: {float(s[\"duration\"]):.1f}s')
print(f'Sample rate: {s[\"sample_rate\"]} Hz')
print(f'Channels: {s[\"channels\"]}')
"
```

---

## 🚫 Anti-Patterns

Following CF2 Rule 39 — these are banned, no exceptions.

| Anti-Pattern | Rule Violated | Correct Approach |
|---|---|---|
| Hardcoded voice WAV path in any tool | Rule 23, Rule 28 | Always read from `inputs["voice_clone_config"]["speaker_wav"]` |
| Clone engine placed outside `voice_clone/` subfolder | Rule 17 (function isolation) | One file per engine in `voice_clone/` |
| Generating audio without smart skip check | Rule 24, Rule 32 | Check `os.path.exists(output_path)` first |
| Unit-Debate calling XTTS directly | Rule 8 (consumer units read-only) | Route through `tts_service.py` only |
| Writing cached audio to `output/` | Rule 39 (`.runtime/cache/` boundary) | Cache goes to `.runtime/cache/voice_clone/` |
| Running full XTTS model init on every call | — | Singleton pattern (`_model` global, init once) |
| Committing `models/xtts/` or `.runtime/` to git | Rule 39 | Add to `.gitignore` |
| Two engines sharing the same output path | Rule 20 (idempotent writes) | Each engine writes to its own tmp path |

---

## 🎯 Recommended Migration Path

### Stage 1 (Today — 1 hour)

```bash
# 1. Create folders
mkdir -p assets/voices models/xtts src/cf2/core/services/voice_clone

# 2. Record your voice sample
arecord -f S16_LE -r 22050 -c 1 assets/voices/matin.wav

# 3. Install XTTS
uv sync --extra xtts

# 4. Test standalone
uv run python -c "from TTS.api import TTS; TTS('tts_models/multilingual/multi-dataset/xtts_v2')"
```

### Stage 2 (Day 1 — integrate CF2)

- Create `xtts_service.py`, `cache_manager.py`, `audio_exporter.py`
- Add `elif engine == "xtts"` branch in `tts_service.py`
- Add `voice_clone_config` block to `data.schema.json`
- Set `"tts_engine": "xtts"` in `data.json` + test one video

### Stage 3 (Week 1 — per-role voices)

- Record `narrator_female.wav` and `judge_en.wav`
- Enable `per_role_voices` in `voice_clone_config`
- Run full debate video with 5 distinct cloned voices

### Stage 4 (Optional — premium upgrade)

- Collect 10+ min of clean recordings
- Train RVC model
- Use piper → RVC pipeline for highest voice fidelity

---

## 🧠 Final Mental Model

```
data.json
  "tts_engine": "xtts"
  "tts_fallback": "piper"
  "voice_clone_config": { ... }
        ↓
tts_service.py  (router — unchanged interface)
        ↓
voice_clone/xtts_service.py  (new engine — isolated)
        ↓
assets/voices/matin.wav  (your identity)
        ↓
.runtime/output/{slug}/debate/audio_{role}.mp3
        ↓
existing merge pipeline (100% unchanged)
```

> **One voice. Every video. Your brand.**
