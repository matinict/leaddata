# CF2 — Hologram Service Plan

> **One-line purpose:** Turn any archived or external video into a reusable, stylized teaching panel consumable by any CF2 unit.

---

## What It Is

Hologram is a **shared platform service** — not a unit. It does media transformation only. No business logic, no CrewAI, no content generation. It sits alongside `audio_service`, `tts_service`, and `ffmpeg_service`.

❌ `Unit-Hologram` — wrong layer  
✅ `src/cf2/core/services/hologram.py` — correct layer

---

## Who Uses It

| Unit | How |
|---|---|
| Unit-Classroom | Large floating teaching panel |
| Unit-Podcast | Visual B-roll |
| Unit-Definition | Concept demonstration clip |
| Unit-Debate | Evidence clip overlay |

All units call the same two methods. The service handles everything else.

---

## Full File Structure

```text
CF2
├── assets/
│   └── archive_tutorials/          ← any "hologram": {any paths defined }permanent human-maintained source library
│       ├── python/
│       ├── ai/
│       ├── coding/
│       └── automation/
│
├── input/profile/
│   └── {channel}.json              ← hologram config declared per channel {
            "hologram": {    "enabled": true,    "default_style": "floating_screen",    "sources": []  }
}
│
├── src/cf2/core/services/
│   ├── audio_service.py
│   ├── ffmpeg_service.py
│   ├── tts_service.py
│   └── hologram.py         ← NEW (fits existing service pattern)
│
└── .runtime/output/{TopicSlug}/
    └── _runtime_media/
        └── hologram/
            ├── manifest.json       ← smart skip tracker
            ├── source/             ← normalized original media (immutable)
            ├── clips/              ← extracted semantic micro-clips
            ├── renders/            ← pre-rendered overlay versions (cache)
            └── cache/              ← hashes, download status, timestamps
```



Why `_runtime_media/hologram` and not inside a unit folder: hologram output is not owned by any single unit. Keeping it under `_runtime_media/` lets every unit read it without cross-unit coupling.

---

## Config

Declared in the channel profile, alongside existing channel config:

```json
"hologram": {
  "enabled": true,
  "default_style": "floating_screen",
  "sources": [
    {
      "id": "python_loops",
      "source_type": "local",
      "source_path": "assets/archive_tutorials/python/loops.mp4"
    },
    {
      "id": "remote_demo",
      "source_type": "url",
      "source_path": "https://example.com/demo.mp4"
    },
    {
      "id": "yt_tutorial",
      "source_type": "youtube",
      "source_path": "https://youtube.com/watch?v=abc123"
    }
  ]
}

#or 
"hologram": {
  "enabled": true,
  "mode": "floating",
  "size": "1280x720",
  "sources": [
    {
      "id": "old_screen_tutorial",
      "type": "local",
      "path": "assets/archive_tutorials/python/for_loop_screenrecord.mp4",
      "clips": [
        {"id": "loop_demo", "start": "00:00:05", "end": "00:00:22"},
        {"id": "output_demo", "start": "00:01:10", "end": "00:01:30"}
      ]
    }
  ]
}

```

**Source types:** `local` · `url` · `youtube` — all resolve to a local runtime file before any further processing.

---

## Service Lifecycle (One Pass Per Topic)

```text
Profile config declares sources
         ↓
Task A: Resolve — local copy / URL download / yt-dlp
         ↓
Task B: Normalize — re-encode to CF2 standard (mp4, fixed fps, fixed size)
         ↓
Task C: Extract — cut into semantic micro-clips (code / terminal / demo)
         ↓
Task D: Render — apply visual style via FFmpeg (hologram / projector / flat)
         ↓
Task E: Manifest — write manifest.json, enable smart skip on next run
         ↓
Unit consumes clip via service.resolve(...)
```

Smart skip: if `manifest.json` hash matches source hash, steps A–D are skipped entirely. Only step E re-confirms paths.

---

## Five Internal Tasks

### Task A — Source Resolver
Resolves source config to a local file path. Handles `local` (file copy), `url` (HTTP download), `youtube` (yt-dlp). Output lands in `source/`.

### Task B — Normalizer
Re-encodes source to CF2 standard via FFmpeg: mp4 container, 30fps, 1920×1080 or 1080×1920. Prevents every downstream consumer from handling codec inconsistency.

### Task C — Clip Extractor
Cuts the normalized source into semantic micro-clips and writes them to `clips/`. Segments are defined in config (time ranges or scene labels). One long recording becomes many reusable chunks.

```json
"segments": [
  { "id": "code_intro",  "start": "00:00", "end": "01:30" },
  { "id": "terminal",    "start": "01:30", "end": "02:45" },
  { "id": "result",      "start": "02:45", "end": "03:20" }
]
```

### Task D — Hologram Builder
Applies the visual style FFmpeg filter chain. Output goes to `renders/`.

| Style | Effect |
|---|---|
| `floating_screen` | Cyan tint, brightness lift, soft vignette |
| `projector` | Warm tone, mild grain, corner darkening |
| `glass_panel` | Desaturated, frosted edge blur, high contrast |

### Task E — Manifest Manager
Writes and reads `manifest.json`. Stores source hash, clip paths, render paths, and timestamps. Powers smart skip — if source is unchanged, the service returns cached paths immediately.

---

## Public API (Two Methods Only)

```python
# Called once per topic — prepares all clips from config
service.prepare(topic_slug, hologram_config)

# Called by any unit — returns path to the requested clip
clip_path = service.resolve(topic_slug, source_id="python_loops", segment_id="code_intro")
```

Units never touch `source/`, `clips/`, `renders/`, or `manifest.json` directly.

---

## Scene Script Integration

Scene scripts can trigger hologram display with a tag:

```text
[PHASE:explain_loops]
[HOLOGRAM:python_loops:code_intro]
Teacher: Watch the loop run on the screen behind me.
```

The renderer reads the `[HOLOGRAM:id:segment]` tag, calls `service.resolve(...)`, and composites the clip into the frame at the configured position and size.

**Size:** 35–60% of frame width. Positioned right or center. Distinct from speech bubbles (small dialogue UI) — this is a large instructional panel.

---

## Rules Alignment

| CF2 Rule | How Hologram Respects It |
|---|---|
| Rule 19 — no hardcoded paths | All paths derived from `TopicSlug` and profile config |
| Rule 39 — `.runtime` is system-only | All generated files stay under `.runtime/output/{slug}/_runtime_media/` |
| Smart skip (meta.py pattern) | `manifest.json` hash check mirrors the existing config fingerprint approach |
| Shared service pattern | Same layer as `audio_service`, `tts_service`, `ffmpeg_service` |
| No unit coupling | Units call only `service.resolve()` — no direct file access |

---

## Future Extensions

The service contract (`prepare` / `resolve`) is stable regardless of new modes. Extensions are additive only:

- Smartboard mode (annotation overlay)
- Split-screen (two clips side by side)
- Transparent phone screen composite
- TV frame overlay
- Scene-change-based auto-segmentation (replaces manual time ranges)

No unit changes required when new modes are added — only the service internals change.
