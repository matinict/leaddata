# 🎬 CF2=CrewAiFlowFactory — Flow-Based Rebuild Plan (Aligned with Current `crew.py`)

---

# 🧠 1. GOAL OF REBUILD

Your current system (from `crew.py`) is:

* ✅ Powerful (many agents/tools)
* ❌ Hard to control (manual triggers)
* ❌ Repeats work (no central data control)
* ❌ Not optimized for heavy video cost

---

## 🎯 New Goal

> Convert into **Flow-based Modular System** with:

* ✅ `Unit-*` naming (clear structure)
* ✅ Central **DataCreation Unit**
* ✅ Independent execution (run 1 unit only)
* ✅ Smart skip (no time waste)
* ✅ Reuse all existing tools (NO rewrite)

---

# 🧱 2. NEW NAMING STANDARD (MANDATORY)

## ✅ Main Units

```text
Unit-Scout
Unit-Data
Unit-Debate
Unit-Definition
Unit-Animation
Unit-Comparison
Unit-Publisher
Unit-Advertise
```

---

## ✅ Sub Units (camelCase)

```text
subUnitYtMetadata
subUnitYtUpload
subUnitFbUpload
subUnitSocialShare
subUnitTvc
subUnitShorts
```

---

# 🧠 3. CORE ARCHITECTURE (FLOW)

```text
FlowController
   ↓
Unit-Data   ← 🔥 ONLY generator
   ↓
Unit-Debate / Unit-Animation / Unit-Definition
   ↓
Unit-Publisher
   ↓
Unit-Advertise
```

---

# 🧩 4. MAPPING YOUR CURRENT CREW → NEW UNITS

Based on your `crew.py` 👇

---

## 🔷 Unit-Scout

### Agents:

* `social_scout_unit`

### Output:

```text
topic list
```

---

## 🔷 Unit-Data (🔥 MOST IMPORTANT)

### Agents reused:

* `data_researcher`
* `csv_generator`
* `definition_specialist`
* `debater`, `judge`, `debater_m`, `judge_m`

---

### Tasks reused:

* `research_data`
* `generate_csv`
* `define_topic`
* `create_debate_definition`
* `debate_propose`
* `debate_oppose`
* `debate_decide`

---

### Output (FILE ONLY):

```text
output/{topic}/

  debate/debate.md
  definition/def_*.md
  animation/data.csv
  comparison/comparison.md
```

---

# 🎤 5. Unit-Debate

### Agents:

* `debate_video_producer`
* `debate_merge_specialist`
* `audio_engineer`

---

### Tasks:

* `create_debate_video`
* `debate_merge`

---

### Input:

```text
debate/debate.md
```

---

### Output:

```text
debate/video.mp4
```

---

# 📘 6. Unit-Definition

### Agents:

* `definition_video_producer`

---

### Tasks:

* `create_definition_video`

---

### Input:

```text
definition/*.md
```

---

### Output:

```text
definition/video.mp4
```

---

# 📊 7. Unit-Animation

### Agents:

* `bar_race_video_producer`
* `bar_merge_specialist`
* `bar_race_audio_engineer`
* `intro_clip_producer`

---

### Tasks:

* `create_bar_race_video`
* `bar_merge`
* `add_audio`

---

### Input:

```text
animation/data.csv
```

---

### Output:

```text
animation/video.mp4
```

---

# ⚖️ 8. Unit-Comparison

(Reuses debate-style logic)

### Agents:

* `debater`, `judge`

---

### Output:

```text
comparison/comparison.md
```

---

# 🚀 9. Unit-Publisher

## 🔷 subUnitYtMetadata

* agent: `yt_metadata_specialist`
* task: `generate_youtube_metadata`

---

## 🔷 subUnitYtThumbnail

* agent: `yt_thumbnail_specialist`
* task: `generate_thumbnail`

---

## 🔷 subUnitYtUpload

* agent: `youtube_upload_specialist`
* task: `upload_to_youtube`

---

## 🔷 subUnitFbUpload

* agent: `facebook_upload_specialist`
* task: `upload_to_facebook`

---

## 🔷 subUnitSocialShare

* agent: `social_share_specialist`
* task: `share_to_social`

---

### Output

```text
publisher/

  metadata/youtube.json
  uploads/youtube/status.json
  uploads/facebook/status.json
```

---

# 📢 10. Unit-Advertise

## 🔷 subUnitShorts

* cut from main video
* reuse `SmartVideoTool`

---

## 🔷 subUnitSocial

* captions + short clips

---

## 🔷 subUnitTvc

* cinematic ad
* reuse:

  * `SmartVideoTool`
  * `AudioGenerationTool`

---

### Output

```text
advertise/

  social/
  shorts/
  tvc/
```

---

# ⚡ 11. FLOW EXECUTION DESIGN

```text
run --unit Unit-Data
run --unit Unit-Debate
run --unit Unit-Publisher
```

---

## 🔥 KEY RULE

> Only ONE unit runs at a time

---

# 🧠 12. META.JSON (CONTROL SYSTEM)

```json
{
  "topic": "...",

  "status": {
    "Unit-Data": "done",
    "Unit-Debate": "pending",
    "Unit-Publisher": "pending"
  },

  "uploads": {
    "youtube": "done",
    "facebook": "pending"
  }
}
```

---

# ⚡ 13. SMART SKIP SYSTEM

Each unit checks:

```text
IF output exists → SKIP
IF meta == done → SKIP
```

---

# 🔒 14. LOCK SYSTEM

During execution:

```text
.lock
```

Prevents:

* double run
* partial failure

---

# 🧩 15. CREW.PY ROLE (IMPORTANT CHANGE)

## ❌ Before:

* All agents + tasks run together

## ✅ After:

> Crew becomes **tool registry only**

---

### Flow controls execution:

```text
Flow → selects agents/tasks → runs specific unit
```

---

# 🚀 16. FINAL FLOW STRUCTURE

```text
flow/

  flow_main.py
  unit_data.py
  unit_debate.py
  unit_definition.py
  unit_animation.py
  unit_publisher.py
  unit_advertise.py
```

---

# 🔥 17. WHY THIS REBUILD WORKS

✔ Reuses your existing tools
✔ No rewrite of agents
✔ No repeated LLM calls
✔ Supports heavy video pipeline
✔ Easy debugging (per topic folder)
✔ Fully modular

---

# 🎯 FINAL PRINCIPLE

> **One Topic = One Workspace = Modular Units = Zero Waste**

---

# ✅ NEXT STEP

If you’re ready, I’ll:

👉 Design **FlowController (exact execution logic)**
👉 Show how to call Crew selectively per unit
👉 Add CLI (`--unit`, `--topic`) system

Just say:

**“build flow controller”**


PLAN:
================================================================================
# 🎬 CF2=CrewAiFlowFactory — Flow-Based Rebuild Plan (Aligned with Current `crew.py`)

---

# 🧠 1. GOAL OF REBUILD

Your current system (from `crew.py`) is:

* ✅ Powerful (many agents/tools)
* ❌ Hard to control (manual triggers)
* ❌ Repeats work (no central data control)
* ❌ Not optimized for heavy video cost

---

## 🎯 New Goal

> Convert into **Flow-based Modular System** with:

* ✅ `Unit-*` naming (clear structure)
* ✅ Central **DataCreation Unit**
* ✅ Independent execution (run 1 unit only)
* ✅ Smart skip (no time waste)
* ✅ Reuse all existing tools (NO rewrite)

---

# 🧱 2. NEW NAMING STANDARD (MANDATORY)

## ✅ Main Units

```text
Unit-Scout
Unit-Data
Unit-Debate
Unit-Definition
Unit-Animation
Unit-Comparison
Unit-Publisher
Unit-Advertise
```

---

## ✅ Sub Units (camelCase)

```text
subUnitYtMetadata
subUnitYtUpload
subUnitFbUpload
subUnitSocialShare
subUnitTvc
subUnitShorts
```

---

# 🧠 3. CORE ARCHITECTURE (FLOW)

```text
FlowController
   ↓
Unit-Data   ← 🔥 ONLY generator
   ↓
Unit-Debate / Unit-Animation / Unit-Definition
   ↓
Unit-Publisher
   ↓
Unit-Advertise
```

---

# 🧩 4. MAPPING YOUR CURRENT CREW → NEW UNITS

Based on your `crew.py` 👇

---

## 🔷 Unit-Scout

### Agents:

* `social_scout_unit`

### Output:

```text
topic list
```

---

## 🔷 Unit-Data (🔥 MOST IMPORTANT)

### Agents reused:

* `data_researcher`
* `csv_generator`
* `definition_specialist`
* `debater`, `judge`, `debater_m`, `judge_m`

---

### Tasks reused:

* `research_data`
* `generate_csv`
* `define_topic`
* `create_debate_definition`
* `debate_propose`
* `debate_oppose`
* `debate_decide`

---

### Output (FILE ONLY):

```text
output/{topic}/

  debate/debate.md
  definition/def_*.md
  animation/data.csv
  comparison/comparison.md
```

---

# 🎤 5. Unit-Debate

### Agents:

* `debate_video_producer`
* `debate_merge_specialist`
* `audio_engineer`

---

### Tasks:

* `create_debate_video`
* `debate_merge`

---

### Input:

```text
debate/debate.md
```

---

### Output:

```text
debate/video.mp4
```

---

# 📘 6. Unit-Definition

### Agents:

* `definition_video_producer`

---

### Tasks:

* `create_definition_video`

---

### Input:

```text
definition/*.md
```

---

### Output:

```text
definition/video.mp4
```

---

# 📊 7. Unit-Animation

### Agents:

* `bar_race_video_producer`
* `bar_merge_specialist`
* `bar_race_audio_engineer`
* `intro_clip_producer`

---

### Tasks:

* `create_bar_race_video`
* `bar_merge`
* `add_audio`

---

### Input:

```text
animation/data.csv
```

---

### Output:

```text
animation/video.mp4
```

---

# ⚖️ 8. Unit-Comparison

(Reuses debate-style logic)

### Agents:

* `debater`, `judge`

---

### Output:

```text
comparison/comparison.md
```

---

# 🚀 9. Unit-Publisher

## 🔷 subUnitYtMetadata

* agent: `yt_metadata_specialist`
* task: `generate_youtube_metadata`

---

## 🔷 subUnitYtThumbnail

* agent: `yt_thumbnail_specialist`
* task: `generate_thumbnail`

---

## 🔷 subUnitYtUpload

* agent: `youtube_upload_specialist`
* task: `upload_to_youtube`

---

## 🔷 subUnitFbUpload

* agent: `facebook_upload_specialist`
* task: `upload_to_facebook`

---

## 🔷 subUnitSocialShare

* agent: `social_share_specialist`
* task: `share_to_social`

---

### Output

```text
publisher/

  metadata/youtube.json
  uploads/youtube/status.json
  uploads/facebook/status.json
```

---

# 📢 10. Unit-Advertise

## 🔷 subUnitShorts

* cut from main video
* reuse `SmartVideoTool`

---

## 🔷 subUnitSocial

* captions + short clips

---

## 🔷 subUnitTvc

* cinematic ad
* reuse:

  * `SmartVideoTool`
  * `AudioGenerationTool`

---

### Output

```text
advertise/

  social/
  shorts/
  tvc/
```

---

# ⚡ 11. FLOW EXECUTION DESIGN

```text
run --unit Unit-Data
run --unit Unit-Debate
run --unit Unit-Publisher
```

---

## 🔥 KEY RULE

> Only ONE unit runs at a time

---

# 🧠 12. META.JSON (CONTROL SYSTEM)

```json
{
  "topic": "...",

  "status": {
    "Unit-Data": "done",
    "Unit-Debate": "pending",
    "Unit-Publisher": "pending"
  },

  "uploads": {
    "youtube": "done",
    "facebook": "pending"
  }
}
```

---

# ⚡ 13. SMART SKIP SYSTEM

Each unit checks:

```text
IF output exists → SKIP
IF meta == done → SKIP
```

---

# 🔒 14. LOCK SYSTEM

During execution:

```text
.lock
```

Prevents:

* double run
* partial failure

---

# 🧩 15. CREW.PY ROLE (IMPORTANT CHANGE)

## ❌ Before:

* All agents + tasks run together

## ✅ After:

> Crew becomes **tool registry only**

---

### Flow controls execution:

```text
Flow → selects agents/tasks → runs specific unit
```

---

# 🚀 16. FINAL FLOW STRUCTURE

```text
flow/

  flow_main.py
  unit_data.py
  unit_debate.py
  unit_definition.py
  unit_animation.py
  unit_publisher.py
  unit_advertise.py
```

---

# 🔥 17. WHY THIS REBUILD WORKS

✔ Reuses your existing tools
✔ No rewrite of agents
✔ No repeated LLM calls
✔ Supports heavy video pipeline
✔ Easy debugging (per topic folder)
✔ Fully modular

---

# 🎯 FINAL PRINCIPLE

> **One Topic = One Workspace = Modular Units = Zero Waste**

---

# ✅ NEXT STEP

If you’re ready, I’ll:

👉 Design **FlowController (exact execution logic)**
👉 Show how to call Crew selectively per unit
👉 Add CLI (`--unit`, `--topic`) system

Just say:

**“build flow controller”**
