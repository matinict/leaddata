# 🎬 CF2(CrewAiFactoryFlow) Project — Engineering Rules & Principles (Final)
# 🧠 CORE PROBLEM (WHY WE ARE REBUILDING)

Old CrewAI system:
 ❌ Too many agents + tasks in one place
 ❌ Manual chaining → hard to control
 ❌ Repeated execution (waste of time & cost)
 ❌ 1000+ line files → unmaintainable
 ❌ Tight coupling (everything depends on everything)
# 🎯 CORE GOAL
Build a Flow-based Modular Pipeline that is simple, modular, skippable, debuggable, scalable, and multi-channel.

🔥 Golden Principle: Flow controls logic — Units do work — Files store truth — Config defines identity

> Build a Flow-based Modular System that is:
 ✅ Simple to run (one command)
 ✅ Modular (Unit-based)
 ✅ Skippable (no repeat work)
 ✅ Debuggable (file-based)
 ✅ Scalable (add/remove units easily)
# 🔥 GOLDEN PRINCIPLE

> Flow controls logic — Units do work — Files store truth
# 🧱 RULES (STRICT ENGINEERING GUIDELINES)
# 1. main.py → Router Principle

> 🔑 Must be dumb and simple

## Responsibilities:
 Parse CLI arguments
 Pass control to FlowController
 NOTHING else
## ❌ NOT ALLOWED:
 Business logic
 File handling
 Crew execution
## ✅ Example Responsibility:text: run --unit Unit-Debate --topic "AI vs Humans"

# 2. flow_controller.py → Brain of System

> 🧠 ALL logic lives here
## Responsibilities:
 Load input
 Resolve topic (manual / auto)
 Generate slug
 Create workspace
 Load/update meta.json
 Decide RUN / SKIP
 Call correct Unit
 Handle errors + retry
## ❌ NOT ALLOWED:
 Actual task execution
 Video generation
 LLM prompts
## 🔥 Rule:
> FlowController = Decision Engine
# 3. Unit- → Execution Blocks

> 🔧 Each Unit = ONE responsibility
## Examples:text: Unit-Data
Unit-Debate
Unit-Animation
Unit-Publisher
Unit-Advertise

## Responsibilities:
 Read input files
 Call Crew (agents + tasks)
 Save outputs
 Return status
## ❌ NOT ALLOWED:
 Cross-unit logic
 Topic resolution
 Folder creation logic
## 🔥 Rule:
> Unit does work — Flow decides when
# 4. subUnit- → Micro Tasks

> 🧩 Small reusable blocks
## Examples:text: subUnitYtMetadata
subUnitYtUpload
subUnitFbUpload
subUnitShorts
subUnitTvc

## Responsibilities:
 Perform ONE specific job
 Reusable across units
## 🔥 Rule:
> One function = one responsibility
# 5. Unit-Data → ONLY Generator

> 🔥 MOST IMPORTANT RULE
## Responsibilities:
 Generate ALL base data:
   .md
   .csv
 NEVER generate video
 NEVER depend on other units
## Output:text: output/{topic}/
  debate/debate.md
  definition/def_.md
  animation/data.csv

## ❌ NOT ALLOWED:
 Video generation
 Upload
 Ads
## 🔥 Rule:
> Generate once → used everywhere
# 6. Consumer Units → NO DATA CREATION
## Units:text: Unit-Debate
Unit-Definition
Unit-Animation
Unit-Comparison

## Responsibilities:
 Read .md / .csv
 Generate video
## ❌ NOT ALLOWED:
 Calling LLM for content again
 Re-generating data
## 🔥 Rule:
> Consume only — never regenerate
# 7. Unit-Publisher → Distribution Layer
## Responsibilities:
 Generate metadata
 Upload videos (YT / FB)
 Track upload status
## SubUnits:text: subUnitYtMetadata
subUnitYtUpload
subUnitFbUpload
subUnitSocialShare

## 🔥 Rule:
> Publishing depends on finished content only
# 8. Unit-Advertise → Promotion Layer
## Responsibilities:
 Create promotional assets
 Shorts / reels / TVC
## SubUnits:text: subUnitShorts
subUnitSocial
subUnitTvc

## 🔥 Rule:
> Reuse existing videos — never regenerate core content
# 9. File System → Source of Truth
## Rule:
> Files = truth, NOT memory
## Examples:text: debate.md → source of script
data.csv → source of animation
video.mp4 → final output

## ❌ NOT ALLOWED:
 Hidden state in memory
 Recomputing instead of reading
# 10. Folder Structure → Topic-Based
## Rule:text: output/{TopicSlug}/Unit-

## Example:text: output/EvaFrameworkNew/

  Unit-Debate/
  Unit-Animation/
  Unit-Publisher/

## 🔥 Rule:
> One Topic = One Workspace
# 11. Slug Rule → Predictable Naming
## Rule:
 First 3 meaningful words
 Skip stop words
 PascalCase
## Example:text: "EVA Framework for New Evaluating Voice Agents"
→ EvaFrameworkNew

# 12. Collision Rule → __01 System
## Rule:text: EvaFrameworkNew/
EvaFrameworkNew__01/
EvaFrameworkNew__02/

## 🔥 Rule:
> Never overwrite existing topic
# 13. meta.json → System Brain
## Responsibilities:
 Track unit status
 Track uploads
 Store topic info
## Status:text: pending
running
done
failed

## 🔥 Rule:
> Always trust meta before running anything
# 14. Smart Skip → Time Saver
## Rule:text: IF meta == done → SKIP
IF file exists → SKIP
ELSE → RUN

## 🔥 Rule:
> Never repeat heavy tasks
# 15. Lock System → Safety
## Rule:text: .lock file during execution

## Purpose:
 Prevent duplicate runs
 Detect crashes
# 16. Crew Usage → Execution Only
## Rule:
> Crew = tool executor only
## ❌ NOT ALLOWED:
 Running full crew blindly
 Mixing multiple tasks in one run
## ✅ Allowed:text: Flow → select agent → run task

# 17. Function Design Rule
## Rule:
 Max ~50–80 lines
 Single responsibility
 No nested chaos
## ❌ NOT ALLOWED:
 1000-line functions
 mixed logic
# 18. Unit Independence Rule
## Rule:
 Units must NOT depend on each other
 Only depend on files
## 🔥 Example:text: Unit-Animation does NOT call Unit-Debate

# 19. Execution Rule
## Rule:
> Run ONE unit at a time
## Example:
bash
run --unit Unit-Debate
run --unit Unit-Publisher

# 20. System Philosophy (FINAL)
> ❌ Old Way:
 One giant crew
 manual control
 repeated work
> ✅ New Way:
 Flow-controlled system
 Modular units
 File-based pipeline
 Zero waste execution
## Others Files base Rules

1. main.py → Router Principle — Dumb and simple. Only parses CLI profile, loads config lazily, hands off to flow_controller. Nothing else.

2. flow_controller.py → Brain — ALL logic lives here. Loads config, resolves topic, generates slug, creates workspace, loads meta.json, decides run/skip, dispatches units, handles errors.

3. Unit- → Execution Blocks — Each unit has ONE responsibility. Reads input files, calls Crew, saves output, returns status. Nothing more.

4. subUnit- → Micro Tasks — Small reusable blocks. One function = one responsibility. Reusable across units.

5. Unit-Data → Generator Only — Generates ALL base data (.md, .csv). Never generates video. Never depends on other units. Most critical rule.

6. Consumer Units → No Data Creation — Unit-Debate, Unit-Animation, Unit-Definition only read files. Never call LLM to regenerate content.

7. Unit-Publisher → Distribution Only — Handles metadata, YT/FB upload, social share. Depends on finished content files only.

8. Unit-Advertise → Promotion Only — Creates Shorts, TVC, social assets. Reuses existing videos — never regenerates core content.

9. File System → Source of Truth — Files = truth, not memory. Never recompute what a file already holds.

10. Folder Structure → Topic-Based — output/{TopicSlug}/Unit-/. One topic = one workspace. Never mix outputs across topics.

11. Slug Rule → Predictable Naming — First 3 meaningful words, skip stop words, PascalCase. e.g. "EVA Framework for New Agents" → EvaFrameworkNew.

12. Collision Rule → __01 System — EvaFrameworkNew/ → EvaFrameworkNew__01/ → EvaFrameworkNew__02/. Never overwrite an existing topic folder.

13. meta.json → Unit State Brain — Tracks every unit status (pending / running / done / failed) and upload history. Always check meta before running anything.

14. Smart Skip → Zero Waste — meta[unit] == done or output file exists → SKIP. Never repeat heavy tasks. Crash recovery is automatic.

15. Lock System → Safety — .lock file created at run start, deleted on clean exit. Prevents duplicate parallel runs. Detects crashes.

16. Crew → Execution Only — Flow selects agent → runs single task. Never run full crew blindly. Never mix unrelated tasks in one run.

17. Function Design → 50–80 Lines Max — Single responsibility per function. No nested chaos. No 1000-line functions.

18. Unit Independence → Files Only Interface — Units never call each other directly. Only dependency allowed is reading files from output/{slug}/.

19. Config Profile → One File Per Channel — data.json = default, data3d.json = 3D channel, datasports.json = sports channel. Only differing keys needed — base data.json is always the foundation.

20. Execution → One Unit at a Time — Flow runs units sequentially and explicitly. Never blindly chain everything.# 🚀 FINAL STATEMENT

> You are not building a script — you are building a production pipeline
