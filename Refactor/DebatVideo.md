


# 🔥 Core Rule (Non-Negotiable)

> **Verdict ≠ summary**
> It is the **anchor of meaning**. Never compress it like others.

---

# ✅ What “Preserve Verdict Clarity” Actually Means

From your `decide.md`:

* Winner → **PROPOSITION WINS**
* Why → **applications → deportation vector**
* Evidence → **73% ICE orders from USCIS data**

👉 These 3 must ALWAYS survive.

Everything else is optional.

---

# 🚀 Upgrade Strategy

## 1. Extract Verdict Structure (NOT sentences)

Instead of:

```python
decision_sents = _sentences(parts["reason"])
```

👉 Do:

```python
def _extract_verdict_core(text: str):
    import re

    winner = re.search(r'(PROPOSITION|OPPOSITION)\s+WINS', text, re.I)
    winner = winner.group(0).upper() if winner else ""

    # Key causal claim (shortened)
    cause = ""
    if "principal vector" in text or "enables removal" in text:
        cause = "applications now trigger deportation risk"

    # Key stat
    stat = ""
    m = re.search(r'(\d+%)[^\.]*ICE[^\.]*', text, re.I)
    if m:
        stat = m.group(0)

    return winner, cause, stat
```

---

## 2. Rebuild Verdict (Compressed but Strong)

```python
def _build_verdict(winner, cause, stat):
    parts = [winner]

    if cause:
        parts.append(cause)

    if stat:
        parts.append(stat)

    return ". ".join(parts) + "."
```

---

## 3. Hard-Protect Verdict Budget

Instead of:

```python
reason = _weight_and_select(decision_sents, 120)
```

👉 Replace with:

```python
winner, cause, stat = _extract_verdict_core(parts["reason"])
reason = _build_verdict(winner, cause, stat)
```

---

## 4. Reserve Space FIRST (CRITICAL)

Before assembling body:

```python
verdict_len = len(reason)

remaining_budget = max_chars - verdict_len
```

Then distribute:

```python
budgets = {
    "pro": int(remaining_budget * 0.2),
    "con": int(remaining_budget * 0.2),
    "analysis": int(remaining_budget * 0.6),
}
```

👉 This guarantees:

* Verdict NEVER gets cut
* Everything else adapts

---

## 5. Final Guard (Never Cut Verdict)

Replace your cut logic:

```python
if len(body) > max_chars:
```

👉 with:

```python
if len(body) > max_chars:
    # split BEFORE verdict
    main, verdict = body.rsplit(reason, 1)

    safe_main = main[:max_chars - len(reason)].rsplit(' ', 1)[0]

    body = safe_main.strip() + "\n\n" + reason
```

---

# 📊 Before vs After

### ❌ Current Output (risk)

* Verdict gets truncated
* Logic becomes unclear
* TTS sounds weak

---

### ✅ New Output (guaranteed)

```text
PROPOSITION WINS. Applications now trigger deportation risk. 73% of ICE orders rely on USCIS data.
```

✔ Short
✔ Clear
✔ Evidence-backed
✔ TTS powerful

---

# 🔥 Extra Boost (Optional but High Impact)

## Add “contrast punchline”

```python
if "not administrative strain" in text:
    parts.append("not delay, but structural risk")
```

👉 Result:

```text
PROPOSITION WINS. Applications now trigger deportation risk. 73% of ICE orders rely on USCIS data. Not delay, but structural risk.
```

---

# 🎯 Final Insight

> You don’t compress the verdict.
> You **reconstruct it into a high-density signal**.

---

If you want next level:

I can align this with your:

* `debate_secs_per_line`
* TTS pacing
* Shorts retention hook

👉 say: **“verdict + TTS optimization”**







HD version
You should now see individual block clips being generated:
_blk_p0 (PROPOSITION & OPENING STATEMENT) → Guy voice
_blk_c0 (OPPOSITION OPENING STATEMENT ) → Aria voice  
_blk_p1 (Argument 1)       → Guy voice
_blk_c1 (Counter-Argument 1)   → Aria voice
_blk_p2 (Argument 2)       → Guy voice
_blk_c2 (Counter-Argument 2)   → Aria voice
_blk_p3 (Argument 3)       → Guy voice
_blk_c3 (Counter-Argument 3)   → Aria voice
mod                    → Ryan voice


Short/Mini version
You should now see individual block clips being generated:
_blk_p0 (PRO opening) → Guy voice
_blk_c0 (CON opening) → Aria voice  
_blk_p1 (Arg 1)       → Guy voice
_blk_c1 (C Arg 1)   → Aria voice
_blk_p2 (Arg 2)       → Guy voice
_blk_c2 (C Arg 2)   → Aria voice
_blk_p3 (Arg 3)       → Guy voice
_blk_c3 (C Arg 3)   → Aria voice
mod                    → Ryan voice
