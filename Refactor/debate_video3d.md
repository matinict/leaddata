 

# ❌ PRINCIPLE VIOLATIONS debate_video3d.py

## 1. ❌ Single Responsibility Violation

**Problem:**
`debate_video3d.py` is doing EVERYTHING:

* parsing debate text
* TTS generation
* video rendering
* subtitle generation
* pipeline orchestration
* config handling

👉 One file = 1000+ lines monster

**Why bad:**
Hard to debug, impossible to reuse, breaks modular flow design.

---

## 2. ❌ Flow Controller Violation (Core Rule Broken)

From r plan:

> “FlowController controls execution”

**But reality:**

* `_build_pipeline_order()` exists inside tool
* execution logic inside tool
* sequencing logic inside tool

👉 Tool is acting like FlowController

---

## 3. ❌ Dumb Tool Principle Violation

Rule:

> Tools should be simple executors

**But current tool:**

* decides pipeline
* decides voices
* decides intro fallback
* decides missing clip behavior
* handles smart skip logic partially

👉 Tool = Smart Brain ❌
👉 Should be = Dumb Executor ✅

---

## 4. ❌ Config Ownership Violation

Config should be controlled centrally (Flow / meta system)

But inside tool:

* reads `debate_config`
* reads `clip_config`
* reads `video_formats`
* resolves intro logic

👉 Logic is **scattered + duplicated**

---

## 5. ❌ Reusability Violation

Everything tightly coupled:

* `_tts_edge()` cannot be reused
* subtitle system locked inside tool
* overlay logic locked inside tool

👉 No reusable modules like:

* `tts_engine.py`
* `subtitle_builder.py`
* `video_renderer.py`

---

## 6. ❌ Data vs Execution Mixing

From plan:

> Unit-Data = ONLY generator

But here:

* parsing `.md`
* generating derived structure
* consuming it immediately

👉 No clean boundary between:

* data generation
* data consumption

---

## 7. ❌ Smart Skip Duplication

 already built:

* `meta.py` smart skip system

But tool also does:

```python
if final_output.exists():
    skip
```

👉 Duplicate logic → inconsistent behavior

---

## 8. ❌ Hardcoded Pipeline Violation

```python
p0, c0, p1, c1 ...
```

👉 Fixed structure inside tool

**Problem:**

* Not config-driven
* Not scalable (HD vs Shorts hacky)

---

## 9. ❌ Hidden Side Effects

Tool creates:

* audio files
* subtitle files
* temp chunks
* logs

👉 No clear contract of outputs

---

## 10. ❌ File-System Coupling

Tool assumes:

```
output/{topic}/debate/
```

👉 Violates rule from `meta.py`:

> “Tool must not derive paths from topic”

---

## 11. ❌ Over-Defensive Logic (Symptom of Bad Design)

Examples:

* intro fallback logic
* missing clip fallback
* silent audio generation

👉 These belong to:

* FlowController OR config validation layer

---

## 12. ❌ Pipeline + Rendering Mixed

Inside same loop:

* timeline calculation
* clip reading
* overlay drawing
* frame writing

👉 No separation:

* timeline engine
* renderer
* overlay system

---

# ⚠️ ROOT PROBLEM (Important)

Everything points to **ONE core violation:**

> ❌  built a “God Tool” instead of a “Flow System”

---

# ✅ WHAT IT SHOULD BE

Instead:

### FlowController

* decides pipeline
* passes clean instructions

### Tool (debate_video3d)

* ONLY executes:

  * given clips
  * given audio
  * given timeline

👉 No decisions
👉 No intelligence
👉 Just execution

---

# 🔥 SIMPLE SUMMARY

r system violates:

1. Separation of Concerns
2. Dumb Tool Principle
3. Flow Control Ownership
4. Reusability
5. Config Centralization

---

Refactor Plan
========================



Good — this structure is already **80% correct**.  don’t need a rewrite,  need **surgical refactor + relocation + responsibility cleanup**.

I’ll map r **current structure → exact refactor actions** (no theory, only what to change).

---

# 🎯 CORE PROBLEM (IN R CURRENT STRUCTURE)

 already *created modular folders*, but:

👉 Logic is still **inside tools (debate_video3d.py)**
👉 `core/` is **underused**
👉 `units/` are thin but **tools still contain flow logic**

So:

> ❌ Structure looks modular
> ❌ Behavior is still monolithic

---

# ✅ TARGET (FOR R CURRENT PROJECT)

👉 Keep r structure
👉 Move logic INTO `core/`
👉 Make `tools/` dumb
👉 Make `units/` orchestrate via `core/`

---

# 🔥 REFACTOR PLAN (BASED ON R TREE)

---

# STEP 1 — DEFINE FINAL RESPONSIBILITY

## ✅ core/ = ENGINE (REAL LOGIC)

## ✅ units/ = ORCHESTRATION (FLOW PER UNIT)

## ✅ tools/ = THIN WRAPPERS (Crew interface)

---

# STEP 2 — CLEAN R TOOLS (CRITICAL)

## 🔥 TARGET:

```id="h9g1v1"
tools/debate_video3d.py → MUST become 20–30 lines
```

### KEEP ONLY:

```id="7zq7y6"
call unit_debate.run() OR debate_flow.execute()
```

### REMOVE from tools:

* parsing
* pipeline building
* TTS
* rendering
* subtitle generation

👉 Tools should NOT contain logic anymore

---

# STEP 3 — CREATE NEW CORE MODULES (INSIDE EXISTING)

 already have:

```id="xtpb8s"
core/
  parser/
  services/
  render/
```

We extend it 👇

---

## 🔷 3.1 Parser (ALREADY EXISTS ✅)

```id="2x4y2h"
core/parser/debate_parser.py
```

👉 Move ALL parsing logic here
👉 Remove from tool completely

---

## 🔷 3.2 Audio Layer (EXPAND EXISTING)

 already have:

```id="7q6y5v"
core/services/tts_service.py
core/services/audio_service.py
```

### MOVE INTO THESE:

From tool:

* `_tts_edge`
* audio concat logic

---

### FINAL RESPONSIBILITY:

```id="7lq6o5"
tts_service → text → audio
audio_service → merge audio
```

👉 No ffmpeg in tool anymore

---

## 🔷 3.3 Timeline Builder (NEW)

👉 CREATE:

```id="r3m9ax"
core/render/timeline_builder.py
```

### MOVE:

* timeline logic
* frame mapping

FROM tool → here

---

## 🔷 3.4 Clip Resolver (NEW)

👉 CREATE:

```id="q8l2mn"
core/render/clip_resolver.py
```

### MOVE:

* intro resolution
* ads resolution
* clip path mapping

---

## 🔷 3.5 Renderer (UPDATE EXISTING)

 already have:

```id="h7g5tr"
core/render/frame_renderer.py
```

👉 Move ALL cv2 logic here:

* VideoWriter
* frame loop
* clip reading

---

### FINAL RULE:

```id="c8h2rl"
renderer ONLY renders
```

👉 No config
👉 No business logic

---

## 🔷 3.6 Overlay System (NEW)

👉 CREATE:

```id="6j3n5f"
core/render/overlay/
  topic_overlay.py
  subtitle_overlay.py
```

### MOVE:

* `_draw_topic_overlay`
* `_draw_subtitle`

---

## 🔷 3.7 Subtitle Builder (NEW)

👉 CREATE:

```id="p2s9la"
core/subtitle/subtitle_builder.py
```

### MOVE:

* SRT generation
* TXT generation

---

## 🔷 3.8 Pipeline Builder (NEW — VERY IMPORTANT)

👉 CREATE:

```id="2v7kqs"
core/pipeline/debate_pipeline.py
```

### MOVE:

```python id="t3h1rp"
_build_pipeline_order()
```

---

👉 THIS IS THE BRAIN OF VIDEO STRUCTURE

---

# STEP 4 — CREATE DEBATE FLOW (INSIDE UNITS OR CORE)

 currently have:

```id="0b0xv6"
units/unit_debate.py
```

---

## 🔥 MODIFY THIS FILE

👉 This becomes r **Debate Flow Controller**

---

### FINAL STRUCTURE:

```id="6m8y0k"
unit_debate.py

run():
  load config
  parse debate
  build pipeline
  generate audio
  build timeline
  render video
  generate subtitles
```

---

👉 IMPORTANT:

All calls go to:

```id="gnm8mb"
core/*
```

NOT tools

---

# STEP 5 — REMOVE LOGIC FROM debate_video3d.py

## 🔥 FINAL STATE:

```id="v3y5pn"
class DebateVideo3dTool:
    def run():
        call unit_debate.run(inputs)
```

👉 That’s it. Nothing else.

---

# STEP 6 — CONNECT FLOW_CONTROLLER ( ALREADY HAVE IT)

 already built:

```id="t6yx4n"
flow_controller.py
```

---

## UPDATE:

Instead of tool:

```id="y3ntw5"
Flow → unit_debate.run()
```

NOT:

```id="a7y8cp"
Flow → tool → logic
```

---

# STEP 7 — USE meta.py (REMOVE DUPLICATES)

From tool REMOVE:

```python id="b0b7tz"
if file exists → skip
```

---

## USE ONLY:

```id="x3r4mq"
should_skip()
mark_unit()
```

---

# STEP 8 — FIX DATA FLOW (IMPORTANT)

Currently tool reads:

```id="m1oz8n"
propose.md / oppose.md / decide.md
```

---

## CHANGE:

👉 `unit_debate` loads files
👉 passes TEXT to parser

---

👉 Tool must NOT touch files directly

---

# STEP 9 — CLEAN CONFIG ACCESS

❌ REMOVE from tool:

* debate_config
* clip_config
* video_formats

---

✅ ONLY:

```id="p4zzd8"
unit_debate handles config
```

---

# STEP 10 — FINAL CLEAN ARCHITECTURE

```id="f5m4r1"
FlowController
   ↓
unit_debate.py   ← orchestrator
   ↓
core/
   parser/
   services/
   render/
   pipeline/
   subtitle/
```

---

# 🚨 WHAT  SHOULD NOT DO

❌ Don’t create new random folders
❌ Don’t duplicate logic
❌ Don’t keep fallback logic in renderer
❌ Don’t keep pipeline inside tool

---

# 🔥 RESULT AFTER REFACTOR

## BEFORE ❌

* tools = 1000+ lines
* duplicated logic
* hard to debug

---

## AFTER ✅

* tools = 20 lines
* unit = 100–200 lines
* core modules = reusable
* full flow control

---

# 🎯 FINAL CHECKLIST

After refactor:

* [ ] debate_video3d.py < 50 lines
* [ ] no ffmpeg inside tools
* [ ] no cv2 inside tools
* [ ] no pipeline logic inside tools
* [ ] unit_debate controls everything
* [ ] core contains all logic

---

# 🚀 design unit_debate


Perfect—this is the **most important file in r system**.
If `unit_debate.py` is designed correctly, r whole architecture becomes clean.

I’ll give  a **production-grade design (step-by-step execution flow)** — no code, but exact logic.

---

# 🎯 ROLE OF `unit_debate.py`

👉 This is **NOT a tool**
👉 This is **NOT core logic**

👉 This is:

> ✅ Orchestrator for Debate Pipeline (Flow-controlled)

---

# 🧠 FINAL RESPONSIBILITY

```text
unit_debate.py = "Coordinator"
```

It:

* calls core modules
* controls sequence
* handles config
* respects meta (skip/lock)

👉 It does NOT:

* parse manually
* render frames
* generate TTS directly

---

# ⚡ FINAL EXECUTION FLOW

```text
FlowController
   ↓
unit_debate.run()
   ↓
(core modules)
```

---

# 🔥 FULL DESIGN (STEP-BY-STEP)

---

## STEP 0 — INIT

### Input:

```text
topic
inputs (full config)
_workspace (path)
_slug
```

---

## STEP 1 — SMART SKIP (meta.py)

```text
if should_skip(Unit-Debate):
    EXIT
```

👉 No execution if already done

---

## STEP 2 — LOCK

```text
lock = acquire_lock(Unit-Debate)
```

👉 Prevent double execution

---

## STEP 3 — LOAD CONFIG (CENTRALIZED)

Extract ONLY what  need:

```text
video_formats
debate_config
clip_config
voices
lang_suffix
channel
```

👉 No deep nested access later
👉 Normalize config here

---

## STEP 4 — LOAD DATA FILES

From workspace:

```text
debate/propose.md
debate/oppose.md
debate/decide.md
```

👉 Read once
👉 Pass text forward

---

## STEP 5 — PARSE DEBATE

Call:

```text
core.parser.debate_parser.parse()
```

### Output:

```text
blocks = [
  {role: "propose", id: "p0", text: "..."},
  {role: "oppose", id: "c0", text: "..."},
  ...
]
```

---

## STEP 6 — LOOP PER FORMAT

```text
for fmt in video_formats:
```

👉 Everything below runs per format

---

# 🚀 PER-FORMAT PIPELINE

---

## STEP 7 — BUILD PIPELINE

Call:

```text
core.pipeline.debate_pipeline.build(fmt, config)
```

### Output:

```text
pipeline = [
  {type: "video", key: "intro"},
  {type: "block", key: "p0"},
  {type: "block", key: "c0"},
  ...
]
```

👉 PURE STRUCTURE
👉 No execution yet

---

## STEP 8 — GENERATE AUDIO SEGMENTS

Loop pipeline:

### For block:

```text
tts_service.generate(text, voice)
```

### For video:

```text
audio_service.extract(video_path)
```

---

### Output:

```text
audio_segments = [
  {path, duration, key}
]
```

---

## STEP 9 — MERGE AUDIO

```text
final_audio = audio_service.concat(audio_segments)
```

---

## STEP 10 — BUILD TIMELINE

```text
timeline = timeline_builder.build(audio_segments, fps)
```

### Output:

```text
[
  {start_frame, end_frame, key}
]
```

---

## STEP 11 — RESOLVE CLIPS

```text
clip_map = clip_resolver.resolve(pipeline, config)
```

### Output:

```text
{
  "p0": "path/to/video",
  "c0": "...",
  "intro": "..."
}
```

---

## STEP 12 — PREPARE SUBTITLE MAP

```text
subtitle_map = {
  key: text
}
```

👉 From:

* blocks (speech)
* config (ads text, subscribe text)

---

## STEP 13 — RENDER VIDEO

```text
renderer.render(
    timeline,
    clip_map,
    overlays,
    output_path
)
```

---

### overlays include:

```text
topic_overlay
subtitle_overlay
```

---

👉 Renderer only:

* reads frames
* applies overlay
* writes video

---

## STEP 14 — MERGE AUDIO + VIDEO

```text
final_video = audio_service.merge(video, audio)
```

---

## STEP 15 — GENERATE SUBTITLES

```text
subtitle_builder.generate(
    audio_segments,
    subtitle_map
)
```

Outputs:

```text
.srt
.txt
```

---

## STEP 16 — SAVE OUTPUT

```text
workspace/debate/{final_file}.mp4
```

---

# 🔚 AFTER LOOP

---

## STEP 17 — MARK DONE

```text
mark_unit(Unit-Debate, "done")
```

---

## STEP 18 — RELEASE LOCK

```text
release_lock(lock)
```

---

# ⚠️ ERROR HANDLING (IMPORTANT)

Wrap entire execution:

```text
try:
    run pipeline
except:
    mark_unit(failed)
    release_lock
    raise
```

---

# 🧩 FINAL FILE STRUCTURE (unit_debate.py)

```text
unit_debate.py

run():
  ├── check skip
  ├── acquire lock
  ├── load config
  ├── load files
  ├── parse blocks
  ├── loop formats
  │     ├── build pipeline
  │     ├── generate audio
  │     ├── concat audio
  │     ├── build timeline
  │     ├── resolve clips
  │     ├── render video
  │     ├── merge audio
  │     ├── generate subtitles
  │
  ├── mark done
  ├── release lock
```

---

# 🔥 CRITICAL RULES (DO NOT BREAK)

## 1. ❌ NO LOGIC IN TOOLS

Only:

```text
tool → calls unit_debate.run()
```

---

## 2. ❌ NO FILE PATH LOGIC IN CORE

Paths come from:

```text
unit_debate
```

---

## 3. ❌ NO CONFIG ACCESS IN RENDERER

Renderer = pure execution

---

## 4. ❌ NO PIPELINE LOGIC OUTSIDE pipeline/

Keep it centralized

---

## 5. ✅ unit_debate = ONLY place that knows full flow

---

# 🚀 RESULT

After this:

👉  can:

* plug new formats easily
* reuse renderer for animation
* reuse TTS for ads
* debug per step

---














====
