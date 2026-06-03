Yes — **very possible**, and for your CF2 architecture this should be a **new small service/unit**, not a full new pipeline.

Since your source is an existing local video (`/home/matin/Desktop/_Classes_Objects.mp4`) and you already cloned a voice with [Coqui XTTS v2](https://github.com/coqui-ai/TTS?utm_source=chatgpt.com), the simplest flow is:

### Your use case

1. Keep original video visuals
2. Remove original audio
3. Generate new cloned narration
4. Merge cloned narration back into same video

That means you do **not** need Unit-Data / Unit-Debate / rendering pipeline.

---

# Best fit in CF2

Create a reusable service:

### `src/cf2/core/services/video_redub_service.py`

Responsibility:

* input: existing mp4 + text/script + speaker voice sample
* output: same video with replaced cloned voice audio

This fits your rules:

* service = pure reusable block
* no unit coupling
* can later be used by your classroom tutor feature

---

# Recommended mini flow

```text
input/video/_Classes_Objects.mp4
        ↓
extract original duration
        ↓
script.md (manual or whisper-generated)
        ↓
xtts_service.py
        ↓
new narration.wav
        ↓
ffmpeg replace audio
        ↓
output/redubbed_class.mp4
```

---

# Reuse existing service

You already have:

* `xtts_service.py` → voice clone
* ffmpeg installed
* profile-based config system

So only add one new service layer:

### Reuse:

* `xtts_service.py`
* maybe future `transcript_service.py`

### Add:

* `video_redub_service.py`

---

# Minimal engineering design

Suggested structure:

```text
src/cf2/core/services/
├── xtts_service.py          # existing
├── transcript_service.py    # optional future
├── video_redub_service.py   # new
```

---

# Inside new service

Tasks:

### 1. Strip old audio

Example command:

```bash
ffmpeg -i input.mp4 -an silent.mp4
```

### 2. Generate cloned voice

Using your existing XTTS:

```python
clone_to_file(text, speaker_wav, output_wav)
```

### 3. Merge

```bash
ffmpeg -i silent.mp4 -i cloned.wav -c:v copy -map 0:v -map 1:a final.mp4
```

---

# Even better for your classroom project

Since you said earlier CF2 tutorial class can use **single teacher profile**, this becomes powerful:

### teacher profile idea

FFmpeg + cloned voice + old recording

You can:

* take any old tutorial
* auto create new narration
* reuse same visuals
* publish as fresh lesson

That reduces huge manual work for [PlayOwnAi](https://www.youtube.com/@PlayOwnAi?utm_source=chatgpt.com).

---

# My suggestion for CF2

Add a new optional unit:

### `Unit-ReDub`

Not full video generation. Just transformation unit.

```text
Unit-ReDub
    input  → existing video
    input  → script text
    input  → speaker sample
    output → dubbed video
```

Good because future uses:

✅ old tutorial refresh
✅ translate English → Bangla
✅ classroom teacher avatar
✅ hologram teacher playback
✅ bulk YouTube content remake

---

# Fastest test now (today)

You can test immediately:

```bash
python test_redub.py \
  --video /home/matin/Desktop/_Classes_Objects.mp4 \
  --voice samples/me.wav \
  --script script.md
```

If you want, I can design the **exact CF2-compliant file structure + unit/service plan for `Unit-ReDub`** (same style as your previous hologram service planning, no code).


Based on your existing architecture, here's the full design:

---

## `Unit-Dubbing` — Design Proposal

---

### Responsibility
Replace or dub audio in an existing video using cloned or TTS voice. Follows CF2 rules exactly.

---

### Pipeline (4 SubUnits)

```
Unit-Dubbing
├─▶ subUnitTranscribe     → Whisper → script.txt (skip if script exists)
├─▶ subUnitSynthesize     → XTTS / Edge TTS → dubbed.mp3
├─▶ subUnitSync           → atempo align dubbed.mp3 to video duration
└─▶ subUnitMerge          → strip original audio + merge dubbed.mp3 → final.mp4
```

---

### Workspace Structure
```
output/{TopicSlug}/
  dubbing/
    script.txt          ← subUnitTranscribe writes this
    dubbed.mp3          ← subUnitSynthesize writes this
    dubbed_synced.mp3   ← subUnitSync writes this
    dubbed_final.mp4    ← subUnitMerge writes this
    .lock
```

---

### Config Block (in `data.json`)
```json
"Unit-Dubbing": true,
"dubbing_config": {
  "source_video": "/home/matin/Desktop/_Classes_Objects.mp4",
  "script_path": "",
  "tts_engine": "xtts",
  "voice_clone_config": {
    "speaker_wav": "assets/voices/matin.wav",
    "language": "en",
    "device": "cpu",
    "use_cache": true
  },
  "sync_mode": "atempo",
  "keep_bgm": false,
  "bgm_volume": 0.15,
  "video_formats": ["HD"]
}
```

---

### Services Used (all existing)

| SubUnit | Calls |
|---|---|
| subUnitTranscribe | `whisper` (new, ~5 lines) |
| subUnitSynthesize | `xtts_service.synthesize_xtts()` ✅ exists |
| subUnitSync | `AudioService.apply_atempo()` ✅ exists |
| subUnitMerge | `AudioService.merge_audio_video()` ✅ exists |

---

### Smart Skip (Rule 24)
```
script.txt exists      → skip subUnitTranscribe
dubbed.mp3 exists      → skip subUnitSynthesize  
dubbed_synced.mp3      → skip subUnitSync
dubbed_final.mp4       → skip subUnitMerge (entire unit done)
```

---

### Key Design Decisions

**1. `script_path` in config** — if you already have the transcript, Whisper is skipped entirely. No wasted compute.

**2. `sync_mode: atempo`** — cloned voice will never match original timing exactly. `AudioService.apply_atempo()` stretches/compresses dubbed audio to fit video duration. Already exists in your codebase.

**3. `keep_bgm`** — optionally mix background music under the dubbed voice using `FFmpegService.mix_bgm()`. Already exists.

**4. Sentence chunking** — for long videos, `TTSService.split_sentences()` chunks the script before synthesis to avoid XTTS memory issues. Already exists.

---

### What's New (only 2 things)

1. **Whisper transcription** — ~10 lines using `openai-whisper` pip package
2. **`unit_dubbing.py`** — the orchestrator, ~120 lines following `unit_prodcast.py` pattern exactly

Everything else — XTTS, atempo, merge, smart skip, lock, meta — is already in your codebase.

---

Want me to build `unit_dubbing.py` now?


## `Unit-Dubbing` — Full Plan

---

### Architecture
```
unit_dubbing.py (Router)
├─▶ subUnitTranscribe   → Whisper → script.txt
├─▶ subUnitSynthesize   → XTTS/Edge → dubbed.mp3
├─▶ subUnitSync         → atempo align → dubbed_synced.mp3
└─▶ subUnitMerge        → strip + merge → dubbed_final.mp4
```

---

### Rules Compliance

| Rule | How |
|---|---|
| R4 One responsibility | Dubbing only, never touches Unit-Data outputs |
| R6 No data creation | Reads source video, writes only to `dubbing/` |
| R14 Smart Skip | Each subUnit checks output file before running |
| R17 50-80 lines/fn | 4 small subUnit functions + 1 orchestrator |
| R19 No hardcoding | All paths/voices/engine from `dubbing_config` |
| R24 Skip mandatory | `dubbed_final.mp4` exists → entire unit skips |

---

### Workspace
```
output/{TopicSlug}/
  dubbing/
    script.txt          ← Whisper output (skip if provided)
    script_chunks/      ← per-sentence mp3s (long video support)
    dubbed.mp3          ← full synthesized audio
    dubbed_synced.mp3   ← atempo adjusted
    dubbed_final.mp4    ← final deliverable
```

---

### Config
```json
"Unit-Dubbing": true,
"dubbing_config": {
  "source_video": "path/to/video.mp4",
  "script_path": "",
  "tts_engine": "xtts",
  "sync_mode": "atempo",
  "keep_bgm": false,
  "bgm_volume": 0.15,
  "voice_clone_config": {
    "speaker_wav": "assets/voices/matin.wav",
    "language": "en",
    "device": "cpu",
    "use_cache": true
  }
}
```

---

### Existing Services Reused

| SubUnit | Service | Status |
|---|---|---|
| Transcribe | `openai-whisper` | 🆕 new (~10 lines) |
| Synthesize | `xtts_service.synthesize_xtts()` | ✅ exists |
| Synthesize (fallback) | `TTSService.generate_edge()` | ✅ exists |
| Chunk long scripts | `TTSService.split_sentences()` | ✅ exists |
| Sync timing | `AudioService.apply_atempo()` | ✅ exists |
| Merge AV | `AudioService.merge_audio_video()` | ✅ exists |
| Optional BGM | `FFmpegService.mix_bgm()` | ✅ exists |

---

### Decision Tree at Runtime
```
source_video exists?        → NO  → FAIL early
script_path provided?       → YES → skip Whisper
dubbed_final.mp4 exists?    → YES → skip entire unit
tts_engine = xtts?          → YES → synthesize_xtts
                            → NO  → generate_edge (fallback)
video duration > dubbed?    → YES → apply_atempo to stretch
keep_bgm = true?            → YES → mix_bgm under dubbed audio
```

---

### What Needs Building

| File | Lines | Priority |
|---|---|---|
| `unit_dubbing.py` | ~120 | Core |
| `tools/dubbing_transcribe.py` | ~40 | New (Whisper wrapper) |
| `tools/dubbing_synthesize.py` | ~50 | Thin wrapper over xtts_service |
| `tools/dubbing_merge.py` | ~40 | Thin wrapper over AudioService |

**Total new code: ~250 lines. Everything else reused.**

---

### Open Questions Before Building

1. **Script available?** — If yes, Whisper skipped entirely, much faster
2. **XTTS or Edge?** — XTTS needs GPU ideally; Edge TTS is fast but not cloned voice
3. **Multi-language?** — XTTS supports it via `language` param, Edge needs different voice ID
4. **Sentence-level sync?** — Advanced: align each sentence chunk to original timestamps vs simple full-audio atempo
