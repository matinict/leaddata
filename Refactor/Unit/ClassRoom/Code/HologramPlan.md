Here’s a **CF2-compliant implementation plan document** for your plugin idea — written to fit your current architecture (Flow → Unit → SubUnit), without breaking Rule 4 (unit isolation) and Rule 19 (no hardcoded paths).

I used your existing CF2 structure from `src/cf2` and the asset layout shown in your project tree (`assets/clips/...`).

---

# CF2 Plugin Plan — `Unit-Classroom` Hologram Overlay Integration

## Goal

Convert old tutorial recordings (e.g. PyCharm screen captures) into reusable **in-classroom hologram overlays** inside your KidfyCode pipeline, without creating a separate preprocessing pipeline.

This extends your existing classroom renderer by adding a **new overlay type**, not a new standalone unit.

---

# 1. Architectural Decision (CF2 Rule Alignment)

## ✅ Correct CF2 Placement

**Add feature inside:**

`src/cf2/core/render/overlay/`

New plugin file:

```text
src/cf2/core/render/overlay/hologram_overlay.py
```

Reason:

* overlay = rendering concern
* no business logic
* reusable across future units
* obeys Rule 3: SubUnit = reusable micro-task
* obeys Rule 4: file-based communication only

---

# 2. Plugin Scope

## Plugin Name

`subUnitHologramOverlay`

## Responsibility

Single responsibility only:

> Transform one raw tutorial clip into one live FFmpeg hologram stream and composite into current scene.

It must NOT:

❌ extract clips
❌ parse script
❌ choose timestamps
❌ decide scene logic

Those remain in `Unit-Classroom`.

---

# 3. Folder Design (Rule 19 Safe)

Add new source folder:

```text
assets/
└── old_tutorials/
    └── python_basics/
        ├── arithmetic_operators_raw.mp4
        ├── for_loop_raw.mp4
        └── list_methods_raw.mp4
```

Add extracted reusable clips:

```text
assets/
└── clips/
    └── tutorial_holo/
        ├── for_loop_code.mp4
        ├── for_loop_terminal.mp4
        └── arithmetic_terminal.mp4
```

---

# 4. Config Extension

Update your profile config (`kidifycode.json`).

## Add Section

```json
"classroom_config": {
  "clip_overlay_mode": "floating_hologram",
  "old_video_reuse": true,
  "hologram_opacity": 0.82,
  "hologram_color": "cyan",
  "hologram_default_position": "floating_right"
}
```

---

# 5. Scene Contract

Scene script should remain file-driven.

## Example

```markdown
[PHASE:show_code]
[T1] Teacher: Watch the code hologram.

[OVERLAY]
type=hologram_code
clip=for_loop_code.mp4
position=floating_right
duration=8
```

This keeps script readable and parser-simple.

---

# 6. Required SubUnits

## A. `subUnitClipExtractor`

File:

```text
src/cf2/tools/extract_hologram_source.py
```

Purpose:

Extract reusable cropped source clips.

### Input

* raw old tutorial
* timestamp
* crop preset

### Output

* clip file

---

## B. `subUnitHologramOverlay`

File:

```text
src/cf2/core/render/overlay/hologram_overlay.py
```

Purpose:

Apply live FFmpeg hologram effect.

### Input

* base classroom scene
* source clip
* placement config

### Output

* composited segment

---

# 7. Implementation Phases

---

# Phase A — Asset Preparation

### Task

Convert old tutorials into micro-clips.

### Recommended duration

Each source:

| Type          | Length   |
| ------------- | -------- |
| code clip     | 6–10 sec |
| terminal clip | 4–8 sec  |

### Output

```text
assets/clips/tutorial_holo/
```

---

# Phase B — Overlay Engine

Create plugin:

### File

```python
src/cf2/core/render/overlay/hologram_overlay.py
```

### Public API

```python
render_hologram_overlay(
    base_scene: str,
    clip_path: str,
    output_path: str,
    position: str,
    duration: float
)
```

---

# Phase C — Classroom Renderer Hook

Modify:

```text
src/cf2/core/render/frame_renderer.py
```

Register overlay:

```python
OVERLAY_TYPES = {
    "dialogue_bubble": render_bubble,
    "topic_overlay": render_topic,
    "hologram_code": render_hologram_overlay,
    "hologram_terminal": render_hologram_overlay
}
```

---

# 8. Recommended Python Plugin

Create:

```python
# src/cf2/core/render/overlay/hologram_overlay.py

import subprocess
from pathlib import Path


POSITIONS = {
    "floating_right": (980, 120),
    "center_projector": (560, 180),
    "terminal_small": (1080, 300),
}


def render_hologram_overlay(
    base_scene,
    clip_path,
    output_path,
    position="floating_right",
    start=0,
    dur=8
):
    x, y = POSITIONS[position]

    filter_graph = f"""
    [1:v]fps=30,
         scale=800:450,
         format=rgba,
         negate,
         colorchannelmixer=rr=0.1:gg=0.8:bb=1.5:aa=0.80,
         perspective=x0=0:y0=15:x1=800:y1=0:x2=800:y2=450:x3=0:y3=435,
         drawbox=x=2:y=2:w=iw-4:h=ih-4:color=cyan@0.6:thickness=3,
         boxblur=2:1[holo];

    [0:v][holo]overlay={x}:{y}:enable='between(t,{start},{start+dur})'
    """

    cmd = [
        "ffmpeg", "-y",
        "-i", base_scene,
        "-i", clip_path,
        "-filter_complex", filter_graph.replace("\n", " "),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        output_path
    ]

    subprocess.run(cmd, check=True)
```

---

# 9. Metadata Integration

Update `meta.json`:

```json
"hologram_assets": {
  "for_loop_code": "done",
  "for_loop_terminal": "done"
}
```

This enables Smart Skip.

Matches Rule 24.

---

# 10. Best Rollout Strategy

## Start Small

Use only 1 topic first:

### Recommended test

Your existing Python basics videos:

* arithmetic operators
* for loop
* list methods

These are perfect for KidfyCode.

---

# 11. Final CF2 Plugin Layout

```text
src/cf2/
├── core
│   └── render
│       └── overlay
│           ├── subtitle_overlay.py
│           ├── topic_overlay.py
│           └── hologram_overlay.py   ✅ new
│
├── tools
│   └── extract_hologram_source.py    ✅ new
│
assets
└── clips
    └── tutorial_holo                 ✅ new
```

---

# 12. Recommendation for Your Project

Since your channel is [PlayOwnAi YouTube channel](https://www.youtube.com/@PlayOwnAi?utm_source=chatgpt.com) and you’re moving toward AI teaching content, this approach is strong because it lets you reuse your old tutorial recordings instead of re-recording manually.

For your **KidfyCode** content, this gives:

✅ fast production
✅ no new recording cost
✅ cinematic style
✅ fits your CF2 modular rules
✅ reusable clips library
✅ can scale into 30+ lessons

---

# Suggested next build order

### Sprint 1

* create clip extractor
* extract 3 old videos
* manual timestamps
* test hologram overlay

### Sprint 2

* integrate script tag parser
* automate scene insertion
* add terminal-only crop mode

### Sprint 3

* build clip auto-selector by lesson topic
* fully automatic KidfyCode classroom pipeline

---

If you want, I can also generate the **actual CF2-ready code files** for:

1. `hologram_overlay.py`
2. `extract_hologram_source.py`
3. `kidifycode.json` schema extension

as a ready-to-paste package matching your current `src/cf2` tree.
