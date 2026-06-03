# 🎬 CF2 (CrewAI Factory Flow) — Complete Engineering Rules

> **Each token counts. No fluff. Every rule is enforceable.**

---

## 📑 INDEX

- **Section 1 — Flow Rules**
  - Rule 1 · `main.py` → Router Only · `flow_controller.py` → Brain of System
  - Rule 2 · One Unit Per Execution
- **Section 2 — Unit Rules**
  - Rule 3 · `Unit-*` → Execution Blocks · `subUnit-*` → Micro Tasks (camelCase)
  - Rule 4 · `subUnit-*` → Pure Functions (Reusable Micro-Tasks)
- **Section 3 — Unit-Data Rules (Critical)**
  - Rule 5 · Unit-Data is a Provider, Never a Consumer · Unit-Data Never Calls Itself
  - Rule 6 · Unit-Data is Never Called Directly · Task Selection Controlled by Unit Switches Only
  - Rule 7 · Core Tasks Always Run · Consumer-Specific Tasks Only Run for Enabled Units · Output Files Are the Contract
- **Section 4 — Consumer Unit Rules**
  - Rule 8 · Consumer Units → Read-Only
  - Rule 9 · `Unit-Publisher` → Distribution Layer Only
  - Rule 10 · `Unit-Advertise` → Promotion Layer Only
- **Section 5 —  Core `Service` ,LLM & others Rules**
  - Rule 11 · Core Services → tts, ffmpeg, audio, video, 3d, hologram, clips
  - Rule 12 · Core Others / Utility Elements
  - Rule 13 · Centralized LLM Config
- **Section 6 — Crew / Agent Rules**
  - Rule 14 · Crew → Execution Tool Only
  - Rule 15 · Factory Pattern Only
  - Rule 16 · Task = Single Output
- **Section 7 — File System Rules**
  - Rule 17 · File System → Single Source of Truth
  - Rule 18 · Folder Structure → Topic-Based Workspace
  - Rule 19 · No Hardcoded Paths
  - Rule 20 · Idempotent Writes
  - Rule 39 · `.runtime/` → System-Only Directory
- **Section 8 — Meta / Control Rules**
  - Rule 21 · Slug Rule → Predictable PascalCase Naming
  - Rule 22 · Collision Rule → `__01` Suffix System
  - Rule 23 · `meta.json` → Unit State Brain
  - Rule 24 · Smart Skip → Zero Waste Execution
  - Rule 25 ·  executor.py is the Boss  Lock System → Crash Safety
  - Rule 26 · `flow_controller.py` is the ONLY Entry Into Units
- **Section 9 —All Config Rules**
  - Rule 27 · Topics , Focus , profile → One File Per Channel
  - Rule 28 · `unit_config.json` is units config
  - Rule 29 · except Config ,No Hardcoded Values in py code  
  - Rule 30 · Config = Control, Not Logic (Schema-Enforced)
- **Section 10 — Code Quality Rules**
  - Rule 31 · Function Design → 50–80 Lines Max
  - Rule 32 · Smart Skip is Mandatory in Every Tool
  - Rule 33 · Output Naming Convention → Predictable File Names
- **Section 11 — System Config  Rules (`config.py`)**
  - Rule 34 · `config.py` is a Re-Export Layer — No Logic Allowed
  - Rule 35 · `PATHS` Dict → Canonical Key Names Only
  - Rule 36 · `slugify()` Stop-Word List is Canonical
  - Rule 37 · `resolve_config_paths()` → Routing Logic is Fixed
  - Rule 38 · `read_meta()` Must Not Use Collision Slug for Existing Topics
- **Section 12 — Anti-Patterns (Enforce Zero Tolerance)**
  - Rule 39 · Banned Anti-Patterns — Zero Exceptions
  - Rule 40 · Final Mental Model

---

## 🧠 CORE PROBLEM (Why We Rebuilt)

The old CrewAI system failed because:
- ❌ Too many agents + tasks crammed into one place
- ❌ Manual chaining → impossible to control at scale
- ❌ Repeated execution → wasted time & API cost
- ❌ 1000+ line files → unmaintainable
- ❌ Tight coupling → everything depends on everything
- ❌ Units → one unit fails Entire system failures
- ❌ Units → already 12+ units not insist new unit
- ❌ subUnits → no limits add/remove

---

## 🎯 CORE GOAL

Build a **Flow-based Modular Pipeline** that is simple, modular, skippable, debuggable, scalable & multi-channel.

---

## 🔥 GOLDEN PRINCIPLE

> **Flow controls logic — Units do work — Files store truth — Config defines identity**

---

## 🏗️ Final Structure Reference

```
src/cf2/
  main.py                  ← Router only (dumb)
  flow_controller.py       ← All logic lives here
  meta.py                  ← meta.json read/write helpers
  dependency_resolver.py   ← Auto-triggers Unit-Data if inputs missing
  units/
    unit_data.py
    unit_debate.py
    unit_definition.py
    unit_animation.py
    unit_comparison.py
    unit_publisher.py
    unit_advertise.py
  crews/
    crew.py                ← Tool registry + agent/task factory
    config/
      agents.yaml
      tasks.yaml
  tools/
    *.py                   ← One tool per file, smart skip mandatory

.runtime/             ← machine-managed, never committed to git
  logs/
  secrets/
  cache/
  output/             ← all topic workspaces live here
    {TopicSlug}/
      debate/
      definition/
      animation/
      comparison/
      YT/
      .lock
      meta.json
```

---

# 🧩 SECTION 1 — FLOW RULES

## Rule 1 · Universal main,FlowController , Topic & units  responsibilities

**Principle:** `main.py` routes → `flow_controller` decides → Topic is normalized once → Units execute consistently
- no redundancy, no structure break

---

## Rule 1.a · `main.py` → Router Only (Dumb & Simple)

`main.py` must be **dumb & simple**. The single test: delete everything except `from cf2.flow_controller import run` — if the system still works, the router is clean.

**✅ Allowed:**
- Parse CLI arguments / profile flag
- Hand off to `flow_controller.run()`

**❌ Forbidden:**
- Business logic of any kind
- File / meta / state access (`load_meta`, `check_output_folder`, `read_csv`)
- Crew or agent calls
- Conditional flow decisions (`if unit == "debate": ...`)
- Multi-unit execution (`run("Unit-Data"); run("Unit-Debate")`)
- Error handling / retry logic (belongs in FlowController)
- Config or env loading (`load_dotenv`, `read_yaml`)
- Parameter transformation (`argv[1].lower().replace(...)`)
- Any import except the single flow entry point

```python
# ✅ Entire main.py
from cf2.flow_controller import run

def kickoff():
    run()

# ❌ Wrong — infinite recursion (existing bug to fix)
def plot():
    plot()
```

**CLI usage:**
```bash
uv run crewai run --unit Unit-Debate --topic "AI vs Humans"
```

---

## Rule 1.b · `flow_controller.py` → Brain of System (All Logic Lives Here)

`flow_controller.py` is the **sole decision-making authority**. ALL logic lives here.

**Responsibilities:**
- Load config & resolve active profile (`data.json` / `data3d.json` / etc.)
- Validate config against schema (fail fast on structural errors)
- Resolve topic: manual string OR auto-pick from queue OR YouTube reference
- Normalize topic into standard structure (→ Rule 1.c)
- Generate topic slug (→ Rule 21)
- Create workspace folder (→ Rule 18, Rule 22)
- Load / update `meta.json` (→ Rule 23)
- Decide RUN vs SKIP for each unit (→ Rule 24)
- Dispatch the correct Unit (→ Rule 26)
- Handle errors, retries & lock management (→ Rule 25)

**❌ Forbidden:**
- Actual task execution or video generation
- Direct LLM calls
- Writing output files

---

## Rule 1.c · Topic is Normalized Once (Universal Topic Structure)

FlowController MUST normalize `topic` into a **standard structure** so ALL units behave consistently. Normalization happens **once** in FlowController — never repeated in units.

### ✅ Accepted Inputs

```json
"topic": "Cancun hotels, Punta Cana resorts"
```

```json
"topic": "auto"
```

```json
"topic": "yt:VIDEO_ID"
```

```json
"topic": {
  "primary": "Cancun hotels",
  "secondary": ["Punta Cana resorts"],
  "intent": "comparison"
}
```

### 🔄 Mandatory Normalization

All inputs MUST become:

```json
{
  "topic": {
    "primary": "string | null",
    "secondary": [],
    "intent": "general | auto | comparison | reference",
    "source": "manual | auto | youtube"
  }
}
```

### 🔧 Normalization Logic (FlowController Only)

```python
t = inputs.get("topic")

if t == "auto":
    topic = {
        "primary": None,
        "secondary": [],
        "intent": "auto",
        "source": "auto"
    }

elif isinstance(t, str) and t.startswith("yt:"):
    topic = {
        "primary": t.replace("yt:", ""),
        "secondary": [],
        "intent": "reference",
        "source": "youtube"
    }

elif isinstance(t, str):
    parts = [x.strip() for x in t.split(",") if x.strip()]
    topic = {
        "primary": parts[0],
        "secondary": parts[1:] if len(parts) > 1 else [],
        "intent": "comparison" if len(parts) > 1 else "general",
        "source": "manual"
    }

elif isinstance(t, dict):
    topic = {
        "primary": t.get("primary"),
        "secondary": t.get("secondary", []),
        "intent": t.get("intent", "general"),
        "source": t.get("source", "manual")
    }

else:
    raise ValueError(f"Invalid topic format: {t}")

# Inject normalized topic back into inputs
inputs["topic"] = topic
inputs["_topic"] = topic["primary"]  # backward compatibility
```

---

## Rule 1.d · Units Execute Consistently (Topic Contract)

All Units MUST use the normalized topic structure. No unit may parse or interpret topic independently.

### ✅ Correct Usage in Units

```python
# Primary topic (always use this)
topic = inputs["topic"]["primary"]

# Optional: secondary topics for comparison
secondary = inputs["topic"]["secondary"]
intent = inputs["topic"]["intent"]
source = inputs["topic"]["source"]
```

### ❌ Forbidden in Units

- Using raw string topic: `topic = inputs["topic"]` (when not normalized)
- Parsing topic differently per unit: `topic.split(",")` inside a unit
- Assuming topic format: `if "vs" in topic: ...`
- Re-normalizing topic inside a unit (already done in FlowController)

### 📌 Topic Contract Enforcement

```python
# ✅ Correct — Unit reads normalized topic
def run(inputs: dict) -> str:
    topic = inputs["topic"]["primary"]
    if not topic:
        return "skipped — no topic provided"

    # proceed with execution
    ...

# ❌ Wrong — Unit assumes raw string
def run(inputs: dict) -> str:
    topic = inputs["topic"]  # might be dict, might be string
    if "," in topic:         # assumes string format
        parts = topic.split(",")
```

---

## 🔥 Final Principle

> **main.py routes → FlowController decides → Topic is normalized once → Units execute consistently**

This ensures:
- ✅ Universal topic handling across ALL units
- ✅ No unit breaks due to input variation
- ✅ Clean separation of responsibilities
- ✅ Single source of truth for topic structure
- ✅ Fully aligned with CF2 architecture



## Rule 2 · One Unit Per Execution

Only ONE unit runs per command. FlowController never chains units automatically unless a dependency resolver triggers Unit-Data for missing inputs (→ Rule D-2).

```bash
uv run crewai run --unit Unit-Data
uv run crewai run --unit Unit-Debate
uv run crewai run --unit Unit-Publisher
```

**❌ Forbidden:**
- Running multiple units in a single `kickoff()` call
- Automatic cross-unit chaining in FlowController

---


# 🧱 SECTION 2 — UNIT & SUBUNIT RULES (Pure Engineering Rules)

> **Units are isolated execution blocks. SubUnits are reusable pure functions.**

---

## 📐 ARCHITECTURAL PRINCIPLES

### Golden Rule of Separation

```
Flow (Orchestrator)
  ↓ dispatches
Unit (Execution Block)
  ↓ orchestrates
SubUnit (Pure Function)
  ↓ performs
Atomic Task
```

**Never invert this hierarchy.**

---

## Rule 3 · `Unit-*` → Execution Blocks (Complete Isolation)

### 3.1 · Definition

A Unit is an **isolated execution block** that:
- Every unit mus be disabled, only enabled flag make it enabled
- Has exactly ONE responsibility
- Runs independently (can be removed without breaking others)
- Communicates ONLY via files
- Returns ONLY a status string
- Never crashes the pipeline
- No hardcode Adding or removed any unit on Pipeline like flow_controller executor

---

### 3.2 · Unit Responsibility Matrix

Each Unit owns exactly one stage:

| Unit | Single Responsibility | Input Contract | Output Contract |
|------|----------------------|----------------|-----------------|
| `Unit-Scout` | Discover trending topics | Config (platforms, niches) | `topic_queue.json` |
| `Unit-Data` | Generate base content via LLM | Topic string, config | `.md`, `.csv`, `.txt` files |
| `Unit-LeadData` | Generate lead generation data | Topic, target audience | Lead database files |
| `Unit-Debate` | Render debate video | `propose.md`, `oppose.md`, `decide.md` | `debate_video_*.mp4` |
| `Unit-Prodcast` | Create podcast audio/video | Debate scripts OR custom script | `prodcast_*.mp3`, `prodcast_*.mp4` |
| `Unit-Classroom` | Educational video for children | Topic definition text | `classroom_*.mp4` |
| `Unit-Animation` | Render animated bar-race charts | `data.csv` | `bar_race_*.mp4` |
| `Unit-Definition` | Scrolling definition video | `definition.txt` | `definition_video_*.mp4` |
| `Unit-Comparison` | Comparison visualization video | `comparison.md` | `comparison_*.mp4` |
| `Unit-Packaging` | Generate metadata & thumbnails | Final videos (any format) | YT metadata, CC files, thumbnails |
| `Unit-Publisher` | Upload to distribution platforms | Videos + metadata + thumbnails | YouTube/Facebook video IDs |
| `Unit-Advertise` | Create promotional derivatives | Final published videos | Social posts, Shorts cuts, TVC |

**Enforcement:** A Unit that does TWO items from this table must be split.

---

### 3.3 · Unit Signature (Mandatory)

Every Unit MUST follow this exact signature:

```python
def run(
    topic: str,      # ← The subject being processed
    workspace: Path, # ← Absolute path to .runtime/output/{slug}/
    inputs: dict,    # ← Complete merged config (validated)
    force: bool      # ← Override smart skip
) -> str:           # ← Returns: "done" | "failed" | "skipped"
```

**Violations:**
- ❌ Adding extra parameters
- ❌ Returning anything except status string
- ❌ Raising unhandled exceptions
- ❌ Side effects outside workspace

---

### 3.4 · Mandatory Unit Behaviors (The Contract)

Every Unit MUST implement these four behaviors:

#### **Behavior 1 — Input Validation**
- Check required input files exist BEFORE execution
- Return `"skipped"` if inputs missing (NOT crash)
- Log what was missing for debugging

#### **Behavior 2 — Output Isolation**
- Write ONLY to own subfolder: `.runtime/output/{slug}/{unit_name}/`
- NEVER write to another unit's folder
- NEVER write to workspace root
- NEVER write to shared config files

#### **Behavior 3 — Safe Failure**
- Catch ALL exceptions inside Unit
- Log error with full traceback
- Return `"failed"` (NOT raise)
- Pipeline must continue to next Unit

#### **Behavior 4 — Idempotent Execution (Smart Skip)**
- Check if final output already exists
- Skip heavy work if output valid
- Respect `force=True` flag to override
- Log skip reason clearly

---

### 3.5 · Forbidden Unit Behaviors (Zero Tolerance)

| Forbidden Action | Why Banned | Violation of |
|------------------|-----------|--------------|
| Import from another Unit | Creates hidden dependency chain | Rule 3 (Isolation) |
| Return data instead of status | Breaks file-based communication | Rule 3 (Communication) |
| Call another Unit's `run()` | Creates cascading execution | Rule 2 (One Unit Per Execution) |
| Generate topic slug | FlowController's responsibility | Rule 26 (Entry Point) |
| Create workspace folder | FlowController's responsibility | Rule 26 (Entry Point) |
| Modify `inputs` dict | Global state mutation | Rule 4 (No Side Effects) |
| Write to `input/` directory | Config is read-only | Rule 27 (Config Profile) |
| Read from `.runtime/cache/` | Cache is tool-internal only | Rule 39 (Runtime Structure) |
| Change working directory | Pollutes global process state | Rule 19 (No Hardcoded Paths) |
| Raise unhandled exception | Crashes entire pipeline | Rule 4 (Safe Failure) |
| Execute another Unit conditionally | Flow logic in wrong layer | Rule 2 (FlowController Authority) |
| Access environment variables directly | Config must be explicit | Rule 28 (No Hardcoded Values) |

---

### 3.6 · File-Based Communication (The ONLY Interface)

**The Contract:**
- Units NEVER call each other
- Units NEVER share memory
- Units NEVER pass Python objects
- Units communicate ONLY by reading/writing files

**Valid Communication Pattern:**
```
Unit-Data writes:     .runtime/output/{slug}/debate/propose.md
                                    ↓
Unit-Debate reads:    .runtime/output/{slug}/debate/propose.md
```

**Invalid Communication Patterns:**
```
❌ Unit-Debate imports Unit-Data
❌ Unit-Data returns text to Unit-Debate
❌ Unit-Debate calls Unit-Data.regenerate()
❌ Shared global variable between Units
```

---

### 3.7 · File Ownership Rules

Each Unit owns EXACTLY its own output folder:

```
.runtime/output/{slug}/
  ├── debate/        ← Unit-Debate ONLY
  ├── definition/    ← Unit-Definition ONLY
  ├── animation/     ← Unit-Animation ONLY
  ├── prodcast/      ← Unit-Prodcast ONLY
  ├── classroom/     ← Unit-Classroom ONLY
  ├── packaging/     ← Unit-Packaging ONLY (metadata, thumbnails)
  ├── uploads/       ← Unit-Publisher ONLY (upload logs)
  └── advertise/     ← Unit-Advertise ONLY (social derivatives)
```

**Forbidden Actions:**
- ❌ Unit-Debate writing to `animation/`
- ❌ Unit-Publisher modifying files in `debate/`
- ❌ Unit-Packaging deleting files from `prodcast/`
- ❌ Any Unit writing to workspace root (except FlowController)

---

### 3.8 · Unit Isolation Checklist (Pre-Merge Validation)

Before ANY Unit code is merged to main branch, verify:

- [ ] Signature matches: `run(topic, workspace, inputs, force) -> str`
- [ ] No imports from `cf2.units.*` (except in tests)
- [ ] No workspace creation logic
- [ ] No topic/slug generation
- [ ] No modification of `inputs` dict
- [ ] All exceptions caught and logged
- [ ] Returns only: `"done"` | `"failed"` | `"skipped"`
- [ ] Smart skip implemented (checks existing output)
- [ ] Writes ONLY to own subfolder
- [ ] No hardcoded paths (uses `workspace` parameter)
- [ ] No hardcoded config values (uses `inputs` parameter)
- [ ] No direct LLM calls (uses factory pattern)
- [ ] No cross-unit file reads (reads only from predecessor's output)

---

## Rule 4 · `subUnit-*` → Pure Functions (Reusable Micro-Tasks)

### 4.1 · Definition

A SubUnit is a **stateless pure function** that:
- Performs exactly ONE atomic task
- Takes explicit parameters (no globals)
- Returns a concrete result (not status string)
- Has NO side effects on parent Unit
- Can be called from MULTIPLE Units

---

### 4.2 · SubUnit vs Unit (Critical Distinction)

| Aspect | **Unit** | **SubUnit** |
|--------|---------|-------------|
| **Nature** | Execution block (state machine) | Pure function (stateless) |
| **Signature** | Fixed: `run(topic, workspace, inputs, force) -> str` | Custom: any params → any return type |
| **Called by** | FlowController ONLY | Multiple Units |
| **File I/O** | Reads/writes workspace directly | NO direct I/O (caller provides paths) |
| **State** | Owns workspace subfolder | Completely stateless |
| **Error handling** | MUST catch all exceptions | MAY raise exceptions (caller catches) |
| **Return value** | Status string only | Actual result (Path, dict, str, int, etc.) |
| **Reusability** | One-per-pipeline-stage | Many-per-pipeline |
| **Example** | `Unit-Publisher` orchestrates upload pipeline | `subUnitYtUpload` uploads ONE video |
| **Responsibility scope** | Full stage (orchestration) | Single task (atomic operation) |
| **Config access** | Reads from `inputs` dict | Receives values as parameters |
| **Can fail pipeline** | NO (returns `"failed"`) | NO (Unit catches its exceptions) |

---

### 4.3 · SubUnit Naming Convention (Strict)

**Function name:** `subUnit{TaskName}` (camelCase, always starts with `subUnit`)

**File location:** `src/cf2/tools/{category}_{task}.py`

**Examples:**
```
subUnitYtMetadata      → src/cf2/tools/packaging_yt_metadata.py
subUnitYtUpload        → src/cf2/tools/publisher_yt_upload.py
subUnitFbUpload        → src/cf2/tools/publisher_fb_upload.py
subUnitSocialShare     → src/cf2/tools/advertise_social_share.py
subUnitShorts          → src/cf2/tools/advertise_shorts.py
subUnitTvc             → src/cf2/tools/advertise_tvc.py
subUnitLinkedInPost    → src/cf2/tools/advertise_linkedin.py
```

**Violation:** A SubUnit in `units/` folder instead of `tools/`

---

### 4.4 · SubUnit Design Rules (The Contract)

#### **Rule 4.4.1 — Pure Function Signature**

**Required:**
- Explicit parameters (no hidden dependencies)
- Clear return type annotation
- No global variable access
- No environment variable reading

**Examples:**

✅ **CORRECT:**
```python
def subUnitYtMetadata(
    slug: str,
    workspace: Path,
    video_style: str,
    channel: str
) -> dict:
    """Returns: {"title": str, "description": str, "tags": list}"""
```

❌ **WRONG:**
```python
def subUnitYtMetadata():  # ← No parameters, reads globals
    from config import SLUG  # ← Hidden dependency
    return generate_metadata()
```

---

#### **Rule 4.4.2 — Single Responsibility**

One SubUnit = One Atomic Task

✅ **CORRECT:**
```python
subUnitYtUpload(video_path, metadata) -> video_id
subUnitFbUpload(video_path, description) -> fb_video_id
subUnitLinkedInPost(post_text, image_url) -> post_id
```

❌ **WRONG:**
```python
subUnitUploadEverywhere(video_path):  # ← Multiple tasks
    upload_to_youtube()
    upload_to_facebook()
    post_to_linkedin()
    send_email_notification()
```

**Split into:** 4 separate SubUnits

---

#### **Rule 4.4.3 — No Side Effects**

SubUnits must NOT:
- Write files directly (return data, caller writes)
- Modify input parameters (immutable contract)
- Change global state
- Access shared resources without parameters

✅ **CORRECT:**
```python
def subUnitShorts(
    source_video: Path,
    start_time: float,
    duration: float
) -> bytes:  # ← Returns video data, caller saves it
    return cut_video_bytes(source_video, start_time, duration)
```

❌ **WRONG:**
```python
def subUnitShorts(source_video: Path):
    output_path = Path("output/shorts.mp4")  # ← Hardcoded path
    output_path.write_bytes(cut_video())     # ← Direct file write
```

---

#### **Rule 4.4.4 — Reusable Across Units**

A SubUnit must work when called from ANY Unit without modification.

**Test:** Can this SubUnit be used in 3+ different Units?

✅ **CORRECT (Reusable):**
```python
# Can be called from Unit-Publisher, Unit-Advertise, Unit-Packaging
def subUnitYtMetadata(slug: str, style: str, lang: str) -> dict:
    return {"title": f"{slug} - {style}", ...}
```

❌ **WRONG (Tied to One Unit):**
```python
# Only works in Unit-Debate due to hidden dependency
def subUnitYtMetadata():
    from cf2.units.unit_debate import get_debate_context
    context = get_debate_context()  # ← Tight coupling
```

---

### 4.5 · SubUnit Categories (Organizational Principle)

Group SubUnits by the Unit family they primarily serve:

| Category | SubUnits | Serves Units |
|----------|----------|--------------|
| **Data Generation** | `subUnitCsvGenerate`, `subUnitMarkdownFormat` | Unit-Data, Unit-LeadData |
| **Packaging** | `subUnitYtMetadata`, `subUnitYtThumbnail`, `subUnitCcGenerate` | Unit-Packaging |
| **Publishing** | `subUnitYtUpload`, `subUnitFbUpload`, `subUnitYtCcUpload` | Unit-Publisher |
| **Social Media** | `subUnitSocialShare`, `subUnitLinkedInPost`, `subUnitTwitterPost` | Unit-Advertise |
| **Video Derivatives** | `subUnitShorts`, `subUnitTvc`, `subUnitClipExtract` | Unit-Advertise |
| **Audio Processing** | `subUnitTtsGenerate`, `subUnitAudioMerge`, `subUnitAudioNormalize` | Multiple (Debate, Prodcast, Classroom) |
| **Validation** | `subUnitFileValidate`, `subUnitMetaValidate`, `subUnitConfigValidate` | FlowController, Multiple Units |

**Rule:** A SubUnit in wrong category signals misplaced responsibility.

---

### 4.6 · How Units Compose SubUnits (Orchestration Pattern)

**The Pattern:**
- Unit = Orchestrator (decides what/when)
- SubUnit = Executor (does how)

**Example Structure:**

```
Unit-Publisher:
  ├── Validate inputs (Unit logic)
  ├── Call subUnitYtMetadata (SubUnit)
  ├── Call subUnitYtUpload (SubUnit)
  ├── Call subUnitFbUpload (SubUnit)
  ├── Call subUnitSocialShare (SubUnit)
  └── Return "done" (Unit logic)
```

**Key Points:**
- Unit decides execution order
- Unit handles errors from SubUnits
- Unit passes workspace-derived data to SubUnits
- Unit writes SubUnit results to files
- SubUnits remain unaware of pipeline context

---

### 4.7 · Forbidden SubUnit Patterns (Anti-Patterns)

| Anti-Pattern | Why Banned | Correct Alternative |
|--------------|-----------|---------------------|
| SubUnit calls another SubUnit | Creates hidden call chain | Unit orchestrates both |
| SubUnit reads `inputs` directly | Hidden dependency | Unit passes values as parameters |
| SubUnit writes files | Side effect | Return data, Unit writes |
| SubUnit imports from Unit | Circular dependency | Keep SubUnits in `tools/` |
| SubUnit accesses workspace | State dependency | Unit passes specific paths |
| SubUnit does 3+ tasks | Violates single responsibility | Split into 3 SubUnits |
| SubUnit has conditional logic for different Units | Knows too much | Split into specialized SubUnits |
| SubUnit uses `print()` | No structured logging | Unit logs SubUnit results |

---

### 4.8 · SubUnit Validation Checklist (Pre-Merge)

Before ANY SubUnit is merged:

- [ ] Function name starts with `subUnit` (camelCase)
- [ ] Located in `src/cf2/tools/` (not `units/`)
- [ ] All parameters explicitly typed
- [ ] Clear return type annotation
- [ ] No global variable access
- [ ] No direct file I/O (returns data instead)
- [ ] No hardcoded values (all via parameters)
- [ ] No imports from `cf2.units.*`
- [ ] Can be called from 2+ different Units
- [ ] Single atomic task only
- [ ] Raises exceptions (doesn't return status strings)
- [ ] Documented with docstring (params + return)

---

## 🎯 Decision Tree: Unit vs SubUnit

### **Create a Unit when:**
- ✅ It's a new pipeline stage with its own config block
- ✅ It needs its own workspace subfolder
- ✅ It's controlled by a `Unit-*` boolean switch
- ✅ It orchestrates multiple tasks
- ✅ Example: "Unit-Transcript" for video transcription

### **Create a SubUnit when:**
- ✅ It's a helper for existing Units
- ✅ It performs one specific atomic task
- ✅ Multiple Units need the same operation
- ✅ It's a pure function with no state
- ✅ Example: "subUnitTranscriptUpload" for uploading transcripts

### **DON'T create a Unit when:**
- ❌ Existing SubUnits can handle it
- ❌ It's a variation (use config parameter instead)
- ❌ It duplicates another Unit's responsibility
- ❌ It has no workspace output folder

### **DON'T create a SubUnit when:**
- ❌ It needs to orchestrate multiple steps (make it a Unit)
- ❌ It needs to own workspace state (make it a Unit)
- ❌ It's only used once (inline in Unit instead)

---

## 🔥 Production Stability Guarantees

Following these rules ensures:

| Failure Mode | Before Rules | After Rules |
|--------------|--------------|-------------|
| **Adding new Unit breaks old ones** | ❌ Happened frequently | ✅ Impossible (isolation) |
| **Failed Unit stops entire pipeline** | ❌ Entire system crashed | ✅ Returns `"failed"`, continues |
| **Missing input files crash system** | ❌ Unhandled exceptions everywhere | ✅ Graceful `"skipped"` with logs |
| **Hard to trace which Unit failed** | ❌ Cryptic stack traces | ✅ Clear status in `meta.json` |
| **Upgrading one Unit is risky** | ❌ Fear of breaking everything | ✅ Safe (no dependencies) |
| **Can't run Units independently** | ❌ Must run full pipeline | ✅ Single-Unit execution works |
| **SubUnits tied to specific Units** | ❌ Code duplication everywhere | ✅ Reused across pipeline |
| **SubUnit changes break multiple Units** | ❌ Cascading failures | ✅ Isolated to one Unit at a time |

---

## 📏 Enforcement Mechanism

### **Automated Checks (CI/CD):**
- Unit signature validator (fails build if signature wrong)
- Import scanner (fails if Unit imports another Unit)
- File write analyzer (fails if Unit writes outside its folder)
- Exception handler checker (fails if unhandled exceptions)

### **Manual Code Review Checklist:**
- Every Unit PR: Run isolation checklist (3.8)
- Every SubUnit PR: Run validation checklist (4.8)
- Any cross-Unit change: Rejected automatically
- Any hardcoded config: Rejected automatically

### **Runtime Enforcement:**
- FlowController validates Unit return values
- FlowController catches Unit exceptions
- FlowController logs all status transitions
- Meta.json tracks Unit-level state

---

**End of Section 2 — No code, pure rules.**




# 🔥 SECTION 3 — UNIT-DATA RULES (CRITICAL)
## Rule 5 · Unit-Data is a Provider, Never a Consumer · Unit-Data Never Calls Itself

    Unit-Data reads NOTHING from other units. It reads only `topic`, `inputs` (config) & `data.json`. It writes only to `.runtime/output/{slug}/` subfolders.

    ```
    ❌ unit_data.py reads any .md or .mp4 from workspace
    ✅ unit_data.py writes .md, .csv, .txt to .runtime/output/{slug}/
    ```

    No retry loop, no recursive fallback, no self-kickoff. If it fails, it marks `failed` in `meta.json` & stops. FlowController decides whether to re-run.

    ---

## Rule 6 · Unit-Data is Never Called Directly · Task Selection Controlled by Unit Switches Only

    Only two callers are legal:
    1. `FlowController` (full pipeline or `--unit Unit-Data`)
    2. `dependency_resolver` (when a consumer's input files are missing)

    ```python
    # ❌ Never — unit calling a unit
    from cf2.units.unit_data import run as run_data
    run_data(topic, inputs)

    # ✅ Always via FlowController or dependency_resolver
    flow_controller.run(unit="Unit-Data", topic="EVA Framework")
    ```

    Unit-Data reads `inputs["Unit-Debate"]`, `inputs["Unit-Definition"]` etc. It NEVER reads nested config keys like `debate_enabled` or `definition_video_enabled`.

    ```python
    # ✅ Correct
    debate_on = inputs.get("Unit-Debate", False)

    # ❌ Wrong — nested config sub-key
    debate_on = inputs.get("debate_enabled", False)
    ```

---

## Rule 7 · Core Tasks Always Run · Consumer-Specific Tasks Only Run for Enabled Units · Output Files Are the Contract

      `data_research` & `data_generate_csv` run on every execution regardless of any unit switch. They are the non-negotiable foundation.

      ```python
      # Always — no guard
      agents += [factory.data_researcher()]
      tasks  += [factory.data_research()]
      agents += [factory.data_csv_generator()]
      tasks  += [factory.data_generate_csv()]
      ```

      If a unit is disabled, its data is never generated. This prevents wasted LLM calls & partial file states.

      | Task group           | Guard                                            |
      |----------------------|--------------------------------------------------|
      | Definition text      | `Unit-Definition == true`                        |
      | Debate scripts       | `Unit-Debate == true`                            |
      | Debate short scripts | `Unit-Debate == true` & `debate_short == true` |
      | Comparison data      | `Unit-Comparison == true`                        |

      Unit-Data is only `done` when its required output files **physically exist**. `meta.json` status alone is not sufficient.

      **Minimum required output:**
      ```
      .runtime/output/{TopicSlug}/
        debate/propose.md   oppose.md   decide.md
        definition/def_*.md
        animation/data.csv
        comparison/comparison.md
      ```

      **❌ Forbidden:**
      - Video generation (any format)
      - Audio or TTS
      - Upload or social actions
      - Depending on any other unit

      > **Generate once — consumed everywhere. Never re-run if files exist.**

    ---






# 📺 SECTION 4 — CONSUMER UNIT RULES

## Rule 8 · Consumer Units → Read-Only

`Unit-Debate`, `Unit-Animation`, `Unit-Definition`, `Unit-Comparison` are **read-only consumers**.

**Responsibilities:**
- Read `.md` / `.csv` files written by Unit-Data
- Generate video output
- Save to their own subfolder inside `.runtime/output/{slug}/`

**❌ Forbidden:**
- Calling an LLM to regenerate content
- Writing new `.md` or `.csv` files
- Calling Unit-Data directly

> **Consume only — never regenerate.**

---

## Rule 9 · `Unit-Publisher` → Distribution Layer Only

Handles all publishing after video is confirmed final in `meta.json`. Never touches video creation.

**SubUnits:**
```
subUnitYtMetadata    subUnitYtThumbnail   subUnitYtUpload
subUnitFbUpload      subUnitSocialShare
```

**Rule:** Publishing only starts when content files are confirmed `done` in `meta.json`.

---

## Rule 10 · `Unit-Advertise` → Promotion Layer Only

Creates promotional derivatives from finished videos. Never recreates source content.

**SubUnits:**
```
subUnitShorts    subUnitSocial    subUnitTvc
```

**Rule:** Reuse existing `.mp4` files — never regenerate core content.



# 🤖 SECTION 5 — Core `Service`, Utility, LLM & Others Rules

## Rule 11 · Core Services → tts, ffmpeg, audio, video, 3d, hologram, clips

**Location:** `src/cf2/core/services/`

**Standard:**
- Services are **stateless wrappers only**. They do one technical job: generate TTS, run ffmpeg, merge audio/video, render 3D, build clips.
- No business logic, no prompt building, no unit-specific decisions inside a service.
- All methods must be **idempotent** with smart-skip: if output exists, return True immediately. Do not re-process.
- All methods must be **damage-contained**: catch exceptions internally, log, return False. Never raise to crash the pipeline. One failed task must not affect other tasks or units.
- Resource safety required: use timeouts, nice/ionice, process groups. Kill hung subprocesses cleanly.
- No hardcoded paths, voices, bitrates, or limits. Everything comes from caller inputs.
- Services receive a logger, they do not create global loggers.

**Current services:**
- `tts_service.py` — unified gTTS, Edge, Piper
- `ffmpeg_service.py` — safe ffprobe, concat, mix, shorts limit
- `audio_service.py` — merge, atempo, concatenate, duration

> All new core media services must follow this same contract.

---

## Rule 12 · Core Others / Utility Elements

**Location:** `src/cf2/core/` (outside services)

**Standard:**
- These are shared, optional helpers. They must never hold unit state.
- Includes: `config_loader.py`, `paths.py`, `utils.py`, `logging_setup.py`, `progress_tracker.py`, `dependency_resolver.py`, `clip_resolver.py`, `topic_resolver.py`, `weak_words.py`, `registry.py`, `executor.py`
- Sub-packages: `compress/`, `parser/`, `subtitle/`, `tts/providers/`

**Rules:**
- Single responsibility per file. No cross-imports that create circular dependencies.
- Config-driven only. No hardcoded defaults in code.
- Fail-safe by design: return safe defaults (0.0, {}, False) on error, log warning, continue pipeline.
- Must be import-safe and testable in isolation.

---

## Rule 10 · Core Service Isolation Rule

This is the damage-free principle for both Rule 11 and Rule 12:

1. **Task-level isolation:** If any core service or utility fails, only that task fails. The executor marks it failed, logs structured error, pipeline continues.
2. **No shared mutable state:** Services are instantiated per task, not as singletons holding data.
3. **Timeouts everywhere:** ffmpeg, TTS, network calls must have hard timeouts. No blocking calls.
4. **Smart skip is mandatory:** Check file existence first to make retries safe and SaaS-cost efficient.
5. **Observability:** Every service logs: start, skip, success, failure, duration, model/tool used. No silent failures.

> Protect other units at all costs. A failure in TTS must not break video merging. A failure in ffmpeg must not break LLM execution.

---

## Rule 13 · Centralized LLM Config

**LLM RULES — with fallback, reliability & production safety**

### A · Only ONE place holds LLM configuration

`input/llm_conf.json`

```json
"llm_config": {
  "default": "deepseek/deepseek-chat",
  "fallback": [
    "dashscope/qwen-plus",
    "openai/gpt-4o"
  ],
  "temperature": 0.7
}
```

**Runtime behavior:**
- Try `default` first
- On failure (API outage, rate limit, timeout, invalid response) → retry in order through `fallback` list
- Stop on first successful response
- Log which model succeeded and whether fallback was triggered

**Benefits:** Prevents pipeline failure from single-provider issues. Enables multi-provider resilience.

**❌ Forbidden:**
- `llm_*` keys duplicated inside unit-specific config blocks
- Hardcoded model strings anywhere in code
- Embedding fallback logic inside tools or units

> All model selection and fallback must be config-driven.

### B · Agent-Based LLM Mapping

```json
"agents": {
  "debater": "deepseek/deepseek-chat",
  "judge": "dashscope/qwen-plus",
  "data_researcher": "deepseek/deepseek-chat"
}
```

**Enhancements:**
- Mapping is per-agent role, NOT per-task, NOT per-unit
- Each agent inherits `default` and `fallback` chain from `llm_config` automatically
- Optional override supported:

```json
"agents": {
  "debater": {
    "primary": "deepseek/deepseek-chat",
    "fallback": ["dashscope/qwen-plus"]
  }
}
```

**Runtime:** Resolve agent → model → apply fallback chain → maintain consistent output style per agent.

**Benefits:** Stable behavior, controlled variability, agent-level tracing for debugging.

### C · No Direct LLM Calls

All LLM calls must go through the factory agent pattern.

```python
# ❌ Forbidden
openai.chat(...)
anthropic.messages.create(...)

# ✅ Correct
factory.agent()
```

**Execution layer must provide:**
- Retry mechanism (2 to 3 attempts for transient failures)
- Automatic fallback handling using `llm_config.fallback`
- Timeout control to prevent blocking pipeline
- Structured logging (model used, fallback triggered, latency, status)
- Deterministic input/output contract (validated prompt structure, validated response format)

**❌ Forbidden:**
- Direct SDK usage in Units, Tools, or FlowController
- Manual retry loops inside tools
- Custom fallback logic outside centralized LLM layer

---

### 🔥 Operational Principle

> **LLM access must be centralized, observable, retryable and replaceable. Services must be stateless, idempotent and damage-contained.**

This gives you a fault-tolerant pipeline, multi-provider resilience, clean separation of config vs execution, and a production-ready SaaS core where one failing task never kills the whole flow.








# 🏗️ SECTION 6 — CREW / AGENT RULES

## Rule 14 · Crew → Execution Tool Only

Crew is a dumb executor. Flow tells it exactly what to run. Never run the full crew blindly.

```python
# ✅ Correct — explicit selection
agents = [factory.debate_video_producer()]
tasks  = [factory.create_debate_video()]
factory.crew().kickoff(agents=agents, tasks=tasks, inputs=inputs)

# ❌ Wrong — blind execution
factory.crew().kickoff()
```

**❌ Forbidden:**
- Running the full crew without explicit agent/task selection
- Mixing unrelated tasks in one kickoff call

---

## Rule 15 · Factory Pattern Only

All agents & tasks must come from `CF2Crew()`. No inline agent or task definitions anywhere else.

```python
# ✅ Correct
factory.debater()
factory.data_researcher()

# ❌ Wrong — inline definition
Agent(role="debater", goal="...", backstory="...")
```

---

## Rule 16 · Task = Single Output

Each task produces exactly ONE file. Multi-output tasks & hidden outputs are forbidden.

---

# 📁 SECTION 7 — FILE SYSTEM RULES

## Rule 17 · File System → Single Source of Truth

Files are truth. Memory is not.

| File         | Truth it holds        |
|--------------|-----------------------|
| `propose.md` | Propose debate script |
| `data.csv`   | Animation source data |
| `video.mp4`  | Final output          |
| `meta.json`  | Unit run status       |

**❌ Forbidden:**
- Hidden state stored in Python variables between runs
- Recomputing something a file already holds
- Treating in-memory results as authoritative

---

## Rule 18 · Folder Structure → Topic-Based Workspace

All topic workspaces live under `.runtime/output/`. Because `.runtime/` is never committed to git, all generated content is automatically excluded from version control with a single `.gitignore` entry.

```
.runtime/output/
  EvaFrameworkNew/
    debate/
    definition/
    animation/
    comparison/
    YT/
    .lock
    meta.json
  EvaFrameworkNew__01/
    ...
```

> **One Topic = One Workspace. Never mix outputs across topics.**

---

## Rule 19 · No Hardcoded Paths

All paths must be resolved through config or a central `PATHS` constant, never as string literals scattered in code.

```python
# ✅ Correct
from config import PATHS
path = PATHS["output"] / slug / "debate" / "propose.md"

# ❌ Wrong — literal string, breaks when output root moves
path = f".runtime/output/{slug}/debate/propose.md"
```

---

## Rule 20 · Idempotent Writes

Running a unit twice must NOT break or corrupt output. Every write either overwrites safely or skips if the file already exists (→ Rule 24).

---

## Rule 39 · `.runtime/` → System-Only Directory

`.runtime/` is a machine-managed directory. Never committed to version control & never accessed by Units via hardcoded path strings. Only `cf2.core.paths` resolves paths into it & only the  layer (`config.py`) exposes them via `PATHS`.

```
.runtime/
  output/    ← all topic workspaces (was output/ at project root)
  logs/      ← execution logs (flow_controller, units)
  secrets/   ← OAuth tokens, API keys, client_secret*.json
  cache/     ← temporary intermediate data (never treated as final output)
```

Moving `output/` inside `.runtime/` means a single `.gitignore` entry (`/.runtime/`) excludes all generated content — logs, secrets, cache & every rendered video.

**Ownership rules:**

| Subdirectory        | Who writes                          | Who reads                          |
|---------------------|-------------------------------------|------------------------------------|
| `.runtime/output/`  | Units (via tool `_run()`)           | Consumer units + publisher         |
| `.runtime/logs/`    | FlowController + Units (via logger) | Operator / debug tooling only      |
| `.runtime/secrets/` | Operator (manual placement)         | `resolve_config_paths()` only      |
| `.runtime/cache/`   | Tools (intermediate work)           | Same tool on next run (skip logic) |

**❌ Forbidden:**
- Any Unit or tool importing a `.runtime/` path as a string literal
- Committing `.runtime/` contents to git
- Treating `.runtime/cache/` files as final deliverables or referencing them in `meta.json`
- Placing secret files anywhere outside `.runtime/secrets/`
- Using `OUTPUT_ROOT` pointing to the old project-root `output/`

```python
# ✅ Correct — always via PATHS
workspace   = PATHS["output"] / slug
secret_path = PATHS["secrets"] / "pai_token.json"

# ❌ Wrong — hardcoded, breaks on any path restructure
workspace = f"output/{slug}"
workspace = f".runtime/output/{slug}"
```

> **All generated content lives in `.runtime/`. Nothing in `.runtime/` is ever source-controlled.**

---

# 🔄 SECTION 8 — META / CONTROL RULES

## Rule 21 · Slug Rule → Predictable PascalCase Naming

Take the first 3 **meaningful** words of the topic. Skip stop words (`for`, `the`, `a`, `an`, `is`, `of`, `to`, `in`, `and`). Join in PascalCase with no spaces or dashes.

```
"EVA Framework for New Evaluating Voice Agents"  →  EvaFrameworkNew
"Is AI Actually Dangerous?"                       →  IsAiDangerous
"The Future of Work in 2026"                      →  FutureWork2026
```

---



## Rule 22 · Collision Rule → `__01` Suffix System

    **Purpose:**
    Prevent overwriting existing work **and avoid unnecessary API calls**

    ---

    ### Core Principle

    * Do **NOT** create `__01` automatically when a slug exists
    * Always **check existing workspace first**

    ---

    ### Correct Flow

    ```text
    User → topic
          ↓
    Generate slug (AiDangerous)
          ↓
    Check: does workspace exist?
    ```

    #### Case 1 — New Topic

    * Slug does NOT exist
      → Create new workspace
      → `AiDangerous/`

    #### Case 2 — Workspace Exists + All Files Present

    * All required files exist
      → Reuse workspace
      → **Smart Skip (NO API call)**

    #### Case 3 — Workspace Exists + Files Missing

    * Some required files missing
      → Reuse workspace
      → Generate only missing files (**partial run**)

    #### Case 4 — User Requests New Version

    * `--force` or explicit request
      → Create new version
      → `AiDangerous__01/`

    ---

    ### When to Create `__01`

    Create a new folder ONLY when:

    * User explicitly requests a new version
    * Force flag is enabled

    ```text
    AiDangerous/
    AiDangerous__01/
    AiDangerous__02/
    ```

    ---

    ### Required Files Check (Example)

    ```python
    required = [
        "debate/propose.md",
        "debate/oppose.md",
        "debate/decide.md",
    ]

    if all((workspace / f).exists() for f in required):
        return "skipped"   # ✅ No API call
    ```

    ---

    ### FlowController Logic (Mandatory)

    ```python
    if slug_exists:
        if required_files_exist:
            reuse_slug            # ✅ no API call
        else:
            generate_missing      # ✅ partial API
    else:
        create_slug              # new topic
    ```

    ---

    ### Key Rules

    * Reuse first, generate later
    * Never overwrite existing work
    * Never call LLM if files already exist
    * Only create `__01` for intentional regeneration

    ---

    ### 🔥 Final Principle

    > **Reuse > Partial Run > New Version**
    > *(Cost efficiency comes before duplication)*

    ---

    This version removes redundancy, keeps logic tight, and directly enforces **zero-waste API behavior**.


## Rule 23 · `meta.json` → Unit State Brain

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

> **Always trust `meta.json` before running anything. But verify output files too (→ Rule D-7).**

---

## Rule 24 · Smart Skip → Zero Waste Execution

Before running any unit, FlowController checks in this order:

```
IF meta[unit] == "done"    → SKIP
IF output file exists      → SKIP
IF .lock file present      → WARN + prompt operator (possible crash)
ELSE                       → RUN
```

Smart Skip is also **mandatory inside every tool** (→ Rule 28). This enables automatic crash recovery — re-running the pipeline resumes from where it stopped.

> **Never repeat a heavy task that already completed successfully.**

---

## Rule 25 · executor.py is the Boss  Lock System → Crash Safety

### 🔒 Core Principle

> **One lock. One boss. One place.**

The lock system exists in **one place only**: `executor.py`.

No unit, no sub-unit, no service, no helper may touch the lock.

---

### 🎯 Purpose

| Purpose | Description |
|---------|-------------|
| **Crash Detection** | If `.lock` exists at startup → previous run crashed |
| **Duplicate Prevention** | Prevents two parallel runs on the same topic |
| **Operator Safety** | Warns human before proceeding after crash |
| **State Trust** | If lock exists → meta.json may be corrupt or incomplete |

---

### 🏗️ Architecture

```
executor.py
 ├── acquire_lock()     ← ONLY place lock is created
 ├── run_unit_internal()
 │    └── runner.run()  ← unit just does work, zero lock awareness
 └── release_lock()     ← ONLY place lock is released
```

---

### ✅ Rules (Absolute, No Exceptions)

### Rule 25.1 — executor.py is the ONLY lock owner

```
✅ executor.py     → acquire_lock()
✅ executor.py     → release_lock()

❌ unit_dubbing.py → acquire_lock()   FORBIDDEN
❌ meta.py         → acquire_lock()   outside executor context FORBIDDEN
❌ crop_service.py → acquire_lock()   FORBIDDEN
❌ Any sub-unit    → acquire_lock()   FORBIDDEN
```

If you are writing lock code outside `executor.py`:

**You are doing it wrong.**

---

### Rule 25.2 — Lock Lifecycle

```
startup
  │
  ├── .lock exists?
  │     ├── YES → 🚨 Crash Detected (see Rule 25.4)
  │     └── NO  → proceed normally
  │
  ├── acquire_lock()    ← executor.py creates .lock
  │
  ├── runner.run()      ← unit executes, NO lock awareness
  │
  └── release_lock()    ← executor.py deletes .lock (finally block)
```

---

### Rule 25.3 — Lock Must Always Release

Lock release must be in a `finally` block.

```python
lock = acquire_lock(workspace, unit)
if lock is None:
    return None

try:
    result = runner.run(...)
finally:
    release_lock(lock)   # ✅ ALWAYS runs even on crash/exception
```

**No try without finally when a lock is held.**

---

### Rule 25.4 — Crash Detection Protocol

If `.lock` file exists at startup:

```
🚨 CRASH DETECTED

Previous run of '{unit}' on '{topic}' did not complete cleanly.

Options:
  [R] Resume  — trust existing stage checkpoints, continue from last done stage
  [F] Force   — wipe all stages, start fresh
  [A] Abort   — do nothing, exit safely

Operator choice: _
```

**Auto-behavior (non-interactive mode):**

```python
if lock_age > 300:   # 5 minutes = definitely stale
    auto_clean()
    proceed()
else:
    warn_and_abort()
```

---

### Rule 25.5 — Stale Lock Cleanup

A lock older than **5 minutes** is automatically considered stale.

```python
def cleanup_stale_locks(workspace: Path, max_age_seconds: int = 300):
    lock_file = workspace / ".lock"
    if lock_file.exists():
        age = time.time() - lock_file.stat().st_mtime
        if age > max_age_seconds:
            lock_file.unlink(missing_ok=True)
            print(f"  🧹 Stale lock cleaned (age={age:.0f}s)")
```

This runs at:
- Start of `run_unit()` (before dep resolution)
- Only when `force=False`

When `force=True`:
- All locks wiped immediately (no age check)

---

### Rule 25.6 — Per-Unit Lock Scope

Each unit gets its own lock.

```
.runtime/output/ClassesPython/
├── .lock              ← workspace-level lock
└── dubbing/
    └── (no lock here) ← sub-stages NEVER have locks
```

Locks are workspace-level only.  
Sub-stages use **meta subtask status** for coordination.  
Not locks.

---

### Rule 25.7 — Units Are Lock-Unaware

Units receive work.  
Units do work.  
Units report result.

```python
# ✅ CORRECT — unit_dubbing.py
def run(topic, workspace, inputs, force):
    # Just do the work
    # No lock. No acquire. No release.
    return "done"
```

```python
# ❌ WRONG — unit_dubbing.py
def run(topic, workspace, inputs, force):
    lock = acquire_lock(...)   # NEVER DO THIS
    ...
```

---

### Rule 25.8 — Sub-Stages Use Meta, Not Locks

For stage-level coordination inside a unit:

```
✅ Use: mark_subtask(workspace, unit, stage, "done")
✅ Use: should_skip_dubbing_stage(workspace, stage)
✅ Use: meta["subtasks"][unit][stage]

❌ Never: acquire_lock() inside a stage
❌ Never: .lock files inside dubbing/ or any subdirectory
```

---

### Rule 25.9 — Lock File Format

Lock file contains audit trail:

```
Unit-Dubbing | 2025-01-15T10:23:45.123456+00:00
```

Always:
- Unit name
- ISO timestamp (UTC)
- Written atomically on acquire
- Deleted on release

---

## 🧠 Why This Rule Exists

### Before Rule 25 (Broken State)

```
executor.py  → acquire_lock()  ← fd #1 locked
  unit_dubbing.py → acquire_lock()  ← fd #2 → FAILS (same process!)
    🔒 "locked by another process"   ← self-locked!
      → Pipeline aborts
        → Zero work done
          → Infinite confusion 😵
```

### After Rule 25 (Correct State)

```
executor.py → acquire_lock()   ← fd #1 locked
  unit_dubbing.py → just works  ← no lock attempt
    ✅ Pipeline runs cleanly
      ✅ Files created
        ✅ Meta updated
          ✅ Done 🚀
```

---

## 📋 Compliance Checklist

Before shipping any unit or service:

```
□ No acquire_lock() calls outside executor.py
□ No release_lock() calls outside executor.py
□ No .lock file creation in any sub-directory
□ Lock held in try/finally block in executor.py
□ Stale lock cleanup runs at startup
□ Crash detection implemented
□ Unit run() function has zero lock awareness
```

---

## 🔥 One Sentence Summary

> `executor.py` acquires the lock, runs the unit, releases the lock.
> The unit just does the work.
> Everything else is a bug.


---

## Rule 26 · `flow_controller.py` is the ONLY Entry Into Units

No external script, test file, or manual call may invoke a Unit directly. All unit execution goes through FlowController. This preserves skip logic, lock management & meta tracking for every run.

```python
# ✅ Always via FlowController
flow_controller.run(unit="Unit-Debate", topic="EVA Framework")

# ❌ Never call a unit directly
from cf2.units.unit_debate import run
run(topic, inputs)
```

---

# ⚙️ SECTION 9 — All Config Rules inside INPUT_DIR {Topics , Focus , profile & units ..}

> **Config defines identity — Flow controls logic — Units execute work → Tools/Core**

-  All rules only For input/*.json file Rules
-  Topics is mediatory input configure field without this system not start_time , its can not empty
-  Focus is optional supporting for Topics right direction , its can empty
-

---

## Rule 27 · Topics , Focus & profile Rules

    data/data3d.json Config Profile → One File Per Channel
    * Keys defined in `data.schema.json` must **never be removed**
    * Disable features using **existing boolean switches only**
    * `data.json` = **base configuration (single source of truth)**
    * Profile configs override **only existing schema keys**
    * No structure drift allowed beyond `data.schema.json`

    **Files:**

    ```text
    input/
      data.json        ← base
      data3d.json      ← overrides (e.g. debate_3d_enabled)
      datasports.json  ← overrides
      dataBn.json      ← overrides (e.g. audio_lang)
    ```

    **Merge Logic (Schema-Safe):**

    ```python
    final_config = deep_merge(data.json, profile.json)
    ```

    **Constraints (Strict):**

    * Override only keys that already exist in schema
    * Preserve full schema shape after merge
    * Nested overrides must match exact structure

    **Valid override scope:**

    * Top-level: `video_fps`, `tts_engine`, `channel`
    * Nested: `scout_config`, `animation_config`, `debate_config`

    **❌ Forbidden:**

    * Adding new keys not defined in `data.schema.json`
    * Changing structure (e.g. object → list, object → null)

    > **Profiles customize values — never redefine structure**

    ---

## Rule 28 · unit_config  `input/unit/unitName_config.json` is Append-Only main/default (Schema-Safe)

      * All  unit config will be inside here input/unit/
      * no units data inside data/data3d.json except   "Unit-":true/ false,
      * if need unit can extends another config must be include unit config

        **Correct:**
        ```json
        { "Unit-Debate": false }
        ```
        **❌ Wrong:**

        ```json
        { "debate_config": null }        
        ```

        ### Sub-rule · Config Stability

        * `_config` blocks ALWAYS exist
        * Units ignore config when master switch = false
        * No conditional deletion of config blocks

        > **Schema stability > config cleanliness**

        ---

## Rule 29 · Except Configure ,No Hard coded Values anywhere  py code

    * Config is authoritative: if key exists → use it exactly
    * Fallbacks are **safety-only**, never behavioral overrides
    * Every fallback must be **observable (loggable)**

    **All values must come from config (`inputs`)**

    **Schema-driven examples:**

    * `llm_debate`
    * `video_fps`
    * `tts_engine`
    * `audio_speed`, `audio_speed_hd`
    * `debate_config.debate_secs_per_line`
    * `animation_config.intro_duration`

    ```python
    # ✅ Correct
    fps = inputs.get("video_fps")
    debate_speed = inputs.get("debate_config", {}).get("debate_secs_per_line")

    # ❌ Wrong
    fps = 30
    ```

    ### Sub-rule · Fallback Behavior (Strict)

    Fallback is allowed ONLY when:

    * Key is missing
    * Asset is missing
    * External dependency fails

    Fallback must:

    1. Use schema-aligned default OR safe base resource
    2. Never introduce new logic branches
    3. Be logged for operator visibility

    > **Fallback prevents failure — never changes intent**

    ---



## Rule 30 · Config = Control, Not Logic (Schema-Enforced)

    Config maps **only to schema fields**

    **✅ Valid:**

    ```json
    {
      "Unit-Debate": true,
      "debate_config": {
        "debate_secs_per_line": 3.5,
        "debate_max_chars": 1000
      }
    }
    ```

    **❌ Invalid (logic):**

    ```json
    {
      "fast_mode_when_shorts": true
    }
    ```

    **❌ Invalid (derived behavior):**

    ```json
    {
      "debate_config": {
        "use_fast_speed_if_short": true
      }
    }
    ```

    ---

    ### 🔒 Schema Alignment Rules (Critical)

    1. Every key MUST exist in `data.schema.json`
    2. Structure must match exactly (no shape mutation)
    3. Unit execution controlled ONLY by:

       ```
       Unit-Debate
       Unit-Animation
       Unit-Definition
       Unit-Comparison
       Unit-Packaging
       Unit-Publisher
       Unit-Advertise
       ```
    4. `_config` blocks = parameters only (never execution control)



    > **Schema defines structure · Config fills values · Flow controls execution · Units consume config**

    ---

    ## Sub-section · Asset Fallback System (Critical Improvement)

    This part was good but scattered—now made **system-level & enforceable**.

    ### Sub-rule · Universal Clip Fallback

    All clip/image resolution MUST support automatic fallback:

    **Priority order:**

    ```
    1. Exact match (e.g. p3_s.mkv)
    2. Base clip   (e.g. p3.mkv)
    3. Default set (p0 / c0)
    ```


    """
    Universal clip fallback with 3-tier priority:
    1. Exact match (e.g. int7s_s.mkv)
    2. Base clip   (e.g. int7s.mkv)
    3. Default     (e.g. p0/c0 fallback)
    """

    ### Sub-rule · Minimal Key Guarantee

    If clip keys are missing:

    * System MUST fallback to:

      ```
      p0 for host/propose
      c0 for guest/oppose
      ```
    * Segment builder modulo logic guarantees reuse:

    ```python
    host_keys[h_idx % len(host_keys)]
    ```

    → Single fallback key = infinite safe loop

    ---

    ### Sub-rule · Zero Manual Intervention

    **Strict rule:**

    * NO manual copy commands (`cp`)
    * NO asset duplication hacks
    * NO runtime fixes by operator

    > If a file is missing → system resolves it automatically

    ---

    ### Sub-rule · Smart Suffix Fallback

    Inside `_ensure_clip_exists`:

    **Behavior:**

      1. Check suffixed file (`*_s.mkv`)
      2. If missing → strip suffix
      3. Check base file
      4. If exists → use base
      5. Else → fallback to p0/c0

    ---

    ### Sub-rule · Absolute Path Guarantee

    All resolved assets MUST:

    * Return absolute paths
    * Never depend on relative resolution
    * Prevent renderer “Clip Missing” errors

    ---

    ### Sub-rule · Intro Safety Guard

    * If intro clip fails resolution (even after fallback):
      → Skip intro segment entirely

    **Reason:**

    * Avoid black frames
    * Avoid broken timelines

    ---

    ### Sub-rule · System Responsibility Boundary

    | Responsibility          | Owner                |
    | ----------------------- | -------------------- |
    | Clip existence handling | Tool (clip resolver) |
    | Fallback logic          | Tool                 |
    | Execution decision      | Flow                 |
    | Config values           | Config               |

    > **Tools must be self-healing — not operator-dependent**

    ---

    ## Final Principle (Refined)

    > **Config defines what should happen
    > Fallback ensures it still runs
    > Flow decides when
    > Tools guarantee execution without failure**

    ---





# 🔧 SECTION 10 — CODE QUALITY RULES

## Rule 31 · Function Design → 50–80 Lines Max

- Single responsibility per function
- No nested conditional chaos
- Helper functions preferred over long methods
- If a function exceeds 100 lines, it must be split

**❌ Forbidden:** 1000-line god functions. Mixed responsibilities inside a single method.

---

## Rule 32 · Smart Skip is Mandatory in Every Tool

Every tool's `_run()` method must check for its own final output file **before** doing any work. Not optional — must run before any LLM call, TTS generation, or video render.

```python
if os.path.exists(final_output_path):
    return f"⏭️ Skipped — already exists: {final_output_path}"
```

---

## Rule 33 · Output Naming Convention → Predictable File Names

All final output files follow this strict pattern so downstream units & upload tools can locate them without scanning the folder:

```
{Channel}_{TopicSlug}_{Format}_{LangSuffix}.mp4

PlayOwnAi_EvaFrameworkNew_Shorts_En.mp4
PlayOwnAi_EvaFrameworkNew_HD_En.mp4
360Debate_IsAiDangerous_Shorts_Bn.mp4
```

Intermediate files use tool-internal prefixes (`debate_video_`, `bar_race_`, `intro_`) & are **never** treated as final deliverables.

---

# 🔌 SECTION 11 — CONFIG  RULES (`config.py`)

`config.py` is a **compatibility  only**. It exists so legacy imports like `from config import PATHS, slugify` keep working. It must never grow into a logic layer.

## Rule 34 · `config.py` is a Re-Export Layer — No Logic Allowed

All real implementations live in their canonical modules. `config.py` only re-exports them.

```
cf2.core.paths         → path constants + topic workspace helpers
cf2.core.config_loader → profile loading + deep-merge
cf2.meta               → meta.json read/write/lock
```

```python
# ✅ Correct — thin re-export
from cf2.core.paths import OUTPUT_ROOT, get_topic_dir

# ❌ Wrong — logic in the
def get_topic_dir(slug):
    if not slug:
        slug = "default"   #  is now making decisions
    return OUTPUT_ROOT / slug
```

---

## Rule 35 · `PATHS` Dict → Canonical Key Names Only

The `PATHS` dict exposes exactly these keys & no others. All code that needs a base directory imports from `PATHS` — never constructs the path itself.

```python
PATHS = {
    "root"   : PROJECT_ROOT,              # repo root
    "input"  : INPUT_DIR,                 # input files
    "output" : RUNTIME_PATHS["output"],   # .runtime/output/
    "logs"   : RUNTIME_PATHS["logs"],     # .runtime/logs/
    "secrets": RUNTIME_PATHS["secrets"],  # .runtime/secrets/
    "cache"  : RUNTIME_PATHS["cache"],    # .runtime/cache/
}
```

Adding undocumented keys to `PATHS` without updating this rule is a violation.

---

## Rule 36 · `slugify()` Stop-Word List is Canonical

The authoritative stop-word set lives in `cf2.core.topic_resolver`. The copy in `config.py` exists only for backward compatibility & must stay **identical**. If the stop-word list changes, both files must be updated together.

```python
# Canonical stop words — do not diverge between config.py & topic_resolver.py
_STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "is", "are", "was", "were", "be", "by", "from", "with", "as",
    "if", "can", "will", "should", "would", "could", "have", "has", "had",
}
```

Slug max length is capped at **60 characters**. This must be consistent across all callers.

---

## Rule 37 · `resolve_config_paths()` → Routing Logic is Fixed

`resolve_config_paths()` resolves `*_file` keys in the inputs dict to absolute paths. The routing priority is fixed & must not be changed without updating this rule:

```
1. Already absolute path        → leave untouched
2. Starts with "input/"         → PROJECT_ROOT / value
3. Matches a secret pattern     → .runtime/secrets/ basename
4. Anything else                → INPUT_DIR / basename
```

Secret patterns: `client_secret`, `client_secrets`, `token`, `credentials`, `api_key`, `secret`, `credential`. Only `*_file` keys are resolved — plain string keys are never touched.

```python
# ✅ Resolved — key ends with _file, value is relative
{ "token_file": "my_token.json" }  →  ".runtime/secrets/my_token.json"

# ✅ Not touched — key does not end with _file
{ "channel_name": "PlayOwnAi" }    →  unchanged
```

---

## Rule 38 · `read_meta()` Must Not Use Collision Slug for Existing Topics

`read_meta()` in `config.py` currently calls `_find_collision_free_slug()` before reading — this is **wrong for reads**. Collision-free slug generation is only for **workspace creation** (Rule 22). Reading meta must use the exact slug of the existing workspace.

```python
# ✅ Correct for reads
def read_meta(topic: str) -> dict:
    slug = slugify(topic)          # exact slug, no collision suffix
    f = RUNTIME_PATHS["output"] / slug / "meta.json"
    ...

# ❌ Wrong — appends __01 even when reading an existing workspace
def read_meta(topic: str) -> dict:
    slug = _find_collision_free_slug(slugify(topic))   # creates wrong path
    ...
```

This is an existing bug in `config.py` that must be fixed.

---

# 🚫 SECTION 12 — ANTI-PATTERNS (ENFORCE ZERO TOLERANCE)

## Rule 39 · These are banned. No exceptions.

| Anti-Pattern | Why Banned |
|---|---|
| Unit calling another unit | Breaks isolation |
| Unit reading another unit's config | Tight coupling |
| Direct LLM call outside factory | Bypasses config |
| Flow logic inside a unit | Violates Rule 2 |
| Returning data instead of saving files | Hidden state |
| Hardcoded model/path/voice in tool | Violates Rule 28 |
| Re-generating `.md` / `.csv` in consumer units | Violates Rule 8 |
| Running full crew blindly | Violates Rule 14 |
| `plot()` calling `plot()` (recursion) | Runtime crash |
| Multiple units in one `kickoff()` | Violates Rule 3 |
| Deleting keys from `data.json` | Violates Rule 29 |
| Writing output file without smart skip check | Violates Rule 32 |
| Adding logic to `config.py`  | Violates Rule 34 |
| `read_meta()` using collision-free slug | Violates Rule 38 |
| Diverging stop-word list between  & resolver | Violates Rule 36 |
| Constructing paths as string literals instead of `PATHS` | Violates Rule 19 |
| Hardcoded `.runtime/` or `output/` path string in any unit or tool | Violates Rule 39 |
| `OUTPUT_ROOT` still pointing to project-root `output/` (not migrated) | Violates Rule 39 |
| Placing secret files in `input/` instead of `.runtime/secrets/` | Violates Rule 39 |
| Referencing `.runtime/cache/` files in `meta.json` as outputs | Violates Rule 39 |

---

## Rule 40 · Final Mental Model

# 🧠 FINAL MENTAL MODEL

```
User Input
   ↓
main.py  (dumb router — 3 lines)
   ↓
flow_controller.py  (all logic — slug, skip, lock, meta)
   ↓
ONE unit runs
   ↓
Unit produces files  →  .runtime/output/{slug}/
   ↓
Next run reads those files
```

---

## 🎯 ONE-LINE SUMMARY

> **Flow controls execution — Units generate outputs — Files connect everything — LLM is centralized — Config defines identity.**
