# CF2 Flow — Dynamic Task Assignment Map
# ✅ Tasks assigned dynamically per unit at runtime
# ❌ No hardcoded index (full_crew.tasks[N] is DEAD)

---

## 🔥 Core Principle

```
Flow → Unit → reads inputs → assigns only needed agents+tasks → runs
```

Each unit checks `inputs` flags at runtime to decide what to run.
No task is hardcoded. No index is used. Everything is name-based.

---

## 🗺️ Unit → Agent → Task Map

### Unit-Scout
| Agent                | Task                    | Guard (inputs flag)     |
|----------------------|-------------------------|-------------------------|
| social_scout_unit    | scout_trending_topics   | social_scout_unit=true  |

---

### Unit-Data  🔥 (always runs first)
| Agent                | Task                    | Guard                   |
|----------------------|-------------------------|-------------------------|
| data_researcher      | research_data           | always                  |
| csv_generator        | generate_csv            | always                  |
| definition_specialist| define_topic            | definition_enabled=true |
| definition_specialist| create_debate_definition| debate_enabled=true     |
| debater              | debate_propose          | debate_enabled=true     |
| debater_m            | debate_propose_m        | debate_short=true       |
| judge                | debate_decide           | debate_enabled=true     |
| judge_m              | debate_decide_m         | debate_short=true       |

---

### Unit-Debate
| Agent                  | Task                  | Guard                      |
|------------------------|-----------------------|----------------------------|
| debate_video_producer  | create_debate_video   | debate_video_enabled=true  |
| audio_engineer         | add_audio             | audio_enabled=true         |
| debate_merge_specialist| debate_merge          | debate_merge_enabled=true  |
| debate_merge_specialist| debate_merge_m        | debate_short=true          |

---

### Unit-Definition
| Agent                    | Task                    | Guard                   |
|--------------------------|-------------------------|-------------------------|
| definition_specialist    | define_topic            | definition_enabled=true |
| definition_video_producer| create_definition_video | definition_video=true   |

---

### Unit-Animation
| Agent                  | Task                  | Guard                        |
|------------------------|-----------------------|------------------------------|
| intro_clip_producer    | create_intro_clip     | intro_enabled=true           |
| bar_race_video_producer| create_bar_race_video | bar_race_video_enabled=true  |
| bar_race_audio_engineer| add_audio             | bar_race_audio_enabled=true  |
| bar_merge_specialist   | bar_merge             | bar_merge_enabled=true       |

---

### Unit-Comparison
| Agent   | Task            | Guard               |
|---------|-----------------|---------------------|
| debater | debate_propose  | always              |
| debater | debate_oppose   | always              |
| judge   | debate_decide   | always              |

---

### Unit-Publisher
| Agent                    | Task                     | Guard                   |
|--------------------------|--------------------------|-------------------------|
| yt_narration_specialist  | generate_narration       | yt_narration=true       |
| yt_metadata_specialist   | generate_youtube_metadata| always                  |
| yt_thumbnail_specialist  | generate_thumbnail       | always                  |
| youtube_upload_specialist| upload_to_youtube        | yt_upload=true          |
| facebook_upload_specialist| upload_to_facebook      | fb_upload=true          |
| social_share_specialist  | share_to_social          | social_share=true       |

---

### Unit-Advertise
| Agent  | Task           | Guard              |
|--------|----------------|--------------------|
| TBD    | subUnitShorts  | shorts_enabled=true|
| TBD    | subUnitTvc     | tvc_enabled=true   |
| TBD    | subUnitSocial  | social_enabled=true|

---

## ⚡ How Dynamic Assignment Works

```python
# Inside each unit runner — example from unit_publisher.py
agents, tasks = [], []

if inputs.get("yt_narration"):
    agents.append(factory.yt_narration_specialist())
    tasks.append(factory.generate_narration())

# always
agents.append(factory.yt_metadata_specialist())
tasks.append(factory.generate_youtube_metadata())

# always
agents.append(factory.yt_thumbnail_specialist())
tasks.append(factory.generate_thumbnail())

if inputs.get("yt_upload"):
    agents.append(factory.youtube_upload_specialist())
    tasks.append(factory.upload_to_youtube())

if inputs.get("fb_upload"):
    agents.append(factory.facebook_upload_specialist())
    tasks.append(factory.upload_to_facebook())

if inputs.get("social_share"):
    agents.append(factory.social_share_specialist())
    tasks.append(factory.share_to_social())

factory.crew().kickoff(agents=agents, tasks=tasks, inputs=inputs)
```

---

## ✅ Rules

1. **Always pair agent + task together** — never add one without the other
2. **Guard with `inputs.get(flag)`** — never hardcode True/False
3. **Order matters** — sequential process, tasks run top to bottom
4. **Never use index** — `tasks[N]` is forbidden in flow architecture
