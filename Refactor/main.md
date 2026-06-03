

> **Router Principle → “should be dumb and simple”**

STRICT VIOLATION LIST:
---

# 🚫 Router Principle — VIOLATION LIST
## ❌ 1. ANY BUSINESS LOGIC INSIDE ROUTER
**Violation:**

```python
if unit == "debate":
    if file_exists(...) and meta.status != "done":
        run_debate_with_retry_logic()
```

**Why bad:**
Router is thinking → ❌

**Rule:**

> Router ONLY calls → `flow_controller.run(unit)`

---

## ❌ 2. CONDITIONAL FLOW DECISIONS

**Violation:**

```python
if topic_type == "video":
    run_animation()
else:
    run_definition()
```

**Why bad:**
Routing logic = belongs to FlowController

**Rule:**

> Router does NOT decide flow paths

---

## ❌ 3. FILE / META / STATE ACCESS

**Violation:**

```python
load_meta()
check_output_folder()
read_csv()
```

**Why bad:**
State awareness = Flow layer responsibility

**Rule:**

> Router knows NOTHING about files, meta, outputs

---

## ❌ 4. MULTI-UNIT EXECUTION

**Violation:**

```python
run("Unit-Data")
run("Unit-Debate")
run("Unit-Publisher")
```

**Why bad:**
Breaks your core rule:

> “Only ONE unit runs at a time”

---

## ❌ 5. DIRECT AGENT / CREW CALLS

**Violation:**

```python
crew.kickoff()
agent.run_task()
```

**Why bad:**
Router bypasses architecture

**Rule:**

> Router NEVER touches CrewAI

---

## ❌ 6. ERROR HANDLING LOGIC

**Violation:**

```python
try:
    run()
except:
    retry()
    fallback()
```

**Why bad:**
Retry strategy = FlowController concern

---

## ❌ 7. PARAMETER TRANSFORMATION

**Violation:**

```python
unit = sys.argv[1].lower().replace("-", "_")
```

**Why bad:**
Router is mutating inputs

**Rule:**

> Pass raw input → FlowController handles parsing

---

## ❌ 8. LOGGING / DEBUG COMPLEXITY

**Violation:**

```python
print("Starting Unit-Data...")
log_step(...)
track_metrics(...)
```

**Why bad:**
Observability belongs to flow layer

---

## ❌ 9. DEFAULT FALLBACK BEHAVIOR

**Violation:**

```python
if not unit:
    run("Unit-Data")
```

**Why bad:**
Hidden logic = hidden bugs

---

## ❌ 10. RECURSION / INTERNAL CALLS

**Violation:**

```python
def kickoff():
    run()
    kickoff()  # ❌ madness
```

or your current bug:

```python
def plot():
    plot()   # ❌ infinite recursion
```

(Already visible in your code)

---

## ❌ 11. ENV / CONFIG LOADING

**Violation:**

```python
load_dotenv()
config = read_yaml()
```

**Why bad:**
Config belongs to FlowController

---

## ❌ 12. ANY IMPORT EXCEPT FLOW ENTRY

**Violation:**

```python
from crew import *
from tools import *
from utils import *
```

**Rule:**

```python
from cf2.flow_controller import run
```

ONLY.

---

# ✅ WHAT ROUTER SHOULD BE (FINAL FORM)

Your router should NEVER grow beyond this:

```python
from cf2.flow_controller import run

def kickoff():
    run()

if __name__ == "__main__":
    kickoff()
```

---

# 🧠 MENTAL MODEL

Router = **button**
FlowController = **brain**

---

# 🔥 GOLDEN TEST

Ask yourself:

> “If I delete router.py and replace it with 3 lines… does system still work?”

If **NO → You violated the principle**

---
```python
from cf2.flow_controller import run

def kickoff():
    run()

def plot():
    plot()

if __name__ == "__main__":
    kickoff()

```
