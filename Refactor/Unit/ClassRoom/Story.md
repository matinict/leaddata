
# Story
We trying to build something powerful—but the way’ve described it is still too vague for automation to work reliably. If just “input topics” and expect a full classroom discussion video, the output will feel random and low-quality. What actually need is a **structured prompt system with roles, flow, and constraints**.
Let’s design a **Stage-2 “AI Classroom Engine Prompt System”** that can plug into  video automation pipeline (n8n / agents / TTS / avatars).

---

# 🎓 AI Classroom Prompt System (Teacher + 8 Students)

## 🧠 Core Idea

Each video = **multi-agent simulation**

* 1 Teacher (controls flow)
* 8 Students (different personalities)
* Topic-driven structured discussion
* Output = script → voice → video

---

# 🧩 1. MASTER SYSTEM PROMPT (Main Controller)

Use this as  **root prompt**

```
You are an AI Classroom Simulation Engine.

Generate a complete classroom discussion video script based on a given topic.

Class Structure:
- 1 Teacher (expert, clear, engaging)
- 8 Students (curious, diverse personalities)

Goals:
- Teach the topic step-by-step
- Encourage interaction (questions, answers, debate)
- Keep it simple for kids (age 10–15)
- Make it engaging and natural

Output Format STRICT:
1. Scene Title
2. Learning Objective (1-2 lines)
3. Full Dialogue Script (Teacher + Students)
4. Key Takeaways (bullet points)
5. Visual Suggestions (for video generation)

Rules:
- Each student must speak at least once
- Teacher leads but does NOT dominate
- Include at least:
  - 2 questions from students
  - 1 small debate/disagreement
  - 1 real-life example
- Keep sentences short and conversational
- No narration, only dialogue

Topic: {{TOPIC}}
```

---

# 👨‍🏫 2. TEACHER PROMPT

```
You are a friendly classroom teacher.

Style:
- Clear
- Encouraging
- Uses examples
- Asks questions

Responsibilities:
- Introduce topic
- Explain concepts step-by-step
- Ask students questions
- Manage discussion
- Summarize at end

Tone:
- Simple English
- Energetic but calm
```

---

# 👧👦 3. STUDENT PERSONALITIES (VERY IMPORTANT)

You need diversity or the video becomes boring.

### Example (use fixed identities for consistency across videos)

```
Student 1 (Curious): asks many questions
Student 2 (Smart): gives quick correct answers
Student 3 (Confused): asks for clarification
Student 4 (Creative): gives real-life examples
Student 5 (Funny): adds light humor
Student 6 (Debater): sometimes disagrees
Student 7 (Quiet): speaks less but meaningful
Student 8 (Beginner): very basic understanding
```

---

# 🔄 4. DISCUSSION FLOW TEMPLATE

This is what  AI MUST follow:

### Step 1: Introduction

Teacher introduces topic

### Step 2: Basic Explanation

Teacher explains simply

### Step 3: Student Interaction

* Questions
* Answers
* Confusion

### Step 4: Mini Debate

* Student disagrees
* Others respond
* Teacher resolves

### Step 5: Real-life Example

* Student or teacher gives example

### Step 6: Recap

Teacher summarizes

---

# 🎬 5. VIDEO AUTOMATION OUTPUT FORMAT

This is critical for  pipeline (TTS + avatars)

```
[SCENE 1]

Teacher: Today we will learn about photosynthesis.

Student 1: What is photosynthesis?

Student 3: I don't understand...

...

[END SCENE]

[KEY POINTS]
- Plants make food using sunlight
- Uses carbon dioxide and water

[VISUALS]
- Green plants
- Sunlight animation
- Diagram
```

---

# ⚙️ 6. n8n / AI PIPELINE IDEA

Since already use n8n + agents:

### Workflow:

1. Input Topic
2. OpenAI Agent → Generate Script (above prompt)
3. Split Dialogue → Each character
4. ElevenLabs → Voice per character
5. Avatar Engine (D-ID / HeyGen / 3D)
6. Merge → Final Video

---

# 🚀 7. POWER UPGRADE (IMPORTANT)

If want HIGH QUALITY output:

Add constraints like:

```
- Limit total dialogue to 60–90 seconds
- Each line max 12 words
- Use simple vocabulary (grade 5 level)
- Avoid repetition
```

---

# 💡 Example Topic Input

```
Topic: "Why do plants need sunlight?"
```


Good—you already have the hardest part: a **CrewAI content factory (debate/podcast → full video)**.

Now the real move is **NOT rebuilding everything**, but **adapting your existing debate engine into a “Kids Classroom Mode”**.

Right now:

* You generate **debates (multi-agent discussion)**
* KidsLearn system generates **structured narration videos**

👉 What you need = **Hybrid: Debate + Classroom = Interactive Learning Video**

---

# ⚠️ Reality Check (Important)

If you just reuse your debate prompt:

* ❌ Too complex for kids
* ❌ Too argumentative
* ❌ Not structured learning

So instead:
👉 Convert debate → **guided classroom discussion**

---

# 🧠 NEW MODE: “CLASSROOM DISCUSSION ENGINE”

This plugs directly into your existing CrewAI flow.

---

# 🧩 1. MASTER PROMPT (Drop-in Replacement)

Use this instead of your debate prompt:

```text
You are an AI Kids Classroom Simulation Engine.

Generate a classroom discussion video script for kids (age 6–10).

Participants:
- 1 Teacher (guides learning)
- 8 Students (different personalities)

Goal:
Teach the topic through interactive discussion, not debate.

Structure:
1. Hook (curiosity question)
2. Teacher explains simply
3. Students ask questions
4. Small disagreement (light, not aggressive)
5. Real-life example
6. Fun fact
7. Quiz question
8. Teacher summary

Rules:
- Simple words (grade 3–5 level)
- Each student speaks at least once
- Max total length: 60–90 seconds
- Each line under 12 words
- No complex arguments
- Make it fun and curious

Output format:

[SCENE]

Teacher: ...
Student 1: ...
...

[QUIZ]
...

[KEY POINTS]
...

Topic: {{TOPIC}}
```

---

# 👨‍🏫 2. CONVERT YOUR EXISTING ROLES

Your current system probably has:

* Moderator
* Debaters
* Opinions

👉 Replace like this:

| Old (Debate) | New (Classroom)               |
| ------------ | ----------------------------- |
| Moderator    | Teacher                       |
| Debater 1    | Curious Student               |
| Debater 2    | Smart Student                 |
| Aggressive   | Confused Student              |
| Opponent     | Friendly Disagreement Student |

---

# 🎭 3. STUDENT PERSONALITY PROMPTS

Reuse across ALL videos (important for consistency):

```text
Student Roles:

S1: Curious – asks questions
S2: Smart – gives correct answers
S3: Confused – asks “why”
S4: Creative – gives examples
S5: Funny – light humor
S6: Doubter – small disagreement
S7: Quiet – short but meaningful
S8: Beginner – very basic thinking
```

---

# 🔄 4. MODIFY YOUR CREWAI FLOW (Minimal Change)

You DO NOT need a new system.

Just change:

### Before:

```
Topic → Debate Script → Voice → Video
```

### After:

```
Topic → Classroom Script → Voice → Video
```

---

# ⚙️ 5. OUTPUT FORMAT (IMPORTANT FOR VIDEO)

Make sure your output is clean like this:

```text
[SCENE 1]

Teacher: Why do clouds float?

Student 1: Yeah, how do they stay up?

Student 3: I don’t understand clouds.

Teacher: Great question! Clouds are tiny water drops.

Student 2: Like small drops in the air?

Teacher: Exactly!

Student 6: But water falls… why not clouds?

Teacher: Good point! Warm air holds them up.

...

[QUIZ]
Why don’t clouds fall immediately?

A) Too heavy  
B) Warm air holds them  
C) They are empty  

[KEY POINTS]
- Clouds are water droplets
- Warm air keeps them up
```

---

# 🎬 6. WHY THIS FITS YOUR EXISTING SYSTEM

Your system already has:

* ✅ Multi-agent conversation
* ✅ Dialogue format
* ✅ Voice per speaker
* ✅ Video generation

So this upgrade gives you:

* 🎯 Kids-friendly content
* 🎯 Educational structure
* 🎯 Higher retention (YouTube Shorts)

---

# 🔥 7. BIG ADVANTAGE (You’re ahead)

Most people:

* Either do boring narration
* Or expensive animation

You:

* Already have **AI discussion engine**
* Now turning it into **interactive learning**

👉 That’s unique.

---

I’ve gone through your uploaded **CF2 Unit-KidsLearn spec**, and honestly—you’re very close to a scalable system. But there’s a gap between what you built and what you *want* (interactive classroom videos).

Let me break it down clearly 👇

---

# ✅ What Your Current System Does (Strong)

Your **Unit-KidsLearn** is already solid:

### ✔ Architecture Strength

* Topic → Script → Render → Publish ✔
* Fully automated (Scout + Data + Render + Publisher) ✔
* Lightweight (no GPU, reusable visuals) ✔

### ✔ Content Design

* Hook → Explain → Fun Fact → Quiz ✔
* Age-based tone config ✔
* Short-form optimized ✔

👉 This is basically a **Narration-based learning system (like Kurzgesagt-lite for kids)**

---

# ❌ What’s Missing (Your Actual Goal)

You said:

> “Teacher area + 8 students + classroom discussion”

But your current system:

* ❌ No multi-character interaction
* ❌ No classroom simulation
* ❌ No personality-based dialogue
* ❌ No dynamic engagement (only narration)

👉 So right now:
**You built “Kids Learning Videos”**
But you want:
**“AI Classroom Experience”**

---

# 🔥 The Core Gap

| Current System     | Needed Upgrade                   |
| ------------------ | -------------------------------- |
| Narrator voice     | Multi-character voices           |
| Linear script      | Interactive dialogue             |
| Static explanation | Dynamic discussion               |
| Single agent       | Multi-agent (Teacher + Students) |

---

# 🧠 Solution: Add “Classroom Layer” (DON’T REPLACE SYSTEM)

Do NOT destroy your current pipeline.

👉 Just extend it with a new mode:

---

# 🧩 NEW UNIT: `Unit-Classroom`

Add alongside:

* `Unit-KidsLearn` (existing)
* `Unit-Debate` (existing)

👉 New:

```bash
Unit-Classroom
```

---

# ⚙️ HOW IT FITS YOUR PIPELINE

### Current Flow:

```id="lrbx6n"
Scout → KidsLearn-Data → Render → Publish
```

### New Flow:

```id="bnr1p1"
Scout → Classroom-Data → Classroom-Render → Publish
```

---

# 🧠 1. Classroom Data Generator (IMPORTANT)

**New file:**

```bash
kidsclassroom_data_generator.py
```

### Output:

```
output/{topic}/classroom/
 classroom_script.md
 roles.json
 quiz.json
```

---

## 🔥 Prompt Design (Based on Your System)

Replace your current LLM instruction with this:

```text id="d4gxj9"
You are generating a kids classroom discussion.

Participants:
- 1 Teacher
- 8 Students (different personalities)

Goal:
Teach the topic through conversation.

Structure:
1. Hook question
2. Teacher explanation
3. Student questions
4. Small disagreement
5. Real-life example
6. Fun fact
7. Quiz
8. Summary

Rules:
- Age: 6–10
- Simple English
- Each student speaks at least once
- Max 90 seconds total
- Each line < 12 words

Output format:

[SCENE]

Teacher: ...
Student 1: ...
...

[QUIZ]
...

[KEY POINTS]
...
```

---

# 🎭 2. Roles.json (VERY IMPORTANT)

```json
{
 "Teacher": "friendly, clear, encouraging",
 "Student1": "curious",
 "Student2": "smart",
 "Student3": "confused",
 "Student4": "creative",
 "Student5": "funny",
 "Student6": "doubter",
 "Student7": "quiet",
 "Student8": "beginner"
}
```

👉 This enables:

* Voice mapping
* Avatar mapping
* Consistent personality across videos

---

# 🎬 3. Classroom Render (Upgrade your renderer)

**File:**

```bash
kidsclassroom_render.py
```

### Difference from your current renderer:

| KidsLearn      | Classroom           |
| -------------- | ------------------- |
| One narrator   | 9 voices            |
| Text animation | Dialogue bubbles    |
| Static flow    | Character switching |

---

## 🎥 Rendering Idea (LOW COST)

Since you avoid heavy GPU:

👉 Use:

* Same background loop ✔
* Add:

 * Name tags (Teacher / Student 1…)
 * Simple avatar icons (static PNG)
 * Text bubbles

👉 No 3D needed

---

# 🔊 4. Voice Mapping (You already use Edge TTS)

Extend like:

```json
{
 "Teacher": "en-US-AvaNeural",
 "Student1": "en-US-GuyNeural",
 "Student2": "en-GB-RyanNeural",
 "Student3": "en-US-JennyNeural"
}
```

---

# 🚀 5. BEST STRATEGY (IMPORTANT)

Do NOT replace KidsLearn.

👉 Run BOTH:

### Mode A:

* KidsLearn → fast, scalable, daily uploads

### Mode B:

* Classroom → premium, engaging content

---

# 💡 6. REAL OPPORTUNITY (Your Advantage)

You already have:

* Debate engine ✔
* Multi-agent system ✔
* Automation ✔

👉 Others don’t.

So you can create:

### 🔥 “AI Classroom Channel”

* Teacher + Students discussion
* Kids feel like they are inside class

---

# ⚠️ Critical Improvement Suggestion

Right now your system says:

> “No characters, no faces”

👉 That’s fine for KidsLearn
👉 But for Classroom:

You NEED at least:

* Simple avatars (even icons)
* Or name-based identity

Otherwise:
❌ Kids won’t connect

---

# 🧭 Final Direction

You now have 3 content engines:

1. **Debate Engine** → Adults
2. **KidsLearn Engine** → Simple learning
3. **Classroom Engine (NEW)** → Interactive kids learning ⭐

---

# 👉 What I Recommend Next

I can build for you:

### Option 1:

✅ Full `kidsclassroom_data_generator.py`

### Option 2:

✅ Full `kidsclassroom_render.py`

### Option 3:

✅ Complete CrewAI agents (Teacher + 8 Students)

---

Got it—you already have a **5-voice debate system running on Hugging Face**, and you don’t want to touch code right now. Perfect. Then the move is **pure prompt + role redesign**, not rebuilding anything.

Right now your system = **debate voices arguing**
You want = **classroom discussion teaching**

Those are close, but not the same.

---

# ⚠️ Key Adjustment (No Code Needed)

If you keep debate style:

* ❌ too aggressive
* ❌ confusing for kids
* ❌ no structured learning

👉 So instead of adding more voices (like 8 students), do this:

**Reuse your 5 voices → remap roles into classroom**

---

# 🔁 5-VOICE CLASSROOM MAPPING

Keep your exact voice system, just change behavior:

| Voice   | New Role         | Behavior                      |
| ------- | ---------------- | ----------------------------- |
| Voice 1 | Teacher          | explains + guides             |
| Voice 2 | Curious Student  | asks questions                |
| Voice 3 | Smart Student    | answers correctly             |
| Voice 4 | Confused Student | asks “why / don’t understand” |
| Voice 5 | Doubter Student  | small disagreement            |

👉 This alone transforms debate → classroom.

---

# 🧠 DROP-IN PROMPT (Use This Directly)

Replace your debate prompt with this:

```text
You are simulating a kids classroom discussion.

Participants:
- 1 Teacher
- 4 Students

Goal:
Teach the topic through conversation, not argument.

Rules:
- Age: 6–10
- Use very simple English
- Keep sentences short (max 10–12 words)
- Friendly tone (no aggressive debate)
- Each student must speak at least once

Flow:
1. Teacher asks a curiosity question (hook)
2. Students react
3. Teacher explains simply
4. Students ask questions
5. One student slightly disagrees
6. Teacher clarifies
7. Give real-life example
8. Add one fun fact
9. End with a quiz question

Output format:

Teacher: ...
Student A: ...
Student B: ...
Student C: ...
Student D: ...

[QUIZ]
...

[KEY POINTS]
...

Topic: {{TOPIC}}
```

---

# 🎯 WHAT CHANGES IN YOUR OUTPUT

### Before (Debate style):

* “I disagree strongly…”
* “That argument is wrong…”

### After (Classroom style):

* “I don’t understand…”
* “But I thought water falls?”
* “Ohhh now I get it!”

👉 Same system, totally different feel.

---

# 🔥 MICRO-OPTIMIZATION (VERY IMPORTANT)

Add this line to your prompt:

```text
Do NOT use complex words. Speak like talking to a child.
```

And:

```text
Keep total conversation under 80 seconds.
```

---

# 🎬 VIDEO RESULT (WITH YOUR CURRENT PIPELINE)

You’ll automatically get:

* 🎙️ 5 different voices → feels like classroom
* 🧠 Natural Q&A → better retention
* 📈 Better YouTube engagement (kids stay longer)

---

# 💡 Smart Insight (Your Advantage)

Most people try:

* 3D animation ❌ expensive
* Cartoon videos ❌ time-consuming

You:

* Already have **multi-voice AI discussion**
* Just shifting tone → **instant classroom product**

👉 That’s actually very strong.

---

I checked your **CrewAI core + KidsLearn spec**, and here’s the honest technical verdict:

---

# 🧠 1. Your System is Already Advanced (Important)

From :

👉 You have:

* Modular **Unit-based architecture**
* Clean separation: `Scout → Data → Animation → Packaging → Publisher`
* Dedicated **Unit-Debate** with:

  * `debate_debater`
  * `debate_judge`
  * `debate_video_producer`
* LLM fallback system (very strong design)

👉 From :

* KidsLearn = **narration engine**
* Debate = **multi-agent discussion engine**

---

# ⚠️ 2. The REAL Problem (Core Insight)

Your system has **TWO extremes**:

### Mode A: KidsLearn

* Structured
* Educational
* ❌ No interaction

### Mode B: Debate

* Multi-voice
* Interactive
* ❌ Too argumentative for kids

👉 Missing middle layer:

# ❌ “Guided Classroom Discussion”

---

# 🔥 3. GOOD NEWS: You DON'T Need New Unit

You already have everything:

* ✅ Multi-agent (debate)
* ✅ Video generator
* ✅ Voice system (5 voices)
* ✅ Automation pipeline

👉 So:
**DO NOT create new Unit-Classroom (waste of time)**

Instead:

# 👉 Modify Unit-Debate Behavior

---

# 🔁 4. Convert Debate → Classroom (Smartest Move)

Your current debate agents:

```text
debate_debater
debate_judge
debate_debater_m
debate_judge_m
```

👉 Keep ALL of this.

Just change **agents.yaml behavior**

---

# 🧩 5. ROLE TRANSFORMATION (CRITICAL)

Replace debate personalities like this:

| Current     | New Classroom Role               |
| ----------- | -------------------------------- |
| debater     | Teacher                          |
| debater (2) | Smart Student                    |
| debater (3) | Curious Student                  |
| debater (4) | Confused Student                 |
| judge       | Friendly Guide / Summary Teacher |

👉 Same architecture → different behavior

---

# 🧠 6. PROMPT UPGRADE (THIS IS THE KEY)

Right now your debate prompt likely says:

* argue
* oppose
* defend

👉 Replace with:

```text
You are part of a kids classroom discussion.

DO NOT debate aggressively.

Goal:
Explain the topic in a friendly, interactive way.

Roles:
- One teacher (guides explanation)
- Students ask questions, think, and sometimes get confused

Rules:
- Use very simple English (age 6–10)
- No long arguments
- No complex logic
- Keep responses short
- Make it feel like a real classroom

Flow:
1. Teacher introduces topic
2. Students react
3. Teacher explains
4. Students ask questions
5. One student slightly disagrees
6. Teacher clarifies simply
7. End with summary

Important:
- Do NOT behave like a debate
- Behave like a classroom conversation
```

---

# ⚙️ 7. WHY THIS FITS YOUR CREW

From :

👉 Your flow is **sequential tasks**

```text
debate_propose → debate_oppose → debate_decide
```

👉 You don’t need to change flow.

Just reinterpret:

| Task    | New Meaning                  |
| ------- | ---------------------------- |
| propose | Teacher introduces           |
| oppose  | Student questions            |
| decide  | Teacher explains + concludes |

---

# 🎬 8. VIDEO LAYER (Already Compatible)

Your:

* `DebateVideoTool`
* `DebateMergeTool`

👉 Already perfect for:

* Multi-speaker audio
* Dialogue sequencing

No change needed.

---

# ⚠️ 9. One Critical Weakness

Right now your system:

> “No characters, no faces”

That’s fine for KidsLearn.

But for classroom:

👉 At minimum you NEED:

* Speaker labels (Teacher / Student A)
* OR voice identity cues

Otherwise:
❌ Kids won’t follow conversation

---

# 🚀 10. FINAL STRATEGY (BEST PATH)

Do NOT:

* ❌ Create new unit
* ❌ Rewrite pipeline
* ❌ Add complexity

Do:

### Step 1:

Modify `agents.yaml` (behavior only)

### Step 2:

Replace debate prompt → classroom prompt

### Step 3:

Keep everything else SAME

---

# 💡 11. Your Hidden Advantage

Most people:

* Can’t do multi-agent properly

You:

* Already built it ✔
* Already automated ✔

👉 You’re 80% done

That actually clarifies everything—and it changes the strategy.

👉 If your **debate system is already in production on YouTube**, then you should **NOT touch it at all**. Don’t mix classroom logic into it. That would risk breaking something that’s already working.

---

# ⚠️ Correct Direction (Important)

Right now you have:

### ✅ Project A: Debate Engine (LIVE)

* Multi-voice ✔
* Automated ✔
* YouTube running ✔

### 🧪 Project B: KidsLearn (NEW)

* Narration-based ✔
* Educational ✔
* Needs improvement

---

# ❌ What You SHOULD NOT Do

* Don’t modify `Unit-Debate`
* Don’t change debate prompts
* Don’t merge classroom into debate pipeline

👉 That’s a production system. Keep it stable.

---

# ✅ What You SHOULD Do Instead

# 👉 Build Classroom as a SEPARATE MODE (inside KidsLearn)

You already have this from :

* `Unit-KidsLearn` (narration pipeline)

Now extend it slightly:

---

# 🧠 1. Add “Mode Switch” (No new project)

Inside your config:

```json
{
 "kids_mode": "narration"
}
```

OR

```json
{
 "kids_mode": "classroom"
}
```

---

# 🔁 2. Behavior Change Based on Mode

### Mode A (Current):

```
narration → single voice → kinetic text
```

### Mode B (New):

```
classroom → 5 voices → dialogue style
```

---

# 🧩 3. Reuse Your Debate Voice System (Smart Move)

You said:

> “already 5 voice huggingface model”

👉 Perfect.

Use SAME voices, but only inside KidsLearn:

| Voice   | Role             |
| ------- | ---------------- |
| Voice 1 | Teacher          |
| Voice 2 | Curious student  |
| Voice 3 | Smart student    |
| Voice 4 | Confused student |
| Voice 5 | Funny / Doubter  |

---

# 🧠 4. Classroom Prompt (KidsLearn ONLY)

Use this inside your **kidslearn_data_generator**, not debate:

```text
You are generating a kids classroom discussion.

Participants:
- 1 Teacher
- 4 Students

Goal:
Teach the topic in a fun, simple way.

Rules:
- Age 6–10
- Very simple English
- Short sentences
- Friendly tone

Structure:
1. Teacher asks a fun question
2. Students react
3. Teacher explains
4. Students ask questions
5. One student gets confused
6. Teacher clarifies
7. Add fun fact
8. End with quiz

Output:

Teacher: ...
Student A: ...
Student B: ...
Student C: ...
Student D: ...

[QUIZ]
...

[KEY POINTS]
...
```

---

# 🎬 5. Rendering Strategy (Keep It Cheap)

From your system:

> reusable background + text overlay

👉 Keep that.

Just add:

* Speaker labels (Teacher / Student A)
* Different voice per line

👉 No need:

* ❌ 3D animation
* ❌ avatars (optional later)

---

# 🚀 6. Final Architecture (Clean)

### 🔵 Debate Project (unchanged)

```
Topic → Debate → Video → YouTube
```

### 🟢 KidsLearn Project (extended)

```
Topic → KidsLearn
       ├── narration mode
       └── classroom mode (NEW)
```

---

# 💡 7. Business Advantage

Now you have:

| System              | Audience         |
| ------------------- | ---------------- |
| Debate              | Adults / general |
| KidsLearn narration | Basic kids       |
| KidsLearn classroom | Engaging kids ⭐  |

👉 This is powerful:
You’re covering **multiple content markets with one core engine**

---

# 🔥 My Recommendation (Strategic)

Start like this:

1. Keep Debate running (don’t touch)
2. Launch KidsLearn narration (baseline)
3. Add Classroom mode as “premium content”

---
Good—since you only want **prompt design (no code)**, I’ll give you a **production-ready classroom mode prompt system** that fits directly into your existing KidsLearn pipeline and works with your 5 voices.

This is not generic—you can drop this into your LLM step and it will produce **consistent, structured, video-ready classroom dialogue**.

---

# 🎓 FULL CLASSROOM MODE PROMPT SYSTEM

You will use **ONE master prompt + fixed role definitions**.

---

# 🧠 1. MASTER PROMPT (FINAL – USE THIS)

```text
You are an AI Kids Classroom Simulation Engine.

Your job is to generate a short classroom discussion script for a video.

Audience:
- Kids age 6–10

Participants (5 total):
- 1 Teacher
- 4 Students

Goal:
Teach the topic through a fun, simple, interactive classroom discussion.

STRICT RULES:
- Use very simple English (grade 3–5 level)
- Each sentence must be short (max 10–12 words)
- Keep total script length suitable for 60–90 seconds
- No complex explanations
- No long paragraphs
- Only dialogue (no narration)

BEHAVIOR RULES:
- Teacher explains clearly and asks questions
- Students react naturally (curious, confused, playful)
- One student must misunderstand something
- One student must slightly disagree
- Keep tone friendly, never argumentative

STRUCTURE (MUST FOLLOW EXACTLY):

[SCENE]

1. Hook (Teacher asks a fun or surprising question)
2. Student reactions (at least 2 students respond)
3. Teacher simple explanation
4. Student questions (curious + confused)
5. Small disagreement (one student challenges idea)
6. Teacher clarification (very simple)
7. Real-life example (easy to imagine)
8. Fun fact (short “wow” moment)
9. Quick recap (teacher)
10. Quiz question (for kids watching)

OUTPUT FORMAT (STRICT):

Teacher: ...
Student A: ...
Student B: ...
Student C: ...
Student D: ...

[QUIZ]
Question: ...
Options:
A) ...
B) ...
C) ...

[KEY POINTS]
- ...
- ...
- ...

Topic: {{TOPIC}}
```

---

# 🎭 2. FIXED STUDENT PERSONALITIES (IMPORTANT)

Add this **below your prompt OR inside system message**:

```text
Student Roles:

Student A (Curious):
- Asks “what”, “how”, “why”

Student B (Smart):
- Gives quick, simple correct answers

Student C (Confused):
- Says “I don’t understand” or asks basic questions

Student D (Doubter/Funny):
- Slightly disagrees OR says something funny/simple
```

👉 This ensures **consistent behavior across all videos**

---

# 🎯 3. MICRO-CONTROL RULES (VERY IMPORTANT)

Add these lines to improve quality:

```text
- Do NOT use difficult words
- Do NOT explain like a textbook
- Make it feel like real kids talking
- Use everyday examples (water, sun, ball, air, food)
- Avoid repetition
- Keep it fun and curious
```

---

# 🔊 4. VOICE MAPPING (FOR YOUR SYSTEM)

Since you already have 5 voices:

| Speaker   | Voice   |
| --------- | ------- |
| Teacher   | Voice 1 |
| Student A | Voice 2 |
| Student B | Voice 3 |
| Student C | Voice 4 |
| Student D | Voice 5 |

---

# 🎬 5. EXPECTED OUTPUT STYLE (EXAMPLE)

If topic = *“Why do shadows appear?”*

You’ll get:

```text
[SCENE]

Teacher: Why do we see shadows?

Student A: Yes! Why do they follow us?

Student B: Light makes shadows, I think.

Teacher: Good! Light creates shadows.

Student C: I don’t understand that.

Teacher: When light is blocked, shadow appears.

Student D: But shadows move! That’s weird.

Teacher: They move because light position changes.

Teacher: Like sun moving in the sky.

Student A: Ohhh, that makes sense!

Teacher: Fun fact! Shadows can be very long at sunset.

Teacher: So shadows need light and something blocking it.

Teacher: Now a quick question!

[QUIZ]
Question: What makes a shadow?
Options:
A) Sound  
B) Light blocked  
C) Wind  

[KEY POINTS]
- Shadows need light
- Objects block light
- Position changes shadow size
```

---

# 🔥 6. WHY THIS WORKS (WITH YOUR SYSTEM)

Fits perfectly with your:

* ✅ Multi-voice pipeline
* ✅ Dialogue-based rendering
* ✅ No need for new tools
* ✅ Works with reusable visuals

---

# ⚠️ 7. COMMON MISTAKES (AVOID)

If you don’t include rules above, model will:

* ❌ Start debating
* ❌ Use complex language
* ❌ Write long explanations
* ❌ Lose “kid feeling”

---

# 🚀 FINAL RESULT

With this prompt, your system becomes:

👉 “AI Classroom Channel”
instead of
👉 “AI Narration Channel”

---
 
