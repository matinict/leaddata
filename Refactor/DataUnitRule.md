


Data Unit Rule::
-save MASSIVE tokens stop unanted call

> If base `.md` exists → skip generating `-m.md` → move to next stage (video)

---

# ❗ CURRENT PROBLEM

Right now 360debater system:

* treats `propose.md` and `propose-m.md` as separate tasks
* BUT `-m.md` is **derived from `.md`**
* so 360debate are **wasting tokens regenerating same logic**

---

# ✅ CORRECT MODEL (DEPENDENCY GRAPH)

Instead of:

```txt
propose.md
propose-m.md   ❌ treated as independent
```

You define:

```txt
propose.md  → source
   ↓
propose-m.md → derived
```

---

# 🧠 SMART SKIP RULE (WHAT YOU WANT)

## 🔥 Rule:

```txt
IF base file exists:
    skip ALL derived generation
```

---

## ✅ APPLY TO YOUR CASE

You already have:

```txt
propose.md
oppose.md
decide.md
```

👉 So:

```txt
SKIP:
- propose-m.md
- oppose-m.md
- decide-m.md
```

👉 Go directly to:

```txt
video generation
```

---

# ⚙️ IMPLEMENTATION LOGIC (NO CODE, CLEAR FLOW)

## 🧠 Step 1 — Define “Source Files”

```txt
BASE FILES:
- propose.md
- oppose.md
- decide.md
```

---

## 🧠 Step 2 — Define “Derived Files”

```txt
DERIVED FILES:
- propose-m.md
- oppose-m.md
- decide-m.md
```

---

## 🧠 Step 3 — Pre-check before running `-m` tasks

```txt
IF ALL base files exist:
    mark mini tasks as SKIPPED
    DO NOT CALL LLM
```

---

## 🧠 Step 4 — Fallback (important)

```txt
IF base missing BUT mini exists:
    use mini (rare case)

IF both missing:
    generate normally
```

---

# ⚡ SMART FLOW FOR YOUR PIPELINE

```txt
Unit-Data finished
   ↓
Check debate inputs:

IF propose.md + oppose.md + decide.md exist:
    skip mini generation
    skip debate LLM completely
    → go to video

ELSE:
    run debate LLM
```

---

# 🔥 EVEN BETTER (TOKEN SAVER MODE)

Since 360debater video uses:

```txt
debate_video3d
```

👉 It can directly consume:

```txt
propose.md
oppose.md
decide.md
```

💥 So 360debate can COMPLETELY REMOVE:

```txt
-m.md generation in debug mode
```

---

# 🧠 FINAL OPTIMIZED RULESET

## ✅ Rule 1 — Base priority

```txt
.md > -m.md
```

---

## ✅ Rule 2 — Skip derived

```txt
IF .md exists → skip -m.md
```

---

## ✅ Rule 3 — Skip LLM fully

```txt
IF all 3 base files exist:
    skip debate generation entirely
```

---

## ✅ Rule 4 — Video trigger

```txt
IF base files exist:
    allow video generation
```

---

# 🚀 RESULT

With 360debater current folder:

```txt
propose.md ✅
oppose.md ✅
decide.md ✅
```

👉 System should:

```txt
❌ NOT run debate agents again
❌ NOT create -m.md
✅ GO DIRECTLY → video rendering
```

---

# 💡 PRO TIP (VERY IMPORTANT)

Add this mindset:

> **“Files are truth, not tasks.”**

---

# 🔥 BONUS (SUPER CLEAN DESIGN)

Instead of tracking:

```json
"propose-m": "pending"
```

👉 Just infer:

```txt
IF propose.md exists → everything derived is implicitly done
```

---

# 🎯 FINAL ANSWER

✔ `.md` should block `-m.md`
✔ System should jump directly to video
✔ This will save MASSIVE tokens

---
