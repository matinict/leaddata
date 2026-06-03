
---

# CF2 Final Plan — Hologram Service

## Purpose

The Hologram feature turns any external or archived video (local file, URL, or YouTube source) into reusable stylized visual overlays (floating screen / projector / panel) that any unit can use:

* `Unit-Classroom`
* `Unit-Podcast`
* `Unit-Definition`
* `Unit-Debate`

This is a **CF2 platform feature**, so it belongs in shared services.
"hologram": {
  "enabled": true,
  "type" : 1

}

Hologram Type:
1. Original Video crops transcript
  From your recorded tutorial:
      spoken words
      explanations
      examples
      pauses
2. Screen OCR / code text
    From visible screen:
    code snippets
    output text
    menu labels
    terminal

---

# 1. Core Service File Structure

Your current service folder:

```text
src/cf2/core/services/
```

Add:

```text
src/cf2/core/services/
├── audio_service.py
├── ffmpeg_service.py
├── tts_service.py
└── hologram.py   ← NEW _service that already inside services directory
```

---

# 2. Why `hologram.py`

Because this matches your existing architecture:

* `audio_service` → shared audio processing
* `tts_service` → shared voice generation
* `ffmpeg_service` → shared low-level rendering
* `hologram_service` → shared hologram media transformation

### Responsibility

Single purpose:

> Resolve source → prepare runtime clips → provide overlay-ready media

It should **not** contain unit logic.

---

# 3. Runtime Storage (Generated)

All generated hologram files must go under topic runtime.

## Final path

```text
.runtime/output/{TopicSlug}/_runtime_media/hologram/
```

Example:

```text
.runtime/output/PythonForKids/_runtime_media/hologram/
├── manifest.json
├── source_raw_001.mp4
├── clip_code_001.mp4
├── clip_terminal_001.mp4
├── clip_overlay_001.mp4
└── cache/
```

---

# 4. Why `_runtime_media/hologram`

Reason:

Your `.runtime/output/{slug}` already acts as isolated topic workspace.

Hologram is not owned by one unit, so it must stay outside:

❌ `classroom/`
❌ `podcast/`

Use shared:

✅ `_runtime_media/hologram`

This makes every unit able to access it.

---

# 5. Input Config Design

Hologram sources should be declared in profile config.

## Suggested config location

```text
input/profile/{channel}.json
```

Reason:

This matches your existing channel-specific behavior and allows different channels to enable or disable hologram usage.

---

# 6. Config Section

Add new profile section:

```json
"hologram": {
  "enabled": true,
  "sources": [...]
}
```

---

# 7. Source Types Supported

The service should accept multiple source types.

## A. Local source

Archived tutorials

Example:

```text
assets/archive_tutorials/python/for_loop.mp4
```

## B. URL source

Direct downloadable mp4

Example:

```text
https://site.com/demo.mp4
```

## C. YouTube source

Public/unlisted tutorial clips

Example:

```text
https://youtube.com/watch?v=...
```

---

# 8. Source Lifecycle

## Step 1

Profile config declares source.

## Step 2

`hologram_service` resolves source.

## Step 3

Source normalized into runtime folder.

## Step 4

Source cropped into micro-clips.

## Step 5

Units consume resulting clips.

---

# 9. Internal Tasks of `hologram.py`

This service should handle **five tasks only**.

---

## Task A — Source Resolver

Purpose:

Resolve input source path.

Handles:

* local file
* URL
* YouTube

Output:

normalized local runtime file.

---

## Task B — Clip Extractor

Purpose:

Create reusable short clips.

Examples:

* code only
* terminal only
* output section

These are reusable per topic.

---

## Task C — Hologram Builder

Purpose:

Apply visual transformation.

Modes:

* floating hologram
* projector
* glass panel

This layer uses FFmpeg internally.

---

## Task D — Manifest Manager

Purpose:

Track created clips.

File:

```text
manifest.json
```

Stores:

* source id
* derived clips
* timestamps
* cache state

This enables smart skip.

---

## Task E — Consumer Resolver

Purpose:

Provide path to units.

Example:

Classroom asks:

> give me hologram clip for `python_loop`

Service returns:

```text
.runtime/output/.../clip_code_001.mp4
```

---

# 10. Suggested Folder Structure (Full)

## Source Assets

Permanent human archive:

```text
assets/
└── archive_tutorials/
    ├── python/
    ├── ai/
    └── coding/
```

---

## Runtime Generated

Per topic:

```text
.runtime/output/{TopicSlug}/_runtime_media/hologram/
├── manifest.json
├── source/
├── clips/
├── overlays/
└── cache/
```

---

# 11. Detailed Folder Reason

---

## `source/`

Stores normalized original media.

Example:

* downloaded YouTube clip
* copied local file
* fetched URL

Reason:

Keep raw source immutable.

---

## `clips/`

Stores extracted semantic clips.

Examples:

* code segment
* terminal segment
* output moment

Reason:

These are reusable chunks.

---

## `overlays/`

Stores pre-rendered optional hologram overlays.

Only if you cache rendered effect.

Reason:

speed optimization.

---

## `cache/`

Stores metadata.

Examples:

* timestamps
* hashes
* downloaded info

Reason:

skip repeated work.

---

# 12. Service Interaction Flow

## Universal flow

```text
Profile config
     ↓
HologramService
     ↓
Runtime media generation
     ↓
Any Unit consumes
```

---

# 13. Unit Usage

These units can call the same service.

---

## Classroom

Use as teaching panel.

---

## Podcast

Use as visual B-roll.

---

## Definition

Use as concept demonstration.

---

## Debate

Use as evidence clip.

---

# 14. Future Extensions

This architecture supports later features.

Examples:

* projector mode
* split-screen
* smartboard
* transparent phone screen
* TV frame overlay

Same service.

---

# 15. Suggested Minimal API

No implementation, only conceptual:

```python
HologramService.prepare(...)
HologramService.resolve(...)
```

Enough.

---

# 16. Final Best Design (Recommended)

## Keep exactly this

### Service file

```text
src/cf2/core/services/hologram.py
```

### Runtime path

```text
.runtime/output/{TopicSlug}/_runtime_media/hologram/
```

### Config source

```text
input/profile/{channel}.json
```

### Permanent sources

```text
assets/archive_tutorials/
```

---

# Final Architecture Summary

```text
CF2
├── input/profile/
│   └── kidifycode.json
│
├── assets/archive_tutorials/
│
├── src/cf2/core/services/
│   └── hologram.py
│
└── .runtime/output/{TopicSlug}/
    └── _runtime_media/
        └── hologram/
```

---

# Why this is the best fit for your CF2

It respects your current real system:

✅ topic workspace pattern
✅ service pattern
✅ shared feature design
✅ no unit coupling
✅ reusable across all channels
✅ future-proof for more media features

For your project, this is the strongest long-term implementation path.



That’s the right direction for CF2.

You’re describing a feature that behaves like the existing speech bubble system, but instead of tiny text bubbles, the teacher can display a **large floating tutorial screen** (your old recorded screen videos) during explanation. That means:

* enabled/disabled from profile config
* input clip comes from source config
* renderer injects it when scene asks
* reusable across any unit later
* generated files stay in `.runtime`

This is a strong fit as a shared service.

---

# Final CF2 Plan — Hologram Teaching Screen Feature

## Core idea

Teacher can “present” a real tutorial clip inside scene.

Examples:

* Python code recording
* Terminal execution
* Browser demo
* Old tutorial footage

Rendered as:

* floating classroom screen
* projector board
* hologram panel

---

# Folder Structure

## Shared service

```text
src/cf2/core/services/
└── hologram_service.py
```

### Why

Shared system-level media transformation service.

Same layer as:

* audio service
* tts service
* ffmpeg service

Because hologram is media-processing infrastructure.

---

# Runtime output

All generated hologram files:

```text
.runtime/output/{TopicSlug}/_runtime_media/hologram/
```

### Final structure

```text
.runtime/output/{TopicSlug}/_runtime_media/hologram/
├── manifest.json
├── source/
├── clips/
├── renders/
└── cache/
```

---

# Folder purpose

## 1. `source/`

Original normalized source clips.

Stores:

* local copied videos
* downloaded URL videos
* downloaded YouTube videos

Reason:

Keep immutable original source.

---

## 2. `clips/`

Scene-ready extracted segments.

Examples:

* code part
* terminal part
* demo part

Reason:

One long tutorial becomes reusable micro-clips.

---

## 3. `renders/`

Optional processed outputs.

Examples:

* hologram overlay version
* projector version
* flat screen version

Reason:

cache expensive ffmpeg processing.

---

## 4. `cache/`

Internal metadata.

Examples:

* hashes
* download status
* timestamps

Reason:

smart skip.

---

# Config design

Use profile config like your bubble system.

Location:

```text
input/profile/{channel}.json
```

---

# Config section

Example structure:

```json
{
  "hologram": {
    "enabled": true,
    "default_style": "floating_screen",
    "sources": []
  }
}
```

---

# Source config design

Each source entry defines where the teacher clip comes from.

---

## Supported source types

### local

Your own archived recording.

Example:

```json
{
  "id": "python_math",
  "source_type": "local",
  "source_path": "assets/archive_tutorials/python/math.mp4"
}
```

---

## url

Direct downloadable video.

Example:

```json
{
  "id": "remote_demo",
  "source_type": "url",
  "source_path": "https://example.com/demo.mp4"
}
```

---

## youtube

Public/unlisted YouTube.

Example:

```json
{
  "id": "yt_demo",
  "source_type": "youtube",
  "source_path": "https://youtube.com/watch?v=abc"
}
```

---

# Scene integration

Just like bubble scenes, but bigger visual asset.

---

## Scene tag example

Your generated script can contain:

```text
[PHASE:show_code]
[HOLOGRAM:python_math]
Teacher: Watch the code on the smart screen.
```

---

# Service tasks

`hologram_service.py` should do only these tasks.

---

## Task 1 — Resolve source

Input:

source config

Output:

local runtime video path

Reason:

all source types become local file.

---

## Task 2 — Normalize source

Converts source to CF2 standard:

* mp4
* fps normalized
* size normalized

Reason:

units don’t handle source inconsistency.

---

## Task 3 — Extract segments

Cuts source into usable chunks.

Examples:

* intro code
* result output
* explanation part

Reason:

avoid using whole long recording.

---

## Task 4 — Prepare overlay asset

Creates render-ready panel clip.

Style:

* hologram
* projector
* flat display

Reason:

teacher scene simply consumes final asset.

---

## Task 5 — Manifest tracking

Stores metadata.

File:

```text
manifest.json
```

Tracks:

* source id
* runtime paths
* extracted clips
* cached renders

Reason:

skip regeneration.

---

# Unit-Classroom behavior

When enabled:

Teacher can show hologram screen.

Without hologram:

Teacher uses normal bubble.

With hologram:

Teacher uses large teaching panel.

---

# Size behavior

Unlike bubble:

### bubble

small dialogue UI

### hologram

large instructional media screen

Typical screen:

* 35–60% of frame width
* positioned right or center

This matches your need.

---

# Why this is better than making new unit

Because hologram is not content generator.

It is only:

> media augmentation service

So:

❌ not `Unit-Hologram`
✅ shared service

---

# Recommended permanent source folder

Your old tutorial archive:

```text
assets/archive_tutorials/
├── python/
├── ai/
├── coding/
└── automation/
```

Reason:

human-maintained raw source library.

---

# End-to-end flow

```text
Old screen recording
        ↓
Profile config source
        ↓
HologramService
        ↓
.runtime/_runtime_media/hologram
        ↓
Unit-Classroom consumes
        ↓
Teacher shows big hologram screen
```

---

# Final architecture summary

```text
CF2
├── assets/
│   └── archive_tutorials/
│
├── input/profile/
│   └── kidifycode.json
│
├── src/cf2/core/services/
│   └── hologram_service.py
│
└── .runtime/output/{TopicSlug}/
    └── _runtime_media/
        └── hologram/
```

---

# Minimal conceptual sample

Only 2 lines as requested:

```python
service.prepare(topic_slug, hologram_config)
service.resolve("python_math")
```

That’s enough abstraction for CF2.

---

This design fits your Rule 19 (no hardcoded paths) and Rule 39 (`.runtime` system-only) from your uploaded CF2 rules file.Now I have a clear picture of your plan. You want a `HologramService` that displays screen-recorded tutorials as a **large floating hologram panel** in the classroom — like a big bubble/overlay the teacher uses to show video clips. Let me build both the service module and a visual demo of how it looks.Now let me generate the actual `hologram.py` service file:Here's what was built and how it all fits together:

**The interactive demo above** shows exactly how it looks in the classroom — a large floating hologram panel (not a tiny bubble) with the teacher avatar and three switchable clip types: code segment, terminal output, and overlay result. You can also toggle between the three display modes (floating panel, projector, glass panel).

**The `hologram.py` service** implements all five tasks from your plan:

**Task A — Source Resolver** handles all three input types: local `assets/archive_tutorials/` files, direct URLs, and YouTube links (via `yt-dlp`).

**Task B — Clip Extractor** cuts the source into semantic clips — code, terminal, and overlay segments — using FFmpeg. The split is time-based by default, but you can extend it with scene-change detection later.

**Task C — Hologram Builder** applies the visual mode via FFmpeg filter chains. The `floating_panel` mode adds a cyan tint, brightness lift, and vignette — giving that signature hologram look.

**Task D — Manifest Manager** tracks every clip with cache hashing so it skips re-processing if the source hasn't changed.

**Task E — Consumer Resolver** is `service.resolve(topic_slug, ClipType.CODE, source_id)` — any unit (Classroom, Podcast, Definition, Debate) calls this one method to get their clip path.

**To wire it into a unit from config:**
```python
enabled, sources = load_hologram_sources_from_profile(Path("input/profile/kidifycode.json"))
if enabled:
    service.prepare(topic_slug, sources, mode=HologramMode.FLOATING_PANEL)
    clip = service.resolve(topic_slug, ClipType.CODE, source_id="src_001")
```
