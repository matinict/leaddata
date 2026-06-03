# 🎬 Unit-Classroom — Project Plan & Development Lifecycle

> **Golden Rule**: Flow controls logic — Units do work — Files store truth — Config defines identity

---

## 🎯 1. Project Vision & Goals

### Core Purpose
Build a **repeatable, interactive learning video engine** for kids (age 6–10) that plugs into the existing CF2 pipeline — same architecture, same assets, only topic changes.

### Strategic Differentiation
| Content Engine | Core Dynamic | Audience | Output |
|---------------|-------------|----------|--------|
| Unit-Debate | Conflict of ideas | Adults/General | Argument video |
| Unit-Podcast | Conversation flow | General | Discussion video |
| **Unit-Classroom** | **Guided learning interaction** | **Kids 6–10** | **Educational dialogue video** |

### Success Metrics
- ✅ Same pipeline reuse (zero new infrastructure)
- ✅ 7-phase structured script template (Hook → Quiz)
- ✅ 2 Teachers + 8 Student personalities (consistent across videos)
- ✅ 60–90s Shorts / 2–3min HD output formats
- ✅ Simple English (grade 3–5), max 12 words per line
- ✅ File-based communication only (no in-memory coupling)

---

## 🏗️ 2. CF2 Architecture Integration

### Unit Positioning
```
src/cf2/units/
  ├── unit_data.py          ← Content provider (LLM only)
  ├── unit_debate.py        ← Debate video renderer
  ├── unit_podcast.py       ← Podcast video renderer
  └── unit_classroom.py     ← NEW: Classroom video renderer ✅
```

### Responsibility Boundary (Rule 4 Compliance)
| Responsibility | Unit-Classroom | Forbidden |
|---------------|---------------|-----------|
| Read input | `topic`, `inputs`, `data.json` | Other unit outputs |
| Generate | `script.md`, `script-m.md`, `audio.mp3`, `video.mp4` | LLM regeneration of content |
| Save to | `.runtime/output/{slug}/classroom/` | Another unit's folder |
| Return | Status string (`done`/`failed`) | In-memory data to next unit |

### Dependency Flow
```
FlowController
     ↓
Unit-Data (if classroom_enabled=true)
     ↓ writes: classroom_script.md, roles.json, quiz.json
     ↓
Unit-Classroom (reads files only)
     ↓ renders: video.mp4 + audio + subtitles
     ↓
Unit-Publisher (if enabled)
```

---

## 🔄 3. Unit Development Lifecycle (7 Phases)

### Phase 1: Specification & Config Design
**Deliverables**
- `data.json` extension: `"Unit-Classroom": true` + `classroom_config` block
- Stop-word list alignment (Rule 36): ensure `slugify()` consistency
- Output naming convention (Rule 33): `{Channel}_{TopicSlug}_Classroom_{Format}_{Lang}.mp4`

**Unique Details**
- Config is control, not logic (Rule 30): switches enable/disable, never contain conditionals
- Append-only config keys (Rule 29): disable via `false`, never delete keys

---

### Phase 2: Character System & Prompt Engineering
**Deliverables**
- Fixed personality prompts for 10 roles (2 Teachers + 8 Students)
- Master prompt template with strict output format (`[SCENE]`, `[QUIZ]`, `[KEY POINTS]`)
- Voice mapping strategy (reuse existing TTS voices, not 8 unique)

**Personality Matrix (No Repetition)**
| Role | Function | Speech Pattern |
|------|----------|---------------|
| T1 (Teacher 1 Male) | Lead explainer | Clear, structured, question-driven |
| T2 (Teacher 2 Female) | Simplifier + example giver | Warm, relatable, real-life analogies |
| S1 Curious | Asks "what/how/why" | Short questions, eager tone |
| S2 Smart | Gives correct answers | Confident, concise |
| S3 Confused | Requests clarification | "I don't understand…", gentle |
| S4 Creative | Offers examples | Imaginative, connects to daily life |
| S5 Funny | Light humor | Playful, brief jokes |
| S6 Doubter | Small disagreement | "But I thought…", not aggressive |
| S7 Quiet | Short meaningful input | 1–2 word insights, impactful |
| S8 Beginner | Basic thinking | Very simple vocabulary |
| S8 Beginner | Basic thinking | Very simple vocabulary |
| S8 Beginner | Basic thinking | Very simple vocabulary |
| S8 Beginner | Basic thinking | Very simple vocabulary |

**Prompt Guardrails**
- Max 12 words per line, grade 3–5 vocabulary
- Each student speaks ≥1 time; 3–5 active per phase
- Teachers never argue; disagreement is light and resolved
- Total script: 60–90s (Shorts) or 2–3min (HD)

---

### Phase 3: Content Engine Template (7-Phase Structure)
**Deliverables**
- Reusable script template with fixed phase order
- Phase-to-clip mapping for video rendering (no new assets)

**Template Structure (Immutable)**
```
[SCENE]
Phase 1: Hook          → Teacher 1 asks curiosity question
Phase 2: Explain       → Teacher 1 explains; S3 confused; Teacher 2 simplifies
Phase 3: Interaction   → S1 asks deeper; S2 answers; S6 doubts; Teacher 1 clarifies
Phase 4: Example       → Teacher 2 gives real-life example; S4 adds creative; S5 adds humor
Phase 5: Reinforcement → S8 asks simple; Teacher 2 re-explains; S7 gives insight
Phase 6: Fun Fact      → Teacher 2 shares "wow" fact; brief reactions
Phase 7: Recap + Quiz  → Teacher 1 summarizes; Teacher 2 asks quiz

[QUIZ]
Question + 3 options (A/B/C)

[KEY POINTS]
3–5 bullet takeaways
```

**Clip Reuse Mapping (Rule: No New Assets)**
| Classroom Phase | Existing Clip Folder | Purpose |
|----------------|---------------------|---------|
| Hook | `p0/` | Opening visual |
| Explanation | `c0/` | Core content display |
| Interaction | `p1/` or `c1/` | Transition + engagement |
| Example | `p2/` or `c2/` | Visual analogy support |
| Reinforcement | `p3/` or `c3/` | Summary visuals |
| Quiz | `sum/` | Recap screen |
| End | `win/` | Closing + subscribe |

---

### Phase 4: Audio & Rendering Strategy
**Deliverables**
- TTS voice assignment map (5 voices max, personality via script not voice)
- Smart skip logic for audio/video generation (Rule 32)
- Idempotent write pattern (Rule 20): safe re-runs

**Audio Strategy**
```
Teacher 1 → Voice A (e.g., en-US-AvaNeural)
Teacher 2 → Voice B (e.g., en-GB-RyanNeural)
Students  → 3 shared voices rotated by personality
            (Curious/Smart = Voice C; Confused/Beginner = Voice D; Funny/Doubter = Voice E)
```

**Rendering Rules**
- Reuse Debate video engine (bottom-to-top text streaming)
- Add speaker labels (`Teacher:`, `S1:`, etc.) via overlay
- No avatars required (Phase 1); optional icon placeholders later
- Output: `video.mp4` + `audio.mp3` + `subtitles.srt` + `cc_en.txt`

---

### Phase 5: File Contract & Meta Tracking
**Deliverables**
- Required output file manifest (Rule D-7)
- `meta.json` status schema for Unit-Classroom
- Lock file integration (Rule 25)

**Required Outputs (Unit-Classroom "done" criteria)**
```
.runtime/output/{TopicSlug}/classroom/
  ├── script.md                 ← Full dialogue
  ├── script-m.md               ← Shorts-compressed version
  ├── roles.json                ← Personality config
  ├── quiz.json                 ← Quiz Q+A
  ├── classroom_video_Shorts.mp4
  ├── classroom_video_HD.mp4
  ├── classroom_audio_Shorts.mp3
  ├── classroom_audio_HD.mp3
  └── classroom_cc_en.txt
```

**Meta Status Schema**
```json
{
  "status": {
    "Unit-Classroom": "pending" | "running" | "done" | "failed"
  },
  "outputs": {
    "classroom_video_Shorts.mp4": "exists" | "missing",
    "classroom_video_HD.mp4": "exists" | "missing"
  }
}
```

---

### Phase 6: Smart Skip & Crash Recovery
**Deliverables**
- Pre-run checks integrated into FlowController (Rule 24)
- Tool-level skip logic (Rule 32)
- Lock file workflow for crash detection

**Skip Decision Tree**
```
IF meta["Unit-Classroom"] == "done"
   AND all required output files exist
   → SKIP unit

IF .lock file present in workspace
   → WARN operator, prompt to resume or reset

ELSE
   → RUN unit, create .lock, update meta to "running"
```

**Recovery Guarantee**
- Re-running pipeline resumes from last successful unit
- No re-generation of existing files (zero waste)
- Partial outputs never treated as final (Rule D-7)

---

### Phase 7: Publisher Integration & Channel Positioning
**Deliverables**
- Unit-Publisher handoff contract (video confirmed `done` in meta)
- Social share metadata template (thumbnail + description)
- Channel branding guidelines for "Interactive Thinking Classroom"

**Publisher Rules (Rule 9)**
- Publishing starts ONLY when `meta.json` confirms video `done`
- Unit-Classroom never touches upload logic
- Thumbnail: reuse existing `generate_thumbnail` output (1920x1080 / 1080x1920)

**Channel Positioning Statement**
> "Not cartoon ABCs. Not passive narration.  
> An AI-powered classroom where kids think, question, and learn through guided dialogue."

---

## 🛡️ 4. Quality Gates & Validation

### Pre-Merge Checks (No Code, Process Only)
| Gate | Criteria | Owner |
|------|----------|-------|
| Prompt Review | All 10 roles have distinct, non-overlapping behavior prompts | Content Lead |
| Config Audit | `data.json` changes are append-only; no deleted keys | Config Owner |
| File Contract | All 9 required outputs documented; naming follows Rule 33 | Dev Lead |
| Skip Logic | Every tool has `if exists: skip` before heavy work | QA Engineer |
| Path Safety | No hardcoded `.runtime/` or `output/` strings; all via `PATHS` | Arch Review |

### Post-Run Validation
- ✅ `meta.json` status matches actual file presence
- ✅ Video duration within target (60–90s Shorts / 2–3min HD)
- ✅ Each student appears ≥1 time in script
- ✅ No line exceeds 12 words; vocabulary grade 3–5
- ✅ Re-run produces identical output (idempotent)

---

## 🚀 5. Launch Criteria

### Minimum Viable Unit-Classroom
- [ ] Unit-Classroom switch functional in `data.json`
- [ ] 7-phase script template generates valid `script.md`
- [ ] Video renderer produces playable MP4 with speaker labels
- [ ] Smart skip prevents duplicate work on re-run
- [ ] Publisher accepts classroom video for upload

### V1 Enhancement Backlog (Post-Launch)
- [ ] Optional avatar icon overlay (static PNG per role)
- [ ] Multi-language subtitle expansion (`cc_{lang}.txt`)
- [ ] Interactive quiz end-card (clickable in YouTube)
- [ ] A/B test: 4-voice vs 5-voice student mapping

---

## 🧭 Final Mental Model

```
User Input (Topic)
       ↓
main.py (3-line router: parse → handoff)
       ↓
flow_controller.py (slug, skip, lock, meta, dispatch)
       ↓
Unit-Classroom (reads files → renders video → writes files)
       ↓
.runtime/output/{TopicSlug}/classroom/ (truth source)
       ↓
Next run or Publisher reads files — never memory
```

> **One-Line Summary**: Flow decides when — Classroom unit teaches how — Files connect all — Config enables scale.



# 👧👦 Student Gender Distribution — Unit-Classroom

> **Guiding Principle**: Personality drives behavior — gender adds natural diversity, not complexity.

---

## 🎯 Recommended Approach: Balanced & Flexible

### Option A: Fixed 4M/4F Split (Recommended for Consistency)
| Student ID | Personality | Gender | Voice Pool | Notes |
|-----------|------------|--------|-----------|-------|
| S1 | Curious | Female | Voice C | Asks "why/how" questions |
| S2 | Smart | Male | Voice C | Quick correct answers |
| S3 | Confused | Female | Voice D | "I don't understand…" |
| S4 | Creative | Male | Voice E | Real-life examples |
| S5 | Funny | Female | Voice E | Light humor, playful |
| S6 | Doubter | Male | Voice D | "But I thought…?" |
| S7 | Quiet | Female | Voice C | Short meaningful insights |
| S8 | Beginner | Male | Voice D | Very simple vocabulary |

**Why this works:**
- ✅ Balanced representation (4 male / 4 female)
- ✅ Voice reuse: only 3 voices (C/D/E) for all 8 students
- ✅ Gender ≠ voice: same voice can be reused across genders via script cues
- ✅ Consistent across all videos → kids recognize patterns

---

## 🔁 Alternative: Topic-Adaptive Rotation

If you want variety without config complexity:

```json
"classroom_config": {
  "student_gender_mode": "balanced_rotation",
  "rotation_seed": "topic_slug_hash"
}
```

**How it works:**
- Gender assignment is deterministic based on topic slug hash
- Same topic always gets same gender distribution
- Different topics get varied distributions
- No manual config needed per topic

**Example:**
| Topic Slug | Hash Mod 8 | Resulting Split |
|-----------|-----------|----------------|
| WhyCloudsFloat | 3 | 5F/3M |
| HowPlantsGrow | 7 | 4F/4M |
| WhatIsGravity | 2 | 6M/2F |

👉 Keeps content fresh while maintaining reproducibility.

---

## 🎙️ Voice Mapping Strategy (Critical for CF2 Compliance)

**Rule**: Personality via script, not voice (Rule 7 + Audio Strategy)

```
Voice Pool for Students (3 voices max):
├─ Voice C (Neutral-Warm): S1-Curious(F), S2-Smart(M), S7-Quiet(F)
├─ Voice D (Soft-Questioning): S3-Confused(F), S6-Doubter(M), S8-Beginner(M)
└─ Voice E (Expressive-Playful): S4-Creative(M), S5-Funny(F)
```

**Implementation Notes:**
- Gender is indicated in script via name/tag, not voice pitch
- Example output format:
  ```
  [S1-F] Curious: Why do clouds float?
  [S2-M] Smart: Because warm air holds them up!
  ```
- TTS engine uses same voice; visual overlay shows gender-appropriate avatar/icon if used later

---

## 🧩 Config Design (Append-Only, Rule 29 Compliant)

Add to `data.json` under `classroom_config`:

```json
"classroom_config": {
  "mode": "2T8S",
  "age_group": "kids_6_10",
  "student_count": 8,
  "gender_distribution": {
    "method": "fixed_balanced",
    "male": ["S2", "S4", "S6", "S8"],
    "female": ["S1", "S3", "S5", "S7"]
  },
  "voice_mapping": {
    "students": {
      "pool_c": ["S1", "S2", "S7"],
      "pool_d": ["S3", "S6", "S8"],
      "pool_e": ["S4", "S5"]
    }
  }
}
```

✅ Keys are appended, never deleted  
✅ No logic in config — only control switches  
✅ FlowController reads, Unit-Classroom executes

---

## 🎬 Visual Identity (Future-Proofing)

When adding avatar icons later (Phase 1 was text-only):

| Element | Implementation |
|--------|---------------|
| Name Tag | `S1-F`, `S2-M` overlay on video |
| Avatar Icon | Simple PNG: 👧/👦 or colored circle + initial |
| Color Code | Female: soft pink/teal • Male: soft blue/orange (gender-neutral palette) |
| Consistency | Same student ID = same icon/color across all videos |

---

## 🚫 What NOT to Do (Anti-Patterns)

| ❌ Avoid | ✅ Do Instead |
|---------|--------------|
| Assign 8 unique TTS voices | Reuse 3 voices via personality scripting |
| Hardcode gender in prompt logic | Define in config, read by Unit |
| Change gender distribution per run | Use deterministic hash or fixed split |
| Use gendered language in rules | Keep prompts neutral; gender is metadata |
| Store gender in memory between units | Write to `roles.json` file (Rule 7) |

---

## 📦 Output Contract Addition

Update Unit-Classroom required outputs (Rule D-7):

```
.runtime/output/{TopicSlug}/classroom/
  ├── roles.json          ← NEW: includes gender + voice mapping
  ├── script.md
  ├── script-m.md
  ├── quiz.json
  ├── classroom_video_*.mp4
  └── ...
```

**roles.json schema:**
```json
{
  "teachers": {
    "T1": { "role": "lead", "gender": "M", "voice": "VoiceA" },
    "T2": { "role": "simplifier", "gender": "F", "voice": "VoiceB" }
  },
  "students": {
    "S1": { "personality": "curious", "gender": "F", "voice_pool": "C" },
    "S2": { "personality": "smart", "gender": "M", "voice_pool": "C" }
    // ... S3-S8
  }
}
```

---

## 💡 Pro Tip: Test with "Gender-Blind" First

Before finalizing:
1. Run Unit-Classroom with gender tags hidden in script
2. Validate that dialogue still feels natural and distinct
3. Then add gender metadata for visual/voice layer

👉 Ensures personality drives engagement, not stereotypes.

---

> **One-Line Summary**: 4 male + 4 female students, mapped to 3 shared voices, defined in append-only config, written to `roles.json` — personality first, gender second, consistency always.

Need me to draft the exact `roles.json` template or the prompt snippet for gender-aware script generation? 👍
