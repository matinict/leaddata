
# CTutor  idea for CF2

current profile is multi-character classroom mode (`2 Teachers / 8+ Students`) from `croom.json`.
current profile is single-character classroom mode (`1 Teachers`) from `CTutor.json`.

You can create a **new profile** specifically for **single teacher mode**, and it fits your architecture well because profile config controls identity, not logic (matches your CF2 rules).

### Recommended new profile

Create a separate profile, for example:

```json
_profile: "CTutor"
description: "Classroom Cast -- 1 Teacher Solo"
```

### Why separate profile (best for your CF2)

Because in your system:

* `croom` = group interaction format
* `CTutor` = lecture/tutorial format

This keeps **Unit-Classroom reusable** without changing unit code. Only profile changes.

---

# Suggested structure change

From this current:

```json
"description": "Classroom Cast -- 2 Teachers / 8+ Students"
```

to a new dedicated config:

```json
"description": "Classroom Cast -- 1 Teacher Solo"
```

and simplify roles to:

### Teacher only

```json
"classroom_teacher1_name": "James",
"classroom_teacher1_gender": "male",
"classroom_voice_teacher1": "en-US-GuyNeural"
```

### Disable teacher2

Remove:

```json
classroom_teacher2_name
classroom_teacher2_gender
classroom_voice_teacher2
```

### Remove students block

You can remove entire:

```json
roles.students
voice_mapping.students
gender_distribution
```

---

# Best use cases for single teacher profile

Your hologram tutorial idea actually works **better** in single-teacher mode:

Current idea:

* teacher speaks
* hologram shows your old recorded tutorial on side screen

That feels like:

### “AI Instructor + floating demo screen”

Very similar to channels like:

Khan Academy style digital instructor,
but with your own branded screen-cast overlay.

This format is stronger for:

* Python tutorials
* n8n automation tutorials
* local LLM setup
* AI coding classes

---

# My recommendation for CF2 profile naming

Use two permanent classroom profiles:

### 1. Existing

```text
croom
```

→ multi actor
→ kids / discussion / story teaching

### 2. New

```text
ctutor
```

or

```text
tutor_single
```

I recommend:

## `ctutor`

Reason:

* short
* aligned with `croom`
* easy CLI switch
* future scalable

Example:

```bash
python main.py --profile ctutor
```

---

# Ideal description for new profile

Use:

```json
"description": "Classroom Cast -- Single Teacher with Hologram Tutorial Screen"
```

That directly explains your new feature.

---

# Final architecture (clean)

Your profiles become:

```text
input/
 ├── croom.json      → 2 teachers + students
 ├── ctutor.json     → 1 teacher + hologram demo
```

This is the cleanest CF2 approach.

Since you already uploaded `croom.json`, your new `ctutor.json` can be made by cloning it and removing the classroom interaction roles.
Yes — for **CTutor**, the script should be generated differently from `croom`.

Your uploaded `script.md` is clearly **dialogue-driven classroom script** with multi actors (`[T1]`, `[T2]`, `[S1]`, `[HOLO]`) — great for classroom simulation.

For **ctutor**, the generation should be optimized around:

### Core concept

> **Your old tutorial video/audio/text becomes source context → LLM generates a fresh, branded teaching script → single AI teacher narrates it.**

That is exactly the right direction for your CF2.

---

# Recommended CTutor generation pipeline

## Input

Your config:

```json
{
  "topic": "Python Basic Structures Exercises",
  "focus": "video speaker text"
}
```

Meaning:

* `topic` = learning subject
* `focus` = what source to prioritize for teaching style

---

# How CTutor script should generate

## Step 1 — Extract source intelligence

CTutor should collect from your old tutorial:

### A. Video transcript

From your recorded tutorial:

* spoken words
* explanations
* examples
* pauses

### B. Screen OCR / code text

From visible screen:

* code snippets
* output text
* menu labels
* terminal

### C. Topic semantic

From config:

```json
topic
```

This gives LLM lesson target.

---

# Best architecture for CTutor

## New pipeline

```text
Unit-Classroom
   └── subUnitCTutorScript
         ├── transcript extractor
         ├── OCR extractor
         ├── tutorial summarizer
         └── llm script writer
```

---

# New output

Generate:

```text
output/{slug}/classroom/ctutor_script.md
```

---

# Ideal CTutor script format

Instead of this current:

```text
[T1] James:
[T2] Sarah:
[S1]:
```

Use single-teacher clean format:

```markdown
[INTRO]
Welcome back to the channel. Today we will learn Python basic structures.

[HOOK]
Have you ever repeated the same code many times? Python loops solve that.

[EXPLAIN]
A for loop lets us repeat actions automatically.

[DEMO]
[HOLO:old_screen_tutorial]
Here you can see a real example from our coding screen.

[CODE]
for i in range(5):
    print(i)

[OUTRO]
Practice this yourself and build confidence.
```

---

# Best prompt for LLM

This is what your CF2 should send to LLM:

```text
Generate a brand new tutorial script for a single AI teacher.

Inputs:
- topic: {topic}
- transcript: {old_video_transcript}
- screen_text: {ocr_text}
- focus: {focus}

Rules:
- create original script, not copy transcript
- improve clarity
- simplify for beginner
- keep strong tutorial flow
- include demo markers [HOLO:*]
- output markdown only
- narration first
- optimized for TTS voice
```

---

# Your `focus` field can become powerful

You wrote:

```json
"focus": "video speaker text"
```

Excellent design.

You can expand it:

### Suggested modes

```json
"focus": "speaker"
```

→ prioritize voice transcript only

```json
"focus": "screen"
```

→ prioritize code on screen

```json
"focus": "speaker+screen"
```

→ combine both (best)

```json
"focus": "speaker+screen+topic"
```

→ strongest mode (recommended)

For your tutorial project, use:

## Best value

```json
"focus": "speaker+screen+topic"
```

---

# Why this is strong for PlayOwnAi

Since your channel YouTube content is AI automation/tutorial based, this means:

You record **once manually**, then CF2 can:

✅ reuse your tutorial forever
✅ create new teacher voice
✅ rewrite better script
✅ make Shorts
✅ make HD class
✅ make hologram replay
✅ multilingual later

This becomes a real **tutorial replication engine**.

---

# My recommendation for CTutor script file

Use:

```text
ctutor_script.md
```

Structure:

```markdown
[INTRO]
[HOOK]
[EXPLAIN]
[DEMO]
[CODE]
[SUMMARY]
[CTA]
```

---

# Strongest CF2 flow

Final architecture:

```text
ctutor.json
     ↓
old tutorial mp4
     ↓
extract transcript
     ↓
extract OCR
     ↓
LLM rewrite
     ↓
ctutor_script.md
     ↓
single teacher TTS
     ↓
hologram overlay
     ↓
final tutorial video
```

This is a very strong product direction for CF2.
It turns your old manual tutorials into scalable AI-generated teaching assets.


Let me read the project files carefully before designing anything.Now I have everything I need. Let me build the full enhanced spec.Good. Now I have the full picture. Let me build the complete, structured spec.Six tabs — click through each one. Here is the reasoning behind the key decisions.

**Why Unit-Classroom, not a new top-level unit.** Your Rule 3 table already has the right shape: one unit, one responsibility. The responsibility here is "classroom-style video." Whether that's two teachers arguing or one teacher with a hologram demo, the *unit* is the same — what changes is the execution path inside it, controlled by `classroom_mode` in config. This keeps the Unit count small and the FlowController clean.

**Why `classroom_mode` gates, not separate switches.** Adding `Unit-CTutor: true` alongside `Unit-Classroom: false` would create two overlapping switches that could contradict each other — a rule violation. One master switch (`Unit-Classroom`), one config key (`classroom_mode: "single"`), single branch point at unit entry. That is it.

**The `focus` field is the most powerful design here.** It makes the ingest sub-unit fully config-driven rather than logic-driven, which matches Rule 30 exactly. You can change what source material the LLM prioritizes by editing one string in ctutor.json, with zero code changes. `speaker+screen+topic` is the strongest mode: transcript gives pacing and vocabulary, OCR gives code accuracy, topic gives the lesson objective.

**The `[HOLO:timestamp]` marker pattern** is the clean solution for the hologram demo problem. The LLM writes it into the script at the right narrative moment. The `subUnitCTutorHolo` tool reads those markers, extracts the clip from `holo_source` at those timestamps, and composites the overlay. No magic, no hardcoded timing — the script is the source of truth.

**Every sub-unit is independently skippable.** If you already generated `ctutor_script.md` yesterday and just want to re-render the video with a different `holo_position`, you run Unit-Classroom again — ingest and script are both skipped, TTS is skipped, only holo composite and merge re-run. This is Rule 24 applied properly at the sub-unit level, not just the unit level.

**The `ctutor.json` file is a minimal override.** Only the keys that differ from `data.json` are included. The deep-merge in FlowController handles the rest. Schema shape is preserved throughout — no structural drift, fully aligned with Rule 27 and Rule 29.
