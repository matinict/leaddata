# Scoreboard Teaser - Show All Arguments (No Limiting)

## Current Implementation Issue

### Line 184 - Score Extraction (Main Scoreboard)
```python
data = extract_scores(
    debate_dir, md_suffix, 
    {"debate_scoreboard_max_args": sb_cfg.get("max_args", 3)}  # ← Limits to 3 args
)
```

**Problem:** The `max_args: 3` limit is applied **once** during extraction for BOTH:
- Full scoreboard (line 197)
- Teaser (line 204)

Both use the **same `data` object** with scores already limited to 3 arguments.

### Line 197 vs 204 - Rendering
```python
# Full Scoreboard
score_renderer.render(data, score_path, fps, dur, topic, sub, 1.0, logger)
                                                                 ↑
                                                          Scale: 100%

# Teaser
score_renderer.render(data, teaser_path, fps, dur*0.5, topic, sub, 0.75, logger)
                                                                           ↑
                                                              Scale: 75% (KEEP THIS!)
```

## What You Want

**Teaser should show ALL arguments** (no 3-limit), while keeping the **0.75 scale factor**.

So if there are 5 judges giving scores, the teaser should display all 5 scores, not just 3.

## Solutions

### Solution 1: Extract Scores Twice (Recommended)
Extract scores with different limits for each use case:

**Implementation:**
```python
def _resolve_scoreboard(debate_dir, md_suffix, fmt, fps, topic, sb_cfg, enabled, logger):
    if not enabled:
        return None

    # Extract full data with configured limit (for main scoreboard)
    data_limited = extract_scores(
        debate_dir, md_suffix, 
        {"debate_scoreboard_max_args": sb_cfg.get("max_args", 3)}
    )
    if not data_limited:
        logger(f"⚠️ Scoreboard data unavailable for {fmt}.")
        return None

    # Extract full data WITHOUT limit (for teaser to show all)
    data_full = extract_scores(
        debate_dir, md_suffix, 
        {"debate_scoreboard_max_args": 999}  # Show ALL arguments
    )

    dur = float(sb_cfg.get("duration", 8.0))
    sub = sb_cfg.get("subtitle", "Dynamic Intelligent")

    # Full scoreboard with limited args (3)
    score_path = debate_dir / f"scoreboard_{fmt}.mp4"
    if not score_path.exists():
        logger(f"🏁 Rendering scoreboard → {score_path.name}")
        if not score_renderer.render(data_limited, score_path, fps, dur, topic, sub, 1.0, logger):
            return None
    else:
        logger(f"⏭️ Scoreboard exists: {score_path.name}")

    # Teaser with ALL args (no limit) but keep 0.75 scale
    teaser_path = debate_dir / f"scoreboard_teaser_{fmt}.mp4"
    if not teaser_path.exists():
        logger(f"🎬 Rendering teaser → {teaser_path.name}")
        score_renderer.render(data_full, teaser_path, fps, dur*0.5, topic, sub, 0.75, logger)
    
    return score_path
```

### Solution 2: Pass max_args Parameter to Renderer
If `score_renderer.render()` supports a `max_args` parameter, pass it explicitly:

```python
# Full scoreboard - limit to 3 args
score_renderer.render(data, score_path, fps, dur, topic, sub, 1.0, logger, max_args=3)

# Teaser - show ALL args, but keep 0.75 scale
score_renderer.render(data, teaser_path, fps, dur*0.5, topic, sub, 0.75, logger, max_args=None)
```

### Solution 3: Extract with Different Config for Teaser
Store both datasets during extraction:

```python
def _resolve_scoreboard(debate_dir, md_suffix, fmt, fps, topic, sb_cfg, enabled, logger):
    if not enabled:
        return None

    # Extract with limit for display choice
    data = extract_scores(
        debate_dir, md_suffix, 
        {
            "debate_scoreboard_max_args": sb_cfg.get("max_args", 3),
            "teaser_max_args": 999  # Store full version for teaser
        }
    )
    if not data:
        logger(f"⚠️ Scoreboard data unavailable for {fmt}.")
        return None

    dur = float(sb_cfg.get("duration", 8.0))
    sub = sb_cfg.get("subtitle", "Dynamic Intelligent")

    score_path = debate_dir / f"scoreboard_{fmt}.mp4"
    if not score_path.exists():
        logger(f"🏁 Rendering scoreboard → {score_path.name}")
        if not score_renderer.render(data, score_path, fps, dur, topic, sub, 1.0, logger):
            return None
    else:
        logger(f"⏭️ Scoreboard exists: {score_path.name}")

    teaser_path = debate_dir / f"scoreboard_teaser_{fmt}.mp4"
    if not teaser_path.exists():
        logger(f"🎬 Rendering teaser → {teaser_path.name}")
        # Use full data variant (999 args = all)
        data_full = data.get("teaser_version", data)
        score_renderer.render(data_full, teaser_path, fps, dur*0.5, topic, sub, 0.75, logger)
    
    return score_path
```

## Comparison

| Aspect | Full Scoreboard | Teaser |
|--------|-----------------|--------|
| Duration | Full (8s default) | Half (4s default) |
| Scale | 100% (1.0) | 75% (0.75) |
| Arguments Shown | Limited to 3 (configurable) | **ALL** (no limit) |
| Screen Time | More detailed | Quick overview |
| Use Case | End credits | After intro hook |

## Why This Makes Sense

1. **Teaser Hook** - Shows all judge scores immediately to hook viewers
2. **Full Scoreboard** - Shows top 3 scores only (cleaner, less cluttered)
3. **Scale Factor** - Keep 0.75 (75%) to avoid overwhelming after intro
4. **Duration** - Keep half duration for quick teaser (4 seconds)

## Recommended Implementation

Use **Solution 1** (extract twice) because:
- ✅ Clearest intent
- ✅ Most flexible
- ✅ No changes to other functions
- ✅ Easy to maintain
- ✅ Can adjust limits independently

```python
# Extract with limit for main scoreboard
data_limited = extract_scores(debate_dir, md_suffix, {"debate_scoreboard_max_args": 3})

# Extract without limit for teaser
data_full = extract_scores(debate_dir, md_suffix, {"debate_scoreboard_max_args": 999})

# Render main with limited data
score_renderer.render(data_limited, score_path, fps, dur, topic, sub, 1.0, logger)

# Render teaser with full data, but KEEP the 0.75 scale
score_renderer.render(data_full, teaser_path, fps, dur*0.5, topic, sub, 0.75, logger)
```

## Clarification on "No Need to Remove"

You said "no need to remove from it" - meaning:
- ✅ **KEEP** the duration parameter: `dur*0.5` (4 seconds)
- ✅ **KEEP** the scale parameter: `0.75` (75%)
- ✅ **KEEP** the rendering call
- ✅ **ONLY CHANGE** what scores are shown (all vs 3)

So the scale factor `0.75` stays exactly as is. The only change is showing more arguments.

## Code Location to Modify

File: `unit_debate.py`
Function: `_resolve_scoreboard()`
Lines: 179-205

Apply Solution 1 modification to extract scores twice with different limits.
