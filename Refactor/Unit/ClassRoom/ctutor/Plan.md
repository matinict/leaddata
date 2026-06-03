

## 1. CTutor Core idea

Here is the clean plan for your **CTutor** sub-unit — pulled directly from your Tink.md notes and organized for CF2.

It's not a new unit. It's a new *profile* inside your existing Unit-Classroom.

- **croom.json** = multi-character (2 teachers + 8+ students) → discussion, story, kids teaching
- **ctutor.json** = single-character (1 teacher + hologram) → tutorial replication

You keep the same Unit-Classroom code. Only the profile changes the execution path via `classroom_mode`.

## 2. Recommended profile file

Create `input/ctutor.json`:

```json
{
  "_profile": "CTutor",
  "description": "Classroom Cast -- Single Teacher with Hologram Tutorial Screen",

  "Unit-Classroom": true,
  "classroom_mode": "single",

  "classroom_teacher1_name": "James",
  "classroom_teacher1_gender": "male",
  "classroom_voice_teacher1": "en-US-GuyNeural",

  "topic": "Python Basic Structures Exercises",
  "focus": "speaker+screen+topic",

  "holo_source": "input/old_tutorial.mp4",
  "holo_position": "right",
  "holo_scale": 0.35
}
```

**What to remove vs croom:**
- Delete `classroom_teacher2_name`, `classroom_teacher2_gender`, `classroom_voice_teacher2`
- Delete entire `roles.students`, `voice_mapping.students`, `gender_distribution`

This matches Rule 27 — same schema, minimal override.

## 3. Why this architecture works for CF2

1. **One unit, two modes:** Unit-Classroom checks `classroom_mode`. If `"group"` → run croom pipeline. If `"single"` → run ctutor pipeline. No conflicting switches.
2. **Profile controls identity, not logic:** fits your CF2 rule that config drives behavior.
3. **Fully skippable:** each sub-unit checks for its output file first (Rule 24).

## 4. CTutor pipeline (inside Unit-Classroom)

```
ctutor.json
   ↓
subUnitCTutorIngest
   ├── extract transcript (Whisper)
   ├── extract OCR/code (screen text)
   └── summarize topic
   ↓
subUnitCTutorScript → output/{slug}/classroom/ctutor_script.md
   ↓
subUnitCTutorTTS → single teacher voice
   ↓
subUnitCTutorHolo → composite [HOLO:] clips from holo_source
   ↓
subUnitClassroomMerge → final mp4
```

## 5. The `focus` field — your control knob

You already designed this well. Use it to prioritize source:

- `"speaker"` → voice transcript only
- `"screen"` → code/OCR only  
- `"speaker+screen"` → combine both
- `"speaker+screen+topic"` → **recommended** (best for Python, n8n, LLM tutorials)

Change one string, no code change.

## 6. New script format

Replace ``, ``, `` with clean single-teacher markers:

```markdown
[INTRO]
Welcome back to the channel. Today we will learn Python basic structures.

[HOOK]
Have you ever repeated the same code many times? Python loops solve that.

[EXPLAIN]
A for loop lets us repeat actions automatically.

[DEMO]
[HOLO:old_screen_tutorial@00:45-01:12]
Here you can see a real example from our coding screen.

[CODE]
for i in range(5):
    print(i)

[SUMMARY]
Loops save time and reduce errors.

[CTA]
Practice this yourself and build confidence.
```

The `[HOLO:timestamp]` marker is the source of truth — subUnitCTutorHolo reads it and cuts the clip.

## 7. LLM prompt for script generation

This is what CF2 should send:

```
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

## 8. How to run

```bash
# multi-actor classroom
python main.py --profile croom

# single-teacher tutorial
python main.py --profile ctutor
```

## 9. Best use cases

This profile is stronger than croom for:
- Python tutorials
- n8n automation tutorials  
- local LLM setup
- AI coding classes
- Any "AI Instructor + floating demo screen" format (Khan Academy style)

You record once manually → CF2 reuses it forever: new voice, rewritten script, Shorts, HD class, hologram replay, multilingual later.

---

**Final folder:**
```
input/
 ├── croom.json      → 2 teachers + students
 ├── ctutor.json     → 1 teacher + hologram demo
```

Want me to generate the actual `ctutor.json` file from your current `croom.json` by stripping the student/teacher2 blocks?
