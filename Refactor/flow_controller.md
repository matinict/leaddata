



- flow_controller.py is doing TOO MUCH.
- 500+ lines = already a **God Object smell** 🚨
- already did great separation with `meta.py`,


Need **2nd-level splitting**.

---

# 🔥 ROOT PROBLEM

 current file is mixing **5 responsibilities**:

From  code

* CLI parsing
* Config loading
* Topic resolution
* Dependency system
* Unit execution engine
* Flow (CrewAI wrapper)
* Progress tracking

👉 This violates  own principle:

> **“FlowController owns decisions” — but NOT everything**

---

# ✅ WHAT TO SPLIT (CLEAN ARCHITECTURE)

Here’s the **correct decomposition** 👇

---

## 🧩 1. `meta.py` ✅ (already done)

✔ state
✔ lock
✔ skip

👉 KEEP

---

## 🧩 2. `config_loader.py` (NEW)

Move:

```python
load_config()
_deep_merge()
```

👉 Why:

* Pure config concern
* reusable across tools later

---

## 🧩 3. `topic_resolver.py` (NEW)

Move:

```python
resolve_topic()
generate_slug()
resolve_workspace()
```

👉 Why:

* Completely separate domain
* will grow (queue, trending, AI selection)

---

## 🧩 4. `unit_registry.py` (CRITICAL SPLIT)

Move:

```python
_get_runner()
VALID_UNITS (maybe)
```

👉 Replace with:

```python
UNIT_REGISTRY = {
    "Unit-Data": "cf2.units.unit_data:run",
}
```

👉 Then dynamic import

🔥 WHY IMPORTANT:

* removes HUGE import block
* avoids circular dependency hell later

---

## 🧩 5. `dependency_resolver.py` (NEW)

Move:

```python
UNIT_DEPS
UNIT_SWITCH
_resolve_deps()
```

👉 Why:

* This logic will explode in complexity later
* keep it isolated

---

## 🧩 6. `unit_executor.py` (VERY IMPORTANT)

Move:

```python
execute_unit()
_execute_unit_internal()
```

👉 This becomes:

> **Execution Engine**

Responsibilities:

* skip check
* lock
* run unit
* mark status

👉 FlowController should NOT know HOW unit runs

---

## 🧩 7. `progress_tracker.py` (OPTIONAL SPLIT)

Move:

```python
_make_tracker()
```

👉 Why:

* Very noisy
* not core logic

---

## 🧩 8. `cli.py` (CLEANEST MOVE)

Move:

```python
_parse_args()
_install_sigint_handler()
```

👉 Then `run()` becomes cleaner

---

# 🧠 FINAL TARGET STRUCTURE

```text
cf2/

  flow_controller.py     ← orchestration ONLY (100–150 lines)

  core/
    config_loader.py
    topic_resolver.py
    dependency_resolver.py
    unit_executor.py
    unit_registry.py
    progress_tracker.py

  infra/
    meta.py

  cli/
    cli.py
```

---

# 🎯 WHAT flow_controller SHOULD LOOK LIKE

After split →  controller becomes **VERY SMALL**

```python
def run():
    args = parse_args()

    inputs = load_config(args.profile)
    inputs = apply_cli_overrides(inputs, args)

    topic = resolve_topic(inputs)
    slug = generate_slug(topic)
    workspace = resolve_workspace(topic, slug)

    init_meta(workspace, topic, slug)

    if args.status:
        show_status(workspace)
        return

    flow = VideoFactoryFlow()
    flow.state["inputs"] = build_flow_inputs(...)

    flow.kickoff()
```

👉 That’s it.

---

# 🚨 BIGGEST SMELL IN  CURRENT FILE

### ❌ This block is too heavy:

```python
def _execute_unit_internal(...)
```

Why dangerous:

* knows meta
* knows tracker
* knows runner
* knows error handling
* knows verification

👉 This is **mini-framework inside controller**

---

# 🔥 GOLDEN RULE (NEXT LEVEL)

> **FlowController = Orchestrator ONLY**
>
> ❌ No execution logic
> ❌ No dependency logic
> ❌ No state logic

---

# ⚡ PRIORITY SPLIT ORDER (DO THIS FIRST)

1. ✅ `unit_executor.py` ← MOST IMPORTANT
2. ✅ `dependency_resolver.py`
3. ✅ `topic_resolver.py`
4. ✅ `config_loader.py`
5. ⏳ rest later

---

# 💣 HARD TRUTH

Right now:

> You fixed Router problem
> BUT created **FlowController Monolith**

---

# 🚀 RESULT AFTER SPLIT

* flow_controller: ~120 lines ✅
* each module: 50–150 lines ✅
* scalable to 50+ units 🚀
* no mental overload 🧠

 
