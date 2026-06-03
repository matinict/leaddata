# 🎬 CF2 (CrewAI Factory Flow) — Engineering Rules & Principles

---

## 🧠 CORE PROBLEM (WHY WE ARE REBUILDING)

The old CrewAI system failed because:

- ❌ Too many agents + tasks crammed into one place
- ❌ Manual chaining → impossible to control at scale
- ❌ Repeated execution → wasted time and API cost
- ❌ 1000+ line files → unmaintainable
- ❌ Tight coupling → everything depends on everything

---

## 🎯 CORE GOAL

Build a **Flow-based Modular Pipeline** that is simple, modular, skippable, debuggable, scalable, and multi-channel.

---

## 🔥 GOLDEN PRINCIPLE

> **Flow controls logic — Units do work — Files store truth — Config defines identity**

---

## 🧱 RULES (STRICT ENGINEERING GUIDELINES)

---

### Rule 1 · `main.py` → Router Only

`main.py` must be **dumb and simple**.

**Allowed:**
- Parse CLI arguments / profile flag
- Load config lazily
- Hand off to `flow_controller`

**❌ Forbidden:**
- Business logic
- File handling
- Crew execution
- Any conditional pipeline decisions

```
run --unit Unit-Debate --topic "AI vs Humans"
```

---

### Rule 2 · `flow_controller.py` → Brain of System

ALL logic lives here. This is the sole decision-making authority.

**Responsibilities:**
- Load config and resolve active profile (data.json / data3d.json / etc.)
- Resolve topic: manual string OR auto-pick from queue
- Generate topic slug (see Rule 11)
- Create workspace folder (see Rule 10 + Rule 12)
- Load / update `meta.json`
- Decide RUN vs SKIP for each unit (see Rule 14)
- Dispatch the correct Unit
- Handle errors, retries, and lock management (see Rule 15)

**❌ Forbidden:**
- Actual task execution or video generation
- Direct LLM calls
- Writing output files

---

### Rule 3 · `Unit-*` → Execution Blocks

Each Unit has **ONE responsibility**. Units are the only place real work happens.

**Responsibilities:**
- Read input files
- Call Crew (select agents + tasks dynamically)
- Save outputs to `output/{slug}/`
- Return a status string (`done` / `failed`)

**❌ Forbidden:**
- Cross-unit calls
- Topic resolution or slug generation
- Folder creation logic (that belongs in FlowController)

> **Rule:** Unit does work — Flow decides when.

---

### Rule 4 · `subUnit-*` → Micro Tasks (camelCase)

Small, reusable blocks used inside Units.

```
subUnitYtMetadata    subUnitYtUpload    subUnitFbUpload
subUnitSocialShare   subUnitShorts      subUnitTvc
```

**Rule:** One function = one responsibility. Reusable across units without modification.

---

### Rule 5 · `Unit-Data` → Generator Only (Most Critical)

Unit-Data is the **only** place base content is created. All other units consume what it produces.

**Responsibilities:**
- Generate ALL base data: `.md` debate scripts, `.csv` time-series data, definition `.txt`
- Write output to `output/{slug}/debate/`, `animation/`, `definition/`

**❌ Forbidden:**
- Video generation (any format)
- Upload or social actions
- Depending on any other unit

**Output structure:**
```
output/{TopicSlug}/
  debate/propose.md  oppose.md  decide.md
  definition/def_*.md
  animation/data.csv
  comparison/comparison.md
```

> **Rule:** Generate once — consumed everywhere. Never re-run if files exist.

---

### Rule 6 · Consumer Units → No Data Creation

`Unit-Debate`, `Unit-Animation`, `Unit-Definition`, `Unit-Comparison` are **read-only consumers**.

**Responsibilities:**
- Read `.md` / `.csv` files written by Unit-Data
- Generate video output
- Save to their own subfolder inside `output/{slug}/`

**❌ Forbidden:**
- Calling an LLM to regenerate content
- Writing new `.md` or `.csv` files
- Calling Unit-Data directly

> **Rule:** Consume only — never regenerate.

---

### Rule 7 · `Unit-Publisher` → Distribution Layer

Handles all publishing after video is final. Never touches video creation.

**SubUnits:**
```
subUnitYtMetadata    subUnitYtThumbnail   subUnitYtUpload
subUnitFbUpload      subUnitSocialShare
```

**Rule:** Publishing only starts when content files are confirmed complete in `meta.json`.

---

### Rule 8 · `Unit-Advertise` → Promotion Layer

Creates promotional derivatives from finished videos. Never recreates source content.

**SubUnits:**
```
subUnitShorts    subUnitSocial    subUnitTvc
```

**Rule:** Reuse existing `.mp4` files — never regenerate core content.

---

### Rule 9 · File System → Single Source of Truth

Files are truth. Memory is not.

| File | Truth it holds |
|---|---|
| `debate.md` | Debate script |
| `data.csv` | Animation source data |
| `video.mp4` | Final output |
| `meta.json` | Unit run status |

**❌ Forbidden:**
- Hidden state stored in Python variables between runs
- Recomputing something a file already holds
- Treating in-memory results as authoritative

---

### Rule 10 · Folder Structure → Topic-Based Workspace

```
output/
  EvaFrameworkNew/
    Unit-Data/
    Unit-Debate/
    Unit-Animation/
    Unit-Publisher/
```

> **Rule:** One Topic = One Workspace. Never mix outputs across topics.

---

### Rule 11 · Slug Rule → Predictable PascalCase Naming

- Take the first 3 **meaningful** words of the topic
- Skip stop words (`for`, `the`, `a`, `an`, `is`, `of`, `to`, `in`, `and`)
- Join in PascalCase, no spaces or dashes

**Examples:**
```
"EVA Framework for New Evaluating Voice Agents"  →  EvaFrameworkNew
"Is AI Actually Dangerous?"                       →  IsAiDangerous
"The Future of Work in 2026"                      →  FutureWorkThe   ← skip "The"
```

---

### Rule 12 · Collision Rule → `__01` Suffix System

If the slug folder already exists, **never overwrite**. Append a counter instead:

```
EvaFrameworkNew/
EvaFrameworkNew__01/
EvaFrameworkNew__02/
```

FlowController checks for collision before creating the workspace.

---

### Rule 13 · `meta.json` → Unit State Brain

Every unit's run state is tracked here. FlowController reads it before dispatching anything.

```json
{
  "topic": "EVA Framework for New Evaluating Voice Agents",
  "slug": "EvaFrameworkNew",
  "status": {
    "Unit-Data":      "done",
    "Unit-Debate":    "done",
    "Unit-Animation": "pending",
    "Unit-Publisher": "pending"
  },
  "uploads": {
    "youtube":  "done",
    "facebook": "pending"
  },
  "created_at": "2026-03-30T04:34:33Z",
  "updated_at": "2026-03-30T06:16:46Z"
}
```

**Valid statuses:** `pending` · `running` · `done` · `failed`

> **Rule:** Always trust `meta.json` before running anything.

---

### Rule 14 · Smart Skip → Zero Waste Execution

Before running any unit, FlowController checks:

```
IF meta[unit] == "done"    → SKIP
IF output file exists      → SKIP
IF .lock file present      → WARN + SKIP (possible crash)
ELSE                       → RUN
```

This enables automatic crash recovery — re-running the pipeline continues from where it stopped.

> **Rule:** Never repeat a heavy task that already completed successfully.

---

### Rule 15 · Lock System → Crash Safety

A `.lock` file is created inside the topic folder at run start and deleted on clean exit.

**Purpose:**
- Prevents duplicate parallel runs of the same topic
- Lets FlowController detect a previous crash and warn the operator

> **Rule:** If `.lock` exists at startup, prompt the operator before proceeding.

---

### Rule 16 · Crew → Execution Tool Only

Crew is a dumb executor. Flow tells it exactly what to run.

```python
# ✅ Correct
agents = [factory.debate_video_producer()]
tasks  = [factory.create_debate_video()]
factory.crew().kickoff(agents=agents, tasks=tasks, inputs=inputs)

# ❌ Wrong
factory.crew().kickoff()  # runs everything blindly
```

**❌ Forbidden:**
- Running the full crew without explicit agent/task selection
- Mixing unrelated tasks in one kickoff call

---

### Rule 17 · Function Design → 50–80 Lines Max

- Single responsibility per function
- No nested conditional chaos
- Helper functions are preferred over long methods
- If a function exceeds 100 lines, it must be split

**❌ Forbidden:** 1000-line god functions. Mixed logic inside a single method.

---

### Rule 18 · Unit Independence → File Interface Only

Units **never call each other**. The only allowed dependency between units is reading files from `output/{slug}/`.

```
# ✅ Correct
with open(f"output/{slug}/debate/propose.md") as f:
    text = f.read()

# ❌ Wrong
from cf2.units.unit_data import run as run_data
run_data(topic, inputs)   # Unit calling another Unit
```

---

### Rule 19 · Config Profile → One File Per Channel

`data.json` is the base config. Channel-specific overrides contain **only differing keys**.

```
data.json          ← default channel (PlayOwnAi)
data3d.json        ← 3D debate channel (360Debate)
datasports.json    ← sports channel
dataBn.json        ← Bengali language override
```

FlowController deep-merges the profile on top of `data.json`. No duplication of shared keys.

---

### Rule 20 · Execution → One Unit at a Time

Units run sequentially. FlowController never chains them automatically unless explicitly configured.

```bash
crewai run --unit Unit-Data     --topic "EVA Framework"
crewai run --unit Unit-Debate   --topic "EVA Framework"
crewai run --unit Unit-Publisher --topic "EVA Framework"
```

---

### Rule 21 · `flow_controller.py` is the ONLY entry into units  *(New)*

No external script, test file, or manual call may invoke a Unit directly. All unit execution goes through FlowController. This preserves skip logic, lock management, and meta tracking for every run.

```
# ✅ Always via FlowController
flow_controller.run(unit="Unit-Debate", topic="EVA Framework")

# ❌ Never call a unit directly
from cf2.units.unit_debate import run
run(topic, inputs)
```

---

### Rule 22 · Output Naming Convention → Predictable File Names  *(New)*

All final output files follow this strict pattern so downstream units and upload tools can locate them without scanning:

```
{Channel}_{TopicSlug}_{Format}_{LangSuffix}.mp4

# Examples
PlayOwnAi_EvaFrameworkNew_Shorts_En.mp4
PlayOwnAi_EvaFrameworkNew_HD_En.mp4
360Debate_IsAiDangerous_Shorts_Bn.mp4
```

Intermediate files (silent video, raw audio) use tool-internal prefixes (`debate_video_`, `bar_race_`, `intro_`) and are **never** treated as final deliverables.

---

### Rule 23 · No Hardcoded Values in Tools  *(New)*

All configurable values — LLM model, channel name, video format, TTS voice, year range, max chars — must come from `data.json` passed through `inputs`. Tools must accept them as parameters, not embed them as string literals.

```python
# ✅ Correct
model = inputs.get("llm_debate", "claude-sonnet-4-20250514")

# ❌ Wrong
model = "claude-sonnet-4-20250514"   # hardcoded
```

---

### Rule 24 · Smart Skip is Mandatory in Every Tool  *(New)*

Every tool's `_run()` method must check for its own final output file before doing any work. This is not optional.

```python
if os.path.exists(final_output_path):
    return f"⏭️ Skipped — already exists: {final_output_path}"
```

The check must happen before any LLM call, TTS generation, or video render.

---

### Rule 25 · `data.json` is Append-Only for Keys  *(New)*

Keys are never removed from `data.json` — they are disabled by setting their master switch to `false`. This preserves backward compatibility and avoids crashes when old configs are reused.

```json
// ✅ Correct: disable by switch
{ "debate": false }

// ❌ Wrong: delete the debate block entirely
```

---

## 🗂️ FINAL STRUCTURE REFERENCE

```
src/cf2/
  main.py               ← Router only
  flow_controller.py    ← All logic
  meta.py               ← meta.json helpers
  units/
    unit_data.py
    unit_debate.py
    unit_definition.py
    unit_animation.py
    unit_publisher.py
    unit_advertise.py
  crews/
    crew.py             ← Tool registry + agent/task factory
    config/
      agents.yaml
      tasks.yaml
  tools/
    *.py                ← One tool per file, smart skip mandatory

output/
  {TopicSlug}/
    debate/
    definition/
    animation/
    YT/
    .lock
    meta.json
```

---

## 🚀 FINAL STATEMENT

> You are not building a script — you are building a **production pipeline**.
>
> Every decision you make should answer: *"Does this make the system simpler, more skippable, and easier to debug?"*
> If the answer is no, reconsider.
