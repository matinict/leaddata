# KidifyCode — Project Plan
### CF2 Kids Education Pipeline

---

## What Is This?

KidifyCode is a **CF2 config profile** — not a new codebase.

It reuses the existing CF2 engine to produce cinematic, story-based coding lessons for children (age 7–12), auto-generated, multilingual, and faceless.

> **One engine. New profile. New audience.**

---

## Core Principle

```
Unit-Classroom + profile: kidifycode
    → story script (LLM)
    → scene plan
    → clip selection
    → render
    → package + publish
```

No new units are needed beyond `Unit-Classroom`. Everything else is already built.

---

## What Already Exists in CF2

| Component | Status |
|---|---|
| Multi-character scene system | ✅ Ready |
| Clip mapping + loop system | ✅ Ready |
| TTS engine (edge-tts / piper) | ✅ Ready |
| Intro / outro / ad injection | ✅ Ready |
| Subtitle overlay pipeline | ✅ Ready |
| Shorts + HD format switching | ✅ Ready |
| Timeline / segment architecture | ✅ Ready |
| Debate parser (reusable base) | ✅ Ready |
| Meta + Smart Skip system | ✅ Ready |
| Profile / config merge system | ✅ Ready |

The hardest parts are solved. KidifyCode is a content and prompt design project built on top of a production rendering engine.

---

## New Unit Required

### `Unit-Classroom`

One new unit. Sits between `Unit-Data` and `Unit-Animation/Packaging`.

**Responsibility:** Parse a lesson script and produce a sequenced scene plan for the renderer.

**SubUnits:**

| SubUnit | Responsibility |
|---|---|
| `subUnitLessonParser` | Parse `[PHASE:x]` + `[T1]` / `[S1]` tags from lesson .md |
| `subUnitSceneSelector` | Map each line/phase to the correct background clip |
| `subUnitTeacherNarration` | Route teacher lines to TTS |
| `subUnitStudentReaction` | Route student lines + assign personality clips |
| `subUnitSubtitleFX` | Generate highlighted subtitle .txt per segment |

**Input:** `lesson_{lang}.md` written by Unit-Data  
**Output:** `classroom_video_{fmt}_with_audio.mp4`

---

## New Profile Required

### `input/profile/kidifycode.json`

A deep-merge override on top of `data.json`. Only fields that differ are listed.

**Key fields:**

| Field | Value | Purpose |
|---|---|---|
| `_profile` | `"kidifycode"` | Profile identity |
| `Unit-Classroom` | `true` | Enables lesson pipeline |
| `classroom_mode` | `"mission_story"` | Lesson structure style |
| `kidify_level` | `"age_7_12"` | Prompt tone instruction |
| `story_mode` | `true` | Characters use narrative framing |
| `code_overlay_mode` | `"floating_hologram"` | Old tutorial clip injection style |
| `old_video_reuse` | `true` | Inject existing tutorial clips as scene inserts |
| `teachers_count` | `2` | T1 (main) + T2 (demo) |
| `students_count` | `4` | S1 Curious, S2 Smart, S5 Funny, S8 Beginner |
| `clip_style` | `"3d_classroom"` | Renderer mode |

---

## Script Format (Lesson .md)

Unit-Data generates this. LLM prompt drives the structure.

```
[PHASE:hook]
[T1] Teacher Mia: Today our robot forgot its favorite fruit.
[S1-F] Curious: Oh no! Can robots forget things?

[PHASE:mission]
[T1] Teacher Mia: Our mission — teach the robot to remember.
[S2-M] Smart: Like a magic memory box?

[PHASE:show_code]
[T2] Demo Teacher: Watch the hologram code screen.
[S8-M] Beginner: I see letters and fruit words!

[PHASE:mistake]
[T1] Teacher Mia: Oops — robot stored apple, not banana.
[S5-F] Funny: Robot is hungry!

[PHASE:fix]
[T2] Demo Teacher: We update the variable.
[S2-M] Smart: So variable means changing memory?

[PHASE:challenge]
[T1] Teacher Mia: If we store mango, what prints?
[S1-F] Curious: Mango appears?

[PHASE:quiz]
[T1] Teacher Mia: What is a variable?
[S8-M] Beginner: A memory box.
```

---

## Cast (Active for KidifyCode)

| Code | Role | Personality |
|---|---|---|
| T1 | Main Teacher | Friendly, storytelling |
| T2 | Demo Teacher | Technical, calm |
| S1-F | Curious Student | Asks "why" questions |
| S2-M | Smart Student | Connects concepts |
| S5-F | Funny Student | Jokes, lightens mood |
| S8-M | Beginner Student | Confused, relatable |

Four students maximum. Keeps clip mapping simple and audio clean.

---

## Lesson Phase Structure

```
hook       → funny opening problem
mission    → kids must solve it
show_code  → old tutorial clip as hologram overlay
mistake    → bug / wrong output
fix        → teacher explains simply
challenge  → student predicts result
quiz       → one-line recap question + answer
```

This maps directly to clip categories in `classroom_clips.json` (Shorts and HD variants).

---

## Code Overlay System

Old tutorial footage is injected as a scene insert — not discarded.

| Overlay Mode | Description |
|---|---|
| `floating_hologram` | Transparent clip floats top-right |
| `center_board` | Full center projection |
| `teacher_projection` | Behind teacher position |
| `corner_screen` | Small zoomed corner |

Activated during `[PHASE:show_code]` segments automatically.

---

## Pipeline Flow

```
CLI: crewai run --profile kidifycode --topic "Python Variables"
    ↓
flow_controller.py
    ↓
Unit-Data
    → generates lesson_{lang}.md (story script)
    ↓
Unit-Classroom
    → parses phases + speakers
    → selects clips per segment
    → routes TTS per voice
    → builds timeline
    → renders classroom_video_{fmt}_with_audio.mp4
    ↓
Unit-Packaging
    → YT metadata + thumbnail + CC subtitles
    ↓
Unit-Publisher
    → YouTube upload (Shorts + HD)
    ↓
Unit-Advertise
    → social share post
```

---

## Episode Series: "Python for Kids with AI Teachers"

| # | Topic | Concept Metaphor |
|---|---|---|
| 1 | Python Variables | Robot Memory Box |
| 2 | Python Loops | Banana Repeater Robot |
| 3 | If / Else | Magic Decision Door |
| 4 | Functions | Superhero Skills |
| 5 | AI Basics | Talking Robot Brain |
| 6 | Machine Learning | Smart Drawing Machine |
| 7 | Debugging | Bug Monster Attack |
| 8 | APIs | Secret Code Mission |

Each episode is one topic, one run, one pipeline execution.

---

## Scalability: Profile Family

Once `kidifycode` works, clone to:

| Profile | Subject |
|---|---|
| `kidifyai` | AI concepts for kids |
| `kidifymath` | Math with story framing |
| `kidifyscience` | Science basics |
| `kidifyenglish` | Language learning |

Same renderer. Same Unit-Classroom. Different LLM prompt tone.

---

## Build Phases

### Phase 1 — Foundation
- Create `Unit-Classroom` with subunits
- Create `input/profile/kidifycode.json`
- Write Unit-Data LLM prompt for lesson script generation
- Map existing classroom clips to phase keys

### Phase 2 — Enhancement
- Add emotion-aware clip selection (`if "why" in text → confused_clip`)
- Add code overlay injection for `show_code` phase
- Add fake camera motion via FFmpeg (slow zoom, pan)

### Phase 3 — Scale
- Clone profile to `kidifyai`, `kidifymath`
- Add Bengali / Hindi language profiles for local market
- Automate episode queue via Unit-Scout

---

## What Is NOT Needed

- New rendering engine (existing 3D renderer handles it)
- Separate codebase (profile merge covers all differences)
- New upload system (Unit-Publisher handles it)
- Manual clip editing (timeline builder automates it)
- Separate channel brand (PlayOwnAi works as the studio brand)

---

## One-Line Summary

> KidifyCode = `Unit-Classroom` + `kidifycode.json` profile + lesson prompt design.
> The engine is already built. What remains is content intelligence and clip assets.






Here is a streamlined, duplication-free project plan for **KidifyCode**, organized for clarity, execution readiness, and strict alignment with your existing CF2 architecture.

---
### 🎯 Vision & Core Objective
Transform technical coding/AI topics into engaging, story-driven classroom videos for kids (ages 7–12). Leverage the existing CF2 pipeline to produce high-retention educational content without adding new units or renderers.

---
### 🧱 Architecture Strategy
| Principle | Implementation |
|-----------|----------------|
| **Single Unit, Multi-Profile** | Keep `Unit-Classroom` as the only renderer. Drive all behavior via profile configs (`kidifycode.json`, `kidifyai.json`, etc.) |
| **Zero Unit Sprawl** | No `Unit-Kids`, `Unit-Tutor`, or specialized renderers. CF2 stays modular and maintainable. |
| **Config = Identity** | Profiles control tone, vocabulary, scene modes, TTS voices, overlay styles, and clip-injection ratios. |
| **Intent-Driven Scenes** | Replace random/randomized overlays with context-aware scene selection (code → hologram, question → reaction, quiz → challenge UI). |

---
### 📖 Content Design Framework
**1. 7-Phase Classroom Flow**
1. **Hook** – Fun, relatable problem or scenario
2. **Mission** – Clear learning goal framed as a task
3. **Show Code** – Floating hologram/demo screen
4. **Mistake** – Intentional bug or wrong output
5. **Fix** – Simple teacher explanation with visual highlight
6. **Challenge** – Student predicts what happens next
7. **Quiz** – Quick recap + 3 rapid questions

**2. Character Cast**
- **2 Teachers:** Lead explainer + simplifier
- **4 Students:** Curious, Smart, Funny, Beginner
*(Reduces audio/clip overhead while keeping classroom dynamics lively)*

**3. Concept Transformation**
Convert technical terms into kid-friendly metaphors before script generation:
- Variables → Magic Memory Boxes
- Functions → Robot Skill Buttons
- Loops → Repeat Spells
- Bugs → Naughty Gremlins
- APIs → Robot Telephones

---
### 🎨 Visual & Rendering System
| Feature | Execution Approach |
|---------|-------------------|
| **Hologram Overlay Engine** | Reuse old tutorial footage as semi-transparent floating screens (70–85% opacity, cyan/blue glow, slight perspective tilt, subtle hover motion, soft scanlines) |
| **Authenticity Layer** | Old low-quality clips are reframed as “projector footage,” “lab demos,” or “archive screens” to feel intentional and premium |
| **Scene Intent Mapping** | `contains_code` → code hologram • `is_question` → reaction clip • `is_quiz` → challenge popup • `is_important` → zoom/focus mode |
| **Attention Pacing** | Visual or audio change every 4–8 seconds to maintain kid engagement |

---
### 🗺️ Development Roadmap
| Phase | Focus | Deliverables |
|-------|-------|--------------|
| **1. Foundation (MVP)** | Profile + Script + Basic Overlay | `kidifycode.json` schema, LLM topic→story prompt, hologram overlay mode, 3 pilot episodes (Variables, Loops, If/Else) |
| **2. Scene Intelligence** | Automation + Polish | Semantic overlay selector, “pause & explain” timing, “predict output” insertion, automatic old-clip trimming & framing, Shorts+HD output |
| **3. Scale & Expand** | Multi-Profile + Personality Engine | `kidifyai` / `kidifyscience` profiles, emotion-aware pacing, character personality tags, automated quiz generation, render pipeline optimization |

---
### 🔄 End-to-End Workflow
`Input Topic` → `Profile Selection` → `LLM Story Transformer` → `Classroom Script Generation` → `Scene Intent Planner` → `Hologram/Clip Matcher` → `Render Engine` → `Packaging & Distribution`

---
### 🛡️ Guardrails & Best Practices
- ✅ Never hardcode sequences; use intent-driven planning
- ✅ Max 12 words per line, grade 3–5 vocabulary
- ✅ Always validate against the 7-phase structure
- ✅ Reuse existing assets; never duplicate renderers or units
- ✅ Old footage must always be framed, overlaid, or stylized (never raw fullscreen)
- ✅ Profile configs only modify existing schema keys (Rule 27/28 compliance)

This plan removes all brainstorming redundancy, aligns strictly with CF2’s flow/unit/file-based rules, and provides a clear, step-by-step execution path without requiring new code architecture. Let me know if you want this exported as a checklist, milestone tracker, or config schema draft. # KidifyCode — Clean Project Plan

## What KidifyCode Actually Is

A **profile** inside your existing CF2 system. Not a new unit. Not a new renderer.

```
"_profile": "kidifycode"
→ Unit-Classroom handles everything
```

---

## The Core Idea

Transform any technical topic into child-friendly classroom storytelling.

| Real Concept | Kid Version |
|---|---|
| Variable | Magic Memory Box |
| Loop | Repeat Robot |
| Function | Superhero Skill |
| Bug | Naughty Gremlin |
| API | Robot Telephone |

---

## What Already Exists (No New Code Needed)

Your CF2 already has:

- Segment rendering
- Teacher + student speakers
- Bubble system
- TTS sync
- Clip injection
- Classroom scene logic
- Profile switching

**You only need to configure, not rebuild.**

---

## Profile Structure

```
input/profile/kidifycode.json
```

```json
{
  "_profile": "kidifycode",
  "Unit-Classroom": true,
  "classroom_mode": "mission_story",
  "story_mode": true,
  "code_overlay_mode": "floating_hologram",
  "old_video_reuse": true,
  "teachers_count": 2,
  "students_count": 4
}
```

---

## Characters (Simplified)

| ID | Role |
|---|---|
| T1 | Main Teacher |
| T2 | Demo Teacher |
| S1 | Curious Student |
| S2 | Smart Student |
| S5 | Funny Student |
| S8 | Beginner Student |

**Why 4 students only:** Less chaos. Easier clip mapping. Faster production.

---

## Episode Structure (Every Video)

```
hook        → funny problem introduced
mission     → kids must solve it
show_code   → old tutorial clip as hologram
mistake     → bug or wrong output appears
fix         → teacher explains simply
challenge   → student predicts result
quiz        → quick recap
```

---

## How Old Tutorial Videos Get Used

**Never show them raw. Always wrap them.**

| Wrapper Style | Effect |
|---|---|
| Floating hologram | Futuristic, intentional |
| Classroom projector | Teacher points at screen |
| Zoomed crop | Hides low quality |
| Retro terminal | Aesthetic, not outdated |

Old footage becomes: *"AI classroom projection"* — not *"old low quality video."*

---

## Episode Series Plan

| Episode | Story Hook | Concept |
|---|---|---|
| 1 | Robot forgot its fruit | Variables |
| 2 | Banana collecting machine | Loops |
| 3 | Magic decision door | If / Else |
| 4 | Superhero skill buttons | Functions |
| 5 | Talking robot brain | AI Basics |
| 6 | Smart drawing machine | Machine Learning |
| 7 | Bug monster attack | Debugging |
| 8 | Secret code mission | APIs |

---

## What NOT to Build

```
❌ Unit-Kids
❌ Unit-School
❌ renderer_kids.py
❌ Unit-KidifyCode
```

```
✅ Profile: kidifycode
✅ Unit-Classroom (existing)
✅ Scene modes via config
```

---

## Future Expansion (Same Engine)

Once kidifycode works, clone the profile:

- `kidifyai` — AI concepts for kids
- `kidifyscience` — Science stories
- `kidifymath` — Math adventures

**Same renderer. Different prompt style. One engine. Many channels.**

---

## The Only Real Work Remaining

Not more FFmpeg. Not more units.

> **Design the LLM prompt that transforms adult technical topics into kid stories.**

That is the actual next step.**KidfyCode Project Plan**
*AI-Powered Cinematic Coding Education for Kids (Ages 7-12)*

---

## 1. Core Concept
Transform existing Python tutorials into "AI Adventure Classroom" episodes where coding concepts become character-driven missions. Instead of "learning variables," kids help "Byte the Robot" recover his lost memory using "magic memory boxes."

**Key Insight:** Use existing CF2 classroom renderer with a new **profile** (`kidfycode`), not a new unit.

---

## 2. Architecture Strategy
**Decision:** Keep `Unit-Classroom`. Add `kidfycode` profile.

**Configuration Structure:**
```
input/profile/kidfycode.json
```

**Why:** Prevents maintenance hell. One rendering engine powers multiple education channels (coding, AI, math) through profile switches.

---

## 3. Content Transformation Framework

### Concept Mapping (Coding → Story)
| Technical Concept | Kid-Friendly Version | Visual Metaphor |
|---|---|---|
| Variable | Magic Memory Box | Holographic storage container |
| Function | Robot Skill Button | Glowing ability icon |
| Loop | Repeat Spell | Spinning magic circle |
| If/Else | Decision Door | Branching path hologram |
| Bug | Naughty Gremlin | Small monster character |
| API | Robot Telephone | Connection beam |
| Database | Memory Library | Stacked hologram shelves |

### Character Roster (Simplified)
**Teachers:** 2 (Main Teacher + Demo Teacher)  
**Students:** 4 (Curious, Smart, Funny, Beginner)  
*Note: Reduces from 10 voices to 6 for clarity.*

---

## 4. Asset Strategy: "Hologram Reuse"
**Problem:** Old tutorial footage is low quality.  
**Solution:** Repurpose as "classroom projector" content.

**Visual Treatment:**
- Semi-transparent floating screen (75% opacity)
- Cyan glow border + scanlines
- Slight perspective tilt (3-8 degrees)
- Floating/hovering animation

**Usage Modes:**
1. **Floating Screen:** Code appears as hologram beside teacher
2. **Smart Crop:** Show only terminal/code editor section (hides low-res UI)
3. **Pause & Explain:** Teacher freezes old footage, annotates, continues

---

## 5. Episode Structure Template
**Duration:** 5-7 minutes  
**Scene Sequence:**

1. **[HOOK]** Robot/problem introduction (30s)
2. **[MISSION]** Goal stated as story quest (30s)
3. **[SHOW_CODE]** Old tutorial clip plays as hologram (60s)
4. **[MISTAKE]** Bug/gremlin appears, something goes wrong (30s)
5. **[FIX]** Teacher explains concept simply (60s)
6. **[CHALLENGE]** Student predicts output (30s)
7. **[QUIZ]** Quick recap question (30s)

**Script Pattern Example:**
```
[PHASE:hook]
Teacher: Today our robot forgot its favorite fruit.
Student: Can robots forget bananas?

[PHASE:mission]
Teacher: We must teach the robot memory. In Python, that backpack is called a variable.

[PHASE:show_code]
[Hologram clip: x = "banana"]

[PHASE:mistake]
[Robot eats apple instead - wrong value stored]

[PHASE:fix]
Teacher: We simply update the memory box. x = "apple"

[PHASE:challenge]
Teacher: If we store mango, what prints?

[PHASE:quiz]
Teacher: What is a variable?
Student: Memory box!
```

---

## 6. Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
- Create `kidfycode.json` profile
- Define 4 student personalities + 2 teacher voices
- Set hologram overlay parameters (transparency, glow, positioning)
- Create concept mapping dictionary (10 core Python terms)

### Phase 2: Content Pipeline (Week 3-4)
- Build "Kidify Transformer" prompt (converts technical topics to story outlines)
- Tag existing tutorial footage for reuse (identify usable code segments)
- Create 3 test episodes: Variables, Loops, If-Else

### Phase 3: Polish (Week 5-6)
- Add emotional timing (pause before answers, excitement on success)
- Implement "focus mode" (darken background when code appears)
- Test 4-8 second scene rhythm for retention

### Phase 4: Scale (Week 7+)
- Batch process 20 episodes
- Create "KidfyAI" and "KidfyMath" profile variants using same engine

---

## 7. Profile Configuration (kidfycode.json)
**Key Settings:**
- `classroom_mode`: "mission_story"
- `clip_overlay_mode`: "floating_hologram"
- `old_video_reuse`: true
- `code_overlay_mode`: "hologram_terminal"
- `teachers_count`: 2
- `students_count`: 4
- `story_mode`: true
- `quiz_mode`: true
- `pacing`: "fast" (4-8 second scene changes)

---

## 8. Success Metrics
- **Engagement:** 70%+ retention at 3 minutes
- **Learning:** 80%+ correct quiz answers
- **Production:** One 7-minute episode per day (automated pipeline)

---

**Immediate Next Step:** Configure `input/profile/kidfycode.json` with hologram settings and create first test episode using "Robot Memory Box" (Variables) script.
