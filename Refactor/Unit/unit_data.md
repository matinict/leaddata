# 🔥 Unit-Data — Engineering Rules

> **Unit-Data is the raw material engine of CF2.**
> Every other unit is a consumer. Unit-Data is the only producer.
> A deadlock, re-run, or partial output here poisons the entire factory.

---

## IDENTITY RULES

### Rule D-1 · Unit-Data is a Provider, Never a Consumer
Unit-Data reads NOTHING from other units.
It reads only: `topic`, `inputs` (config), and `data.json`.
It writes only to `output/{slug}/` subfolders.

```
❌ unit_data.py reads any .md or .mp4 from workspace
✅ unit_data.py writes .md, .csv, .txt to workspace
```

### Rule D-2 · Unit-Data Never Calls Itself
No retry loop, no recursive fallback, no self-kickoff.
If it fails, it marks `failed` in meta.json and stops.
FlowController decides whether to re-run.

```
❌ unit_data calls run_unit("Unit-Data", ...)
✅ unit_data returns result or raises — nothing else
```

### Rule D-3 · Unit-Data is Never Called Directly
Only two callers are legal:
1. `FlowController` (full pipeline or `--unit Unit-Data`)
2. `dependency_resolver` (when a consumer's input files are missing)

```
❌ unit_debate.py imports and calls unit_data.run()
✅ dependency_resolver.resolve_deps() triggers it
```

---

## TASK SELECTION RULES

### Rule D-4 · Task Selection is Controlled by Unit Switches Only
Unit-Data reads `inputs["Unit-Debate"]`, `inputs["Unit-Definition"]` etc.
It NEVER reads nested config keys like `definition_enabled` or `debate_video_enabled`
to decide which tasks to run.

```python
# ✅ Correct
debate_on = inputs.get("Unit-Debate", False)

# ❌ Wrong — config sub-key, not unit switch
debate_on = inputs.get("debate_enabled", False)
```

### Rule D-5 · Core Tasks Always Run
`data_research` and `data_generate_csv` run on every execution.
They are the foundation. No unit switch can disable them.

```python
# Always — no guard
agents += [factory.data_researcher()]
tasks  += [factory.data_research()]
agents += [factory.data_csv_generator()]
tasks  += [factory.data_generate_csv()]
```

### Rule D-6 · Consumer-Specific Tasks Only Run for Enabled Units

| Task group            | Guard                          |
|-----------------------|--------------------------------|
| Definition text       | `Unit-Definition == true`      |
| Debate scripts        | `Unit-Debate == true`          |
| Debate short scripts  | `Unit-Debate == true` AND `debate_short == true` |
| Comparison data       | `Unit-Comparison == true`      |

If a unit is disabled, its data is never generated.
This prevents wasted LLM calls and partial file states.

---

## OUTPUT RULES

### Rule D-7 · Output Files are the Contract
Unit-Data is only "done" when its required output files physically exist.
`meta.json` status alone is not sufficient.

Current verification (in `meta.py::verify_unit_done`):
```
debate/propose.md   ← required if Unit-Debate enabled
debate/oppose.md    ← required if Unit-Debate enabled
debate/decide.md    ← required if Unit-Debate enabled
definition/def_En.txt ← required if Unit-Definition enabled
animation/data.csv  ← required if Unit-Animation enabled
```

### Rule D-8 · Output is Written Once — Never Overwritten
If a file already exists, Unit-Data does not regenerate it.
Smart skip in tools handles this at file level (Rule 24 of CF2).
If `--force` is passed, FlowController resets meta to `pending` first.

```
IF output file exists → tool skips silently
IF meta says done AND files exist → Unit-Data skips entirely
IF meta says done BUT file missing → meta resets to pending → re-run
```

### Rule D-9 · Output Directory Structure is Fixed
Unit-Data creates these dirs on every run (idempotent):
```
output/{slug}/
  debate/
  definition/
  animation/
  comparison/
```
No unit may create these dirs. Only Unit-Data owns this.

---

## DEADLOCK PREVENTION RULES

### Rule D-10 · Dependency Resolver Uses force=False
When dep resolver auto-triggers Unit-Data, it passes `force=False`.
This means smart-skip applies — if Unit-Data already ran and files exist,
it will NOT re-run, even when called as a dependency.

```python
# ✅ Correct — smart skip protects against re-run
run_unit_internal(dep_unit, topic, workspace, inputs, force=False)

# ❌ Wrong — bypasses smart skip, causes re-run every time
run_unit_internal(dep_unit, topic, workspace, inputs, force=True)
```

### Rule D-11 · Unit-Data Cannot Be Triggered by Its Own Consumers
Unit-Animation, Unit-Debate etc. do NOT call Unit-Data.
They read files. If files are missing, they exit with a clear error.
The dep resolver — not the consumer — is responsible for auto-running Unit-Data.

```python
# ✅ Consumer — just checks file and exits if missing
if not propose_md.exists():
    print(f"❌ Missing: {propose_md}"); sys.exit(1)

# ❌ Consumer calling producer — illegal cross-unit call
from cf2.units.unit_data import run as run_data
run_data(topic, inputs)
```

### Rule D-12 · Lock Protects Against Parallel Runs
Unit-Data acquires a `.lock_unit_data` file before execution.
If a lock exists and is fresh (< 1 hour old), second invocation exits.
This prevents two dep resolvers from triggering Unit-Data simultaneously.

---

## VERIFICATION RULES

### Rule D-13 · verify_unit_done Checks Per-Unit Files
`meta.py::verify_unit_done("Unit-Data")` must verify only the files
that were expected to be generated for the enabled units.

Current: checks debate files always.
**TODO:** make it check only files relevant to enabled units.

```python
# Future improvement
if inputs.get("Unit-Debate"):
    check("debate/propose.md", "debate/oppose.md", "debate/decide.md")
if inputs.get("Unit-Definition"):
    check("definition/def_En.txt")
if inputs.get("Unit-Animation"):
    check("animation/data.csv")
```

---

## SUMMARY — UNIT-DATA CONTRACT

```
INPUTS  : topic string + flat inputs dict (from data.json + _workspace)
PROCESS : research → csv → [definition] → [debate] → [comparison]
          (each block gated by its Unit-* switch)
OUTPUTS : files in output/{slug}/ subfolders
STATUS  : done only when output files physically confirmed
CALLERS : FlowController | dependency_resolver only
NEVER   : calls other units | reads other units' output | runs twice
```
