# **CF2 Unit-KidsLearn — FINAL SPEC**

---

## 🎯 THE PROBLEM & SOLUTION

### **Your Core Conflict**
You want to build an automated YouTube channel for kids learning that:
- Changes topic automatically (`topic = "auto"`)
- Produces unique content daily
- Avoids generic kids content (no ABCs, no animals)
- Stays lightweight (no expensive GPU, no Sora/Runway, no manual asset creation)

**The Blocker:** Kids content *usually* demands new visuals per topic, but your system is built on **reusable clip loops** and lightweight automation.

### **The Insight (Solves Everything)**
You're not building *animation*—you're building a **system-driven content factory** where:
- **The idea drives the content** (topic → script → structure changes)
- **Visuals remain a reusable container** (fixed background loops + dynamic text overlays)
- **Differentiation comes from curation + automation**, not pixel variety

This solves the conflict perfectly: automated daily production, unique educational content, lightweight costs, all within CF2's design philosophy.

---

## 🏗️ ARCHITECTURE: UNIT-KIDSLEARN

Unit-KidsLearn extends CF2 with a kids-learning-specific pipeline that reuses your existing video infrastructure.

### **Visual Foundation (One-Time Creation)**

A single, reusable visual container:
- **Looping background**: A calming, educational space (e.g., cozy isometric study room, abstract particle pattern, or simple colored loop)
- **Fixed intro/outro clips**: Same welcome and subscribe CTAs for all topics
- **Recurring visual motifs**: Simple reusable icons (lightbulb, question mark, star) that appear during key moments
- **Character element** (optional): A friendly, simple static sticker or 3-frame blink loop that "reacts" to new facts

**Cost:** One-time creation, zero per-topic costs.

### **Content Generation Layer (Unit-KidsLearn-Data)**

Extends `Unit-Data` with a kids-specific agent.

**Input:** Topic + age group + vocabulary config
**Output:**
```
output/{TopicSlug}/
  kids_learning/
    learning_script.md      ← structured sections: "What is X?", "Why is it cool?", "Fun Fact!"
    quiz_questions.json     ← 2-3 interactive questions
    vocabulary.json         ← definitions with kid-friendly analogies
```

**Script Structure (Reusable Template):**
1. **Hook (10-15s):** Big surprising question ("Did you know clouds weigh 1 million pounds?")
2. **What Is It?** (20-30s): Simple analogy-driven explanation ("Like a fluffy pillow made of water")
3. **Why Is It Cool?** (20-30s): One mind-blowing connection ("Air carries them like invisible balloons")
4. **Fun Fact** (10-15s): Memorable insight with "wow" moment
5. **Quiz or "Try This!"** (10s): On-screen question kids can pause and answer
6. **Closing Wonder** (5-10s): Spark curiosity for next video

**Tone Config (Switches All Script Generation):**
```json
{
  "age_group": "6-10",
  "vocabulary_level": "simple",
  "pacing": "slow",
  "tone": "wonder-inducing",
  "include_quiz": true,
  "max_script_chars": 800
}
```

**LLM Persona Instruction:**
> "Explain as if talking to a curious 8-year-old. Use simple analogies. No jargon. Lead with 'This is so cool because...' Make it feel like discovery, not school. Ask playful questions. End with wonder."

### **Rendering Layer (Unit-KidsLearn-Render)**

Adapts `definition_video.py` to composite the learning script over reusable visuals.

**Input:** `learning_script.md` + optional AI-generated background image
**Output:** `kidslearn_{fmt}_{lang}_with_audio.mp4` (Shorts + HD)

**Rendering Pipeline:**
1. Load reusable background loop
2. Apply kinetic typography: text pops, bounces, slides as narrator speaks
3. Layer simple visual effects (highlight circles, sparkles on key facts)
4. Composite fixed intro clip (2 sec) + animated content (60-90 sec) + fixed outro (2 sec)
5. Generate TTS audio with kid-appropriate voice (bright, energetic)
6. Merge audio + video

**Config-Driven Customization:**
- Background: Reusable loop or optionally AI-generated still image ($0.02 cost)
- Pacing: Slow/wonder mode (longer pauses) vs. fast/adventure mode (quick cuts)
- Colors: Auto-apply section themes (blue = "What?", yellow = "Wow!", green = "Try This!")
- Recurring visual motifs: Same icons, animations, and character reactions every video

### **Composition Layer (No New Unit)**

No separate publisher needed—use existing `Unit-Publisher`:
- Generate YouTube metadata (title, description, tags) from learning script
- Create CC subtitles in 10+ languages
- Upload to YouTube (public, Education category #27)
- Post to social platforms

### **Topic Curation Layer (Extends Scout)**

Use existing `Unit-Scout` with kids-specific niches:
```json
{
  "niches": [
    "Kids science",
    "Why questions",
    "How things work",
    "Nature wonders",
    "Space and stars",
    "Human body",
    "Everyday magic",
    "Future and tech (kids)"
  ],
  "min_virality_score": 60,
  "use_web_search": true
}
```

Scout finds trending "Why...?" or "How...?" questions from kids' content communities, filters by niche and age-appropriateness, ranks by novelty + educational value, and populates a queue.

---

## ⚙️ CONFIG PROFILE: dataKids.json

```json
{
  "_comment": "Kids Learning Channel — PlayOwnAi Kids, tone & structure overrides only",

  "topic": "auto",
  "channel": "PlayOwnAi Kids",
  "channel_lower": "playownaikids",
  "website": "youtube.com/@PlayOwnAiKids",

  "video_formats": ["Shorts", "HD"],
  "video_fps": 30,
  "audio_speed": 1.1,
  "audio_speed_hd": 0.95,
  "tts_engine": "edge-tts",
  "audio_lang": "en",

  "watermark_enabled": true,
  "watermark_text": "@PlayOwnAiKids",
  "watermark_opacity": 60,

  "start": 2026,
  "end": 2026,
  "granularity": "daily",

  "kids_config": {
    "age_group": "6-10",
    "vocabulary_level": "simple",
    "pacing": "slow",
    "tone_mode": "wonder-inducing",
    "include_quiz": true,
    "max_script_chars": 800,
    "fact_count": 2,
    "use_ai_background": true,
    "background_prompt": "bright cheerful abstract educational space, soft colors, floating shapes, no text, no people, no faces"
  },

  "unit_switches": {
    "Unit-Scout": true,
    "Unit-Data": true,
    "Unit-KidsLearn": true,
    "Unit-Packaging": true,
    "Unit-Publisher": true,
    "Unit-Advertise": false,
    "Unit-Debate": false,
    "Unit-Animation": false
  },

  "scout_config": {
    "force_scraping": false,
    "platforms": ["scraping_url", "YouTube"],
    "niches": [
      "Kids science",
      "Why questions",
      "How things work",
      "Nature wonders",
      "Kids learning"
    ],
    "min_virality_score": 60,
    "output_queue_size": 20,
    "auto_consume": true,
    "use_web_search": true,
    "llm_scout": "deepseek/deepseek-chat"
  },

  "animation_config": {
    "definition_enabled": true,
    "definition_max_chars": 800,
    "intro_enabled": true,
    "intro_duration": 3,
    "intro_duration_hd": 5,
    "intro_slug": "Learn something new today!",
    "llm_definition": "deepseek/deepseek-chat"
  },

  "packaging_config": {
    "video_style": ["kidslearn"],
    "generate_youtube_metadata": true,
    "generate_thumbnail": true,
    "yt_metadata_lang": "15",
    "yt_cc_lang": "10",
    "llm_youtube": "deepseek/deepseek-chat"
  },

  "publisher_config": {
    "yt_upload": true,
    "yt_upload_config": {
      "upload_youtube_video": true,
      "upload_privacy": "public",
      "upload_category_id": "27",
      "upload_cc": true,
      "upload_notify_subscribers": false,
      "yt_pin_comment_gen": true
    }
  },

  "edge_tts_voices": {
    "narrator": {
      "edge_voice": "en-US-AvaNeural"
    },
    "quiz_voice": {
      "edge_voice": "en-US-GuyNeural"
    }
  }
}
```

---

## 🛠️ IMPLEMENTATION ROADMAP

### **Phase 1: Data Generation**

**File:** `src/cf2/tools/kidslearn_data_generator.py`

**LLM Agent:** "Kids Learning Specialist" (in `agents.yaml`)

**Responsibilities:**
- Read topic from inputs
- Generate structured learning script (4-5 sections, simple analogies)
- Create quiz questions (2-3, open-ended)
- Output `learning_script.md`, `quiz_questions.json`, `vocabulary.json`

**Smart Skip Check:**
```python
if os.path.exists(f"output/{slug}/kids_learning/learning_script.md"):
    return "⏭️ Skipped — learning script exists"
```

### **Phase 2: Visual Rendering**

**File:** `src/cf2/tools/kidslearn_render.py`

**Responsibilities:**
- Load reusable background loop (configured path)
- Apply kinetic typography from learning_script.md
- Layer visual effects (highlights, icons, sparkles)
- Generate TTS audio with selected voice + speed config
- Merge into video (intro + content + outro)
- Output: `kidslearn_{fmt}_{lang}_with_audio.mp4`

**Smart Skip Check:**
```python
if os.path.exists(f"output/{slug}/kidslearn_{fmt}_with_audio.mp4"):
    return "⏭️ Skipped — video exists"
```

**Config-Driven Customization:**
- Background source: `kids_config.background_prompt` → triggers AI image generation (optional) or uses fixed loop path
- Pacing: `kids_config.pacing` → controls delay between text animations
- Colors: `kids_config.tone_mode` → selects color scheme
- Voice: `edge_tts_voices.narrator` → TTS voice selection
- Speed: `audio_speed` + `audio_speed_hd` → narration tempo

### **Phase 3: AI Background Generation (Optional)**

**Integrated into kidslearn_render.py:**

When `kids_config.use_ai_background` = true:
- Call Replicate API with `background_prompt` (low-cost, ~$0.02)
- Save as static image (`background.png`)
- Use as overlay behind kinetic text
- If API fails, fall back to fixed loop

**Cost:** ~$0.02 per video (negligible)

### **Phase 4: Metadata & Publishing**

**Extend existing `Unit-Packaging` + `Unit-Publisher`:**
- Detect `video_style: "kidslearn"` in config
- Generate title, description, tags from learning_script.md
- Create CC subtitles from script + TTS
- Upload to YouTube (category: Education #27, public)
- Auto-pin LLM-generated comment ("Did you know...?")
- Post to social (LinkedIn, Instagram, Facebook)

### **Phase 5: Topic Curation**

**Use existing `Unit-Scout`:**
- Set `niches` to kids-learning keywords
- Run daily to find trending "Why...?" questions
- Filter for age-appropriateness (simple concept check)
- Populate output queue
- FlowController auto-consumes with `topic: "auto"`

---

## 📊 FILE STRUCTURE

```
output/
  WhyCloudFloat/
    kids_learning/
      learning_script.md         ← sections: What, Why Cool, Fun Fact, Quiz
      quiz_questions.json
      vocabulary.json
      background.png             ← AI-generated (optional)
    kidslearn_Shorts_En_with_audio.mp4
    kidslearn_HD_En_with_audio.mp4
    YT/
      Shorts/
        MD/
          en.txt                 ← title, description
          fr.txt, de.txt, ...    ← 10+ languages
        CC/
          en.srt                 ← subtitles
          fr.srt, de.srt, ...
        Th/
          thumbnail.jpg
    meta.json                    ← unit run status
    .lock                        ← crash recovery
```

---

## 💡 CONTENT EXAMPLE

### **Input Topic:** "Why Do Clouds Float?"

### **Unit-KidsLearn-Data Output:**

```markdown
# What Is a Cloud?

A cloud is billions of tiny water droplets floating in the sky.
Think of it like a fluffy pillow made of water!
The droplets are so small you can't see them individually—
they stick together to look like one big, fluffy thing.

## Why Do Clouds Float?

Clouds don't actually float—they're held up by warm air rising!
Hot air is lighter than cold air, so it pushes the water droplets up.
It's like the air is an invisible elevator carrying the cloud.

## Fun Fact!

A cloud weighs about 1 million pounds—that's 500 elephants!
But it still floats because the air underneath is strong enough.

## Question for You

If clouds are made of water, why don't they fall as rain right now?
(Hint: Think about how light the droplets are...)

## Try This!

Ask a grown-up: Why is some water called vapor?
(It's the invisible water floating in the air!)
```

### **Unit-KidsLearn-Render Output:**

```
[00:00-02:00] Intro clip
  - Voice: "Welcome to PlayOwnAi Kids!"
  - Reusable welcome animation

[02:00-15:00] What Is a Cloud?
  - Background loop starts
  - Text "What Is a Cloud?" pops on screen
  - Friendly narrator voice reads
  - Small lightbulb icon appears
  - Each sentence fades in as it's spoken

[15:00-30:00] Why Do Clouds Float?
  - Section color shifts to yellow
  - Text animation style changes (bounces instead of fades)
  - Narrator explains with wonder tone
  - Question mark icon appears

[30:00-45:00] Fun Fact!
  - "1 MILLION POUNDS!" appears in large, bold text
  - Sparkle effect around numbers
  - Elephant icon shows size comparison
  - Narrator delivers with excitement

[45:00-55:00] Question for You
  - Quiz appears on screen
  - Pause point for kids to think
  - Alternative voice reads question

[55:00-60:00] Try This!
  - Green section, gentle tone
  - Simple home activity suggestion
  - Character winks

[60:00-62:00] Outro clip
  - Reusable subscribe CTA
  - "Learn more at PlayOwnAi Kids"
```

**Total video:** 62 seconds (Shorts format), perfect for YouTube Shorts

---

## 🎯 WHY THIS WORKS (CF2 COMPLIANCE)

✅ **Rule 1-5:** Data generates (`Unit-KidsLearn-Data`), render consumes (`Unit-KidsLearn-Render`), strict separation  
✅ **Rule 6:** No data regeneration—render only reads and composes  
✅ **Rule 10-12:** One topic = one workspace with slug-based folder + collision handling  
✅ **Rule 13-14:** `meta.json` tracks unit state, smart skip prevents reruns  
✅ **Rule 21:** FlowController is the ONLY entry point  
✅ **Rule 23:** All values (tone, voice, pacing, AI usage) come from config, not hardcoded  
✅ **Rule 24:** Smart skip checks happen before any expensive operation  

**New Principle:** Visual reuse doesn't mean content repetition. Structure + automation + idea curation = differentiation.

---

## 🚀 YOUR DIFFERENTIATION

**Not:** Generic kids animation, manual asset creation, expensive video generation

**But:**
- **Automated discovery** (scout finds trending curiosity questions)
- **Educational scripting** (LLM writes for wonder + simplicity)
- **Lightweight composition** (reusable visuals + dynamic text = daily unique videos)
- **Zero manual work** (from topic to publish, fully automated)

**Position:** "Automated Educational Discovery for Curious Kids" — a niche no one else is filling at scale.

---

## 📋 NEXT IMMEDIATE STEPS

1. **Create `kidslearn_data_generator.py`** — kids script LLM agent
2. **Create `kidslearn_render.py`** — kids video renderer (adapts `definition_video.py`)
3. **Add kids LLM persona** to `agents.yaml` (wonder-inducing tone)
4. **Update `crew.py`** to register new tools
5. **Add `Unit-KidsLearn` entry** to `units/__init__.py`
6. **Test with 1 topic:** "Why do we dream?" → full pipeline run
7. **Deploy dataKids.json** profile + launch scout queue

---

## 📝 FINAL PRINCIPLE

> **"The idea drives the content. Automation handles production. Reusable visuals provide the stage. Your competitive edge is curation + speed, not pixel count."**

This is **Unit-KidsLearn**: A system-driven content factory that turns curious questions into daily educational videos, automatically.
