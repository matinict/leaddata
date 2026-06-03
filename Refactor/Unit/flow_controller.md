# 🔥 Rule Violation Analysis & Config-Driven Fix

I've analyzed your `flow_controller.py` against your engineering rules. Here's the critical breakdown:

---

## 🚨 VIOLATIONS DETECTED

### **Rule 28 Violation** — No Hardcoded Values in Tools
**Location:** `flow_controller.py:_flatten_inputs()` Lines 149–240

```python
# ❌ VIOLATION — 91 hardcoded defaults inside code
D = {
    "debate_definition_enabled": False,
    "debate_max_chars": 3000,
    "debate_secs_per_line": 3.5,
    "video_fps": 30,
    "audio_speed": 1.1,
    "prodcast_voice_host": "en-US-RogerNeural",
    # ... 85+ more defaults
}
```

**Why this breaks production:**
- Changes to `data.json` get **silently overridden** by code defaults
- Different units may use conflicting values (config says 60fps, code forces 30fps)
- Debugging becomes impossible — "Why is my TTS voice wrong?" → hidden in code
- Multi-channel configs break (Bengali voice gets overridden by hardcoded English)

---

### **Rule 30 Violation** — Config = Control, Not Logic
**Location:** Same block — mixing execution control with data

```python
# ❌ VIOLATION — Logic hidden inside "defaults"
"debate_definition_enabled": False,  # ← This controls EXECUTION
"debate_max_chars": 3000,           # ← This is DATA
```

**The problem:** Rule 30 says config should **only contain values**, not decide what runs. But your code mixes both:
- `debate_definition_enabled` is a **Unit switch** (belongs in top-level config)
- `debate_max_chars` is a **parameter** (belongs in `debate_config` block)

---

### **Rule 23 Violation** — All Values Must Come from Config
**Location:** Every `inputs.setdefault(k, v)` call

```python
# ❌ VIOLATION — Code decides defaults instead of config
for k, v in D.items():
    inputs.setdefault(k, v)  # ← Silent injection
```

**The pattern you're violating:**
```
✅ CORRECT:  data.json → schema → FlowController → Units
❌ YOUR CODE: data.json + hidden_defaults_in_code → Units
```

---

## 🛠️ HOW TO FIX — 3-Phase Migration (Production-Safe)

### **Phase 1: Add Validation (Don't Break Anything Yet)**

```python
# ADD THIS at the start of _flatten_inputs()
REQUIRED_KEYS = {
    "video_fps",
    "audio_speed",
    "tts_engine",
    "debate_config",
    "animation_config",
    "prodcast_config",
    "classroom_config",
}

missing = [k for k in REQUIRED_KEYS if k not in inputs]
if missing:
    raise ValueError(
        f"❌ Config missing required keys: {missing}\n"
        f"Add them to input/data.json"
    )
```

**Run this first.** It will crash and show you which keys are actually missing from `data.json`.

---

### **Phase 2: Move Defaults to `data.schema.json`**

Your `data.schema.json` already defines the structure. Add `default` values there:

```json
{
  "video_fps": {
    "type": "integer",
    "default": 30,  // ← Schema-defined default
    "enum": [24, 30, 60]
  },
  "debate_config": {
    "type": "object",
    "properties": {
      "debate_secs_per_line": {
        "type": "number",
        "default": 3.5,  // ← Move here from code
        "minimum": 0.5,
        "maximum": 10.0
      }
    }
  }
}
```

Then load defaults **from schema** in `load_profile()`:

```python
# in config_loader.py or wherever load_profile lives
def load_profile(profile_name: str) -> dict:
    schema = json.load(open("input/data.schema.json"))
    config = json.load(open(f"input/{profile_name}"))

    # Apply schema defaults BEFORE merge
    config = _apply_schema_defaults(config, schema)
    return config

def _apply_schema_defaults(config: dict, schema: dict) -> dict:
    """Recursively apply defaults from schema"""
    for key, spec in schema.get("properties", {}).items():
        if "default" in spec and key not in config:
            config[key] = spec["default"]
        elif spec.get("type") == "object" and key in config:
            config[key] = _apply_schema_defaults(
                config[key],
                spec
            )
    return config
```

---

### **Phase 3: Delete the `D = {}` Block**

Once Phase 1 validation passes and Phase 2 is in place:

```python
# ✅ DELETE THIS ENTIRE BLOCK (Lines 149–240)
# D = {
#     "debate_definition_enabled": False,
#     ...
# }
#
# for k, v in D.items():
#     inputs.setdefault(k, v)

# ✅ REPLACE WITH: (nothing — config is now complete)
```

---

## 🎯 THE CORRECT PATTERN

### **Before (Your Current System):**
```
data.json (incomplete)
    ↓
FlowController adds 91 hidden defaults ❌
    ↓
Units get unpredictable values
```

### **After (Rule-Compliant):**
```
data.schema.json (defines defaults)
    ↓
data.json (overrides what's needed)
    ↓
load_profile() applies schema defaults
    ↓
FlowController validates & passes through
    ↓
Units receive complete, validated config
```

---

## 🔒 ENFORCEMENT RULES (Add to Your Docs)

### **Rule 28.1** — Fail Fast on Missing Config
```python
# ✅ CORRECT — crash early if config wrong
fps = inputs["video_fps"]

# ❌ FORBIDDEN — silent fallback hides bugs
fps = inputs.get("video_fps", 30)
```

### **Rule 28.2** — Schema is Source of Truth
- Every default value lives in `data.schema.json`
- Code **never** contains literal defaults
- `load_profile()` applies schema defaults before merge

### **Rule 28.3** — Config Validation is Mandatory
```python
# Required before pipeline runs
validate_config(inputs, schema="input/data.schema.json")
```

---

## 🚀 IMMEDIATE ACTION ITEMS

1. **Run Phase 1 validation** — it will crash and show missing keys
2. **Add those keys to `data.json`** with proper values
3. **Move defaults to `data.schema.json`** one config block at a time
4. **Test each unit** after migration to catch mismatches
5. **Delete `D = {}` block** once validation passes

---

## 🔥 CRITICAL INSIGHT

Your biggest problem isn't the units — it's **invisible config** buried in code.

**Example of the damage:**
```python
# data3d.json says:
{ "video_fps": 60 }

# But flow_controller.py forces:
inputs.setdefault("video_fps", 30)

# Result: 3D debate renders at 30fps despite config saying 60fps
# A/V sync breaks, operator has no idea why
```

**The fix:** Config must be **the single source of truth**. Code is just an executor.

---

Would you like me to:
1. **Generate the validation function** for Phase 1?
2. **Audit `data.json` vs schema** to find missing defaults?
3. **Create a migration script** to automate Phase 2?
