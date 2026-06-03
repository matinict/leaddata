
"""
🧩 crew.py — Tool Registry Only (Updated v2)
Flow controls execution. Crew just provides agents + tasks.
Naming convention: {unit}{role}
scout*       → Unit-Scout
data_*        → Unit-Data
leaddata_*    → Unit-LeadData
animation_*   → Unit-Animation
definition_*  → Unit-Definition
debate_*      → Unit-Debate
packaging_*   → Unit-Packaging
publisher_*   → Unit-Publisher
advertise_*   → Unit-Advertise

LLM FALLBACK (Rule 28):
All model resolution goes through _resolve_llm(agent_name).
Models are NEVER hardcoded here. They come from llm_conf.json via
cf2.core.llm_resolver.resolve_llm(), which walks the tier's fallback
chain and skips any model whose circuit is currently open.
"""
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
import logging
from cf2.core.llm_resolver import resolve_llm
from cf2.core.llm_circuit  import circuit_status

# ── Existing Tool Imports (Unchanged) ──────────────────────────────────────
from cf2.tools.data_csv                   import CSVTool
from cf2.tools.animation_smart_video      import SmartVideoTool
from cf2.tools.animation_bar_race_video   import BarRaceVideoTool
from cf2.tools.animation_audio            import AudioGenerationTool
from cf2.tools.animation_intro_clip       import IntroClipTool
from cf2.tools.animation_bar_merge        import BarMergeTool
from cf2.tools.animation_merge            import MergeAudioVideoTool
from cf2.tools.data_definition            import DefinitionTool
from cf2.tools.definition_video           import DefinitionVideoTool
from cf2.tools.debate_definition          import DebateDefinitionTool
from cf2.tools.debate_video               import DebateVideoTool
from cf2.tools.debate_merge               import DebateMergeTool
from cf2.tools.packaging_yt_narration     import YTNarrationTool
from cf2.tools.packaging_yt_metadata      import YTMetadataTool
from cf2.tools.packaging_yt_thumbnail     import YTThumbnailTool
from cf2.tools.publisher_yt_upload        import YTUploadTool
from cf2.tools.publisher_fb_upload        import FBUploadTool
from cf2.tools.advertise_social_share     import SocialShareTool
from cf2.tools.scout_trend                import SocialTrendScoutTool

logger = logging.getLogger(__name__)  # 🔧 Fixed: was logging.getLogger(name)

@CrewBase
class CF2Crew:
    """Tool registry — agents and tasks only. Flow controls what runs."""
    agents_config = "config/agents.yaml"
    tasks_config  = "config/tasks.yaml"

    def __init__(self, inputs: dict = None):
        self._inputs = inputs or {}
        status = circuit_status()
        if status:
            open_circuits = {m: s for m, s in status.items() if "OPEN" in s}
            if open_circuits:
                logger.warning(f"⚡ Open circuits at startup: {open_circuits}")

    # ── LLM resolver (replaces old _llm / _llm_kwarg) ───────────────────────
    def _resolve_llm(self, agent_name: str) -> dict:
        try:
            cfg = resolve_llm(agent_name, self._inputs)
            return {"llm": cfg["model"]}
        except Exception as exc:
            logger.warning(f"LLM resolve failed for {agent_name}: {exc} → running tools-only")
            return {}   # agent becomes tools-only, flow continues

    # ── Scout Agents ────────────────────────────────────────────────────────
    @agent
    def scout_trend_agent(self) -> Agent:
        return Agent(config=self.agents_config["scout_trend_agent"],
                     tools=[SocialTrendScoutTool()], verbose=True,
                     **self._resolve_llm("scout"))

    # ── Data Agents ─────────────────────────────────────────────────────────
    @agent
    def data_researcher(self) -> Agent:
        return Agent(config=self.agents_config["data_researcher"],
                     verbose=True, **self._resolve_llm("data_researcher"))

    @agent
    def data_csv_generator(self) -> Agent:
        return Agent(config=self.agents_config["data_csv_generator"],
                     tools=[CSVTool()], verbose=True, **self._resolve_llm("csv_generator"))

    @agent
    def data_definition_specialist(self) -> Agent:
        return Agent(config=self.agents_config["data_definition_specialist"],
                     tools=[DefinitionTool()], verbose=True,
                     **self._resolve_llm("definition_specialist"))
    # ── LeadData Agents ─────────────────────────────────────────────────────
    @agent
    def leaddata_specialist(self) -> Agent:
        return Agent(
            config=self.agents_config["leaddata_specialist"],
            tools=[],  # Unit-LeadData is handled by the router function directly
            verbose=True
        )

    @agent
    def leaddata_reddit_agent(self) -> Agent:
        from cf2.tools.leaddata_reddit import RedditTravelScraperTool
        return Agent(
            config=self.agents_config["leaddata_reddit_agent"],
            tools=[RedditTravelScraperTool()],
            verbose=True,
            **self._resolve_llm("scout") # Reuse research tier
        )
    # ── Animation Agents ────────────────────────────────────────────────────
    @agent
    def animation_bar_race_producer(self) -> Agent:
        return Agent(config=self.agents_config["animation_bar_race_producer"],
                     tools=[BarRaceVideoTool()], verbose=True)

    @agent
    def animation_video_producer(self) -> Agent:
        return Agent(config=self.agents_config["animation_video_producer"],
                     tools=[SmartVideoTool()], verbose=True)

    @agent
    def animation_intro_producer(self) -> Agent:
        return Agent(config=self.agents_config["animation_intro_producer"],
                     tools=[IntroClipTool()], verbose=True)

    @agent
    def animation_bar_merge_specialist(self) -> Agent:
        return Agent(config=self.agents_config["animation_bar_merge_specialist"],
                     tools=[BarMergeTool()], verbose=True)

    @agent
    def animation_bar_race_audio_engineer(self) -> Agent:
        from cf2.tools.animation_bar_race_audio import BarRaceAudioTool
        return Agent(config=self.agents_config["animation_bar_race_audio_engineer"],
                     tools=[BarRaceAudioTool()], verbose=True)

    @agent
    def animation_audio_engineer(self) -> Agent:
        return Agent(config=self.agents_config["animation_audio_engineer"],
                     tools=[AudioGenerationTool()], verbose=True,
                     **self._resolve_llm("audio_engineer"))

    @agent
    def animation_merge_specialist(self) -> Agent:
        return Agent(config=self.agents_config["animation_merge_specialist"],
                     tools=[MergeAudioVideoTool()], verbose=True)

    # ── Definition Agents ───────────────────────────────────────────────────
    @agent
    def definition_video_producer(self) -> Agent:
        return Agent(config=self.agents_config["definition_video_producer"],
                     tools=[DefinitionVideoTool()], verbose=True)

    # ── Debate Agents ───────────────────────────────────────────────────────
    @agent
    def debate_debater(self) -> Agent:
        return Agent(config=self.agents_config["debate_debater"],
                     verbose=True, **self._resolve_llm("debater"))

    @agent
    def debate_judge(self) -> Agent:
        return Agent(config=self.agents_config["debate_judge"],
                     verbose=True, **self._resolve_llm("judge"))

    @agent
    def debate_debater_m(self) -> Agent:
        if not self._inputs.get("Unit-Debate"):
            return None  # CrewBase will skip it
        return Agent(config=..., **self._resolve_llm("debater_m"))

    @agent
    def debate_judge_m(self) -> Agent:
        return Agent(config=self.agents_config["debate_judge_m"],
                     verbose=True, **self._resolve_llm("judge_m"))

    @agent
    def debate_definition_specialist(self) -> Agent:
        return Agent(config=self.agents_config["debate_definition_specialist"],
                     tools=[DebateDefinitionTool()], verbose=True,
                     **self._resolve_llm("definition_specialist"))

    @agent
    def debate_video_producer(self) -> Agent:
        return Agent(config=self.agents_config["debate_video_producer"],
                     tools=[DebateVideoTool()], verbose=True,
                     **self._resolve_llm("video_producer"))

    @agent
    def debate_merge_specialist(self) -> Agent:
        return Agent(config=self.agents_config["debate_merge_specialist"],
                     tools=[DebateMergeTool()], verbose=True)

    @agent
    def debate_score_analyst(self) -> Agent:
        inputs = getattr(self, "_inputs", {}) or {}
        val = inputs.get("llm_debate")
        llm_kw = {"llm": val} if (val and str(val).strip().lower() not in ("null", "none", "")) else {}
        return Agent(config=self.agents_config["debate_score_analyst"], verbose=True, **llm_kw)

    # ── Packaging Agents ────────────────────────────────────────────────────
    @agent
    def packaging_yt_narration_specialist(self) -> Agent:
        return Agent(config=self.agents_config["packaging_yt_narration_specialist"],
                     tools=[YTNarrationTool()], verbose=True, **self._resolve_llm("scout"))

    @agent
    def packaging_yt_metadata_specialist(self) -> Agent:
        return Agent(config=self.agents_config["packaging_yt_metadata_specialist"],
                     tools=[YTMetadataTool()], verbose=True, **self._resolve_llm("scout"))

    @agent
    def packaging_yt_thumbnail_specialist(self) -> Agent:
        return Agent(config=self.agents_config["packaging_yt_thumbnail_specialist"],
                     tools=[YTThumbnailTool()], verbose=True, **self._resolve_llm("scout"))

    # ── Unit-Classroom Agents ────────────────────────────────────────
    @agent
    def classroom_script_writer(self) -> Agent:
        return Agent(config=self.agents_config["classroom_script_writer"],
                     verbose=True, **self._resolve_llm("data_researcher"))

    # ── Prodcast Agents ─────────────────────────────────────────────────────
    @agent
    def prodcast_scriptwriter(self) -> Agent:
        return Agent(config=self.agents_config["prodcast_scriptwriter"],
                     verbose=True, **self._resolve_llm("prodcast_scriptwriter"))

    # ── Publisher Agents ────────────────────────────────────────────────────
    @agent
    def publisher_yt_upload_specialist(self) -> Agent:
        return Agent(config=self.agents_config["publisher_yt_upload_specialist"],
                     tools=[YTUploadTool()], verbose=True)

    @agent
    def publisher_fb_upload_specialist(self) -> Agent:
        return Agent(config=self.agents_config["publisher_fb_upload_specialist"],
                     tools=[FBUploadTool()], verbose=True)

    # ── Advertise Agents ────────────────────────────────────────────────────
    @agent
    def advertise_social_share_specialist(self) -> Agent:
        return Agent(config=self.agents_config["advertise_social_share_specialist"],
                     tools=[SocialShareTool()], verbose=True, **self._resolve_llm("scout"))

    # ── Scout Tasks ─────────────────────────────────────────────────────────
    @task
    def scout_trending_topics(self) -> Task:
        return Task(config=self.tasks_config["scout_trending_topics"])

    # ── Data Tasks ──────────────────────────────────────────────────────────
    @task
    def data_research(self) -> Task:
        return Task(config=self.tasks_config["data_research"])

    @task
    def data_generate_csv(self) -> Task:
        return Task(config=self.tasks_config["data_generate_csv"])

    @task
    def data_define_topic(self) -> Task:
        return Task(config=self.tasks_config["data_define_topic"])

    # ── Unit-LeadData Tasks (✅ NEW) ────────────────────────────────────────
    @task
    def leaddata_pipeline(self) -> Task:
        return Task(config=self.tasks_config["leaddata_pipeline"])
    @task
    def unit_leaddata(self) -> Task:
        return Task(
            config=self.tasks_config["unit_leaddata"],
            output_file="leaddata/status.txt",  # Rule 16: Single output contract
            async_execution=False
        )

    # ── Animation Tasks ─────────────────────────────────────────────────────
    @task
    def animation_create_video(self) -> Task:
        return Task(config=self.tasks_config["animation_create_video"])

    @task
    def animation_create_bar_race_video(self) -> Task:
        return Task(config=self.tasks_config["animation_create_bar_race_video"])

    @task
    def animation_create_intro_clip(self) -> Task:
        return Task(config=self.tasks_config["animation_create_intro_clip"])

    @task
    def animation_bar_merge(self) -> Task:
        return Task(config=self.tasks_config["animation_bar_merge"])

    @task
    def animation_add_audio(self) -> Task:
        return Task(config=self.tasks_config["animation_add_audio"])

    @task
    def animation_merge_audio_video(self) -> Task:
        return Task(config=self.tasks_config["animation_merge_audio_video"])

    # ── Definition Tasks ────────────────────────────────────────────────────
    @task
    def definition_create_video(self) -> Task:
        return Task(config=self.tasks_config["definition_create_video"])

    # ── Debate HD Tasks ─────────────────────────────────────────────────────
    @task
    def debate_propose(self) -> Task:
        return Task(config=self.tasks_config["debate_propose"])

    @task
    def debate_oppose(self) -> Task:
        return Task(config=self.tasks_config["debate_oppose"])

    @task
    def debate_decide(self) -> Task:
        return Task(config=self.tasks_config["debate_decide"])

    @task
    def debate_create_definition(self) -> Task:
        return Task(config=self.tasks_config["debate_create_definition"])

    @task
    def debate_create_video(self) -> Task:
        return Task(config=self.tasks_config["debate_create_video"])

    @task
    def debate_merge(self) -> Task:
        return Task(config=self.tasks_config["debate_merge"])

    # ── Debate Shorts (-m) Tasks ────────────────────────────────────────────
    @task
    def debate_propose_m(self) -> Task:
        return Task(config=self.tasks_config["debate_propose_m"])

    @task
    def debate_oppose_m(self) -> Task:
        return Task(config=self.tasks_config["debate_oppose_m"])

    @task
    def debate_decide_m(self) -> Task:
        return Task(config=self.tasks_config["debate_decide_m"])

    @task
    def debate_create_video_m(self) -> Task:
        return Task(config=self.tasks_config["debate_create_video_m"])

    @task
    def debate_generate_scores(self) -> Task:
        return Task(config=self.tasks_config["debate_generate_scores"])

    # ── Unit-Classroom Tasks ────────────────────────────────────────
    @task
    def create_classroom_script(self) -> Task:
        return Task(config=self.tasks_config["create_classroom_script"])

    # ── Prodcast Tasks ─────────────────────────────────────────────────────
    @task
    def prodcast_write_script(self) -> Task:
        return Task(
            config=self.tasks_config["prodcast_write_script"],
            agent=self.prodcast_scriptwriter(),
            output_file="{podcast_dir}/script.md",
        )

    # ── Packaging Tasks ─────────────────────────────────────────────────────
    @task
    def packaging_generate_narration(self) -> Task:
        return Task(config=self.tasks_config["packaging_generate_narration"])

    @task
    def packaging_generate_yt_metadata(self) -> Task:
        return Task(config=self.tasks_config["packaging_generate_yt_metadata"])

    @task
    def packaging_generate_thumbnail(self) -> Task:
        return Task(config=self.tasks_config["packaging_generate_thumbnail"])

    # ── Publisher Tasks ─────────────────────────────────────────────────────
    @task
    def publisher_upload_to_youtube(self) -> Task:
        return Task(config=self.tasks_config["publisher_upload_to_youtube"])

    @task
    def publisher_upload_to_facebook(self) -> Task:
        return Task(config=self.tasks_config["publisher_upload_to_facebook"])

    # ── Advertise Tasks ─────────────────────────────────────────────────────
    @task
    def advertise_share_to_social(self) -> Task:
        return Task(config=self.tasks_config["advertise_share_to_social"])

    # ── Crew ─────────────────────────────────────────────────────────────────
    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )


=================================================================================

# ── Unit-Scout ───────────────────────────────────────────────────────────
scout_trend_agent:
  role: Viral Topic Intelligence Specialist
  goal: >
    Discover trending, high-engagement topics across {platforms}
    within {niches} that have strong debate potential for the @{channel} channel.
  backstory: >
    Expert social media analyst who monitors YouTube trending, Reddit hot posts,
    X/Twitter viral threads, and LinkedIn top content. Scores each topic on
    virality, debate potential, and audience relevance. Outputs a ranked
    trend_queue.json for downstream pipeline consumption.

# ── Unit-Data ─────────────────────────────────────────────────────────────
data_researcher:
  role: >
    Multi-Item Data Research Specialist
  goal: >
    Research and compile comparative time-series data tracking 5-10 different items for {topic}
    from {start} to {end} with {granularity} granularity in multi-column format
  backstory: >
    You are an expert data researcher who specializes in comparative analysis and trend tracking.
    You excel at identifying the key players, frameworks, tools, or metrics in any domain and
    tracking their evolution over time. Your data is always structured in multi-column format
    where the first column is the time period (Year/Month/Date) and subsequent columns (5-10 items)
    track different entities with numeric values (0-100 scale). You provide realistic, well-researched
    data that shows authentic market dynamics, growth patterns, and competitive landscapes.

data_csv_generator:
  role: >
    CSV Data Engineer
  goal: >
    Generate accurate CSV file at output/{filename}/{filename}.csv with proper structure for {topic}
  backstory: >
    You are a meticulous data engineer who specializes in creating clean, well-structured
    CSV files. You understand the importance of proper formatting and deterministic file
    naming conventions. Your CSV files are always ready for downstream processing.

data_definition_specialist:
  role: >
    Topic Definition & Research Specialist
  goal: >
    Research and write a clear, engaging definition of {topic} that explains
    what it is, why it matters, key terms, timeline context, and what viewers
    will see in the bar race video. Save it as output/{filename}/{filename}.txt.
  backstory: >
    You are an expert technical writer and researcher who excels at explaining
    complex topics in simple, engaging language for a general YouTube audience.
    You use your LLM knowledge to write accurate, insightful definitions that
    add real value for viewers. Write in clear, jargon-free English.
    When definition_enabled is false, skip instantly.

# ── Unit-Animation ────────────────────────────────────────────────────────
animation_video_producer:
  role: >
    Video Production Specialist
  goal: >
    Create engaging visualization videos from CSV data for {topic}
  backstory: >
    You are a creative video producer who transforms data into compelling visual stories.
    You work with the video generation tools to create polished, informative videos that
    bring data to life. You ensure every video is both informative and visually appealing.

animation_bar_race_producer:
  role: >
    Bar Race Video Specialist
  goal: >
    Create amazing bar race animation videos from CSV data for {topic}
  backstory: >
    You are an expert in bar chart race animations, specializing in creating professional,
    smooth, and visually stunning videos. You use advanced bar_chart_race configuration with
    interpolation to create mesmerizing visualizations. Your videos feature smart name compacting,
    professional color schemes, and dynamic bar reordering. You create YouTube-ready content
    that captivates viewers with smooth animations and professional presentation.

animation_audio_engineer:
  role: >
    Audio Narration Specialist
  goal: >
    Generate professional audio narration files when {audio_enabled}=true
  backstory: >
    Audio production expert specializing in text-to-speech narration that enhances data
    visualizations with clear, engaging commentary. Skips processing instantly when audio
    is disabled to avoid unnecessary overhead.

animation_merge_specialist:
  role: >
    Audio-Video Merge Specialist
  goal: >
    Merge existing video files (.mp4) with corresponding audio files (.mp3) when {merge_audio_video}=true
  backstory: >
    Expert in multimedia file processing, specializing in combining video and audio streams
    efficiently using ffmpeg. Ensures final outputs have synchronized audio and video.
    Skips processing instantly when merging is disabled.

animation_bar_race_audio_engineer:
  role: >
    Bar Race Audio Narration Specialist
  goal: >
    Generate professional audio narration files for bar race videos when bar_race_audio_enabled=true
  backstory: >
    Audio production expert specializing in text-to-speech narration specifically for bar chart race
    videos. Reads CSV data to generate dynamic, data-driven commentary that matches the visual
    story being told in the bar race animation. Skips instantly when bar_race_audio_enabled is false.

animation_intro_producer:
  role: >
    Intro Clip Video Specialist
  goal: >
    Create branded intro screen video clips for bar race videos when intro_enabled=true
  backstory: >
    Video production expert specializing in creating professional branded intro screens
    for data visualization videos. Generates polished intro clips showing the channel name,
    topic, and year range for each video format (HD, Shorts, 2K, 4K). Supports optional
    watermark overlay. Skips instantly when intro_enabled is false.
    CRITICAL: Call the tool ONCE. When the tool returns ANY output containing
    "SUCCESS", "Skipped", "skipped", "✅", "⏭️", or "🎬", immediately return
    that as your Final Answer. Never call the tool a second time.

animation_bar_merge_specialist:
  role: >
    Bar Race Final Video Specialist
  goal: >
    Concatenate intro clip and bar race video, then merge with audio
    into a single final MP4 per format when bar_merge_enabled=true
  backstory: >
    Multimedia pipeline expert specializing in combining video segments and
    audio tracks into polished final outputs using ffmpeg. Handles intro
    concatenation and audio merging in one efficient pass per format.
    Skips instantly when bar_merge_enabled is false.
    CRITICAL: Call the tool ONCE. When the tool returns any message containing
    "completed", "skipped", "SUCCESS", or "✅", immediately return that as your
    Final Answer. Never call the tool a second time. Never fabricate output —
    always call the tool first before giving any answer.

# ── Unit-Definition ───────────────────────────────────────────────────────
definition_video_producer:
  role: >
    Definition Video Producer
  goal: >
    Create a scrolling text video clip from the topic definition text when definition_video=true
  backstory: >
    Video production expert specializing in creating clean, readable scrolling text
    videos from plain text content. Generates definition_video clips ready to merge
    into the final pipeline. Skips instantly when definition_video is false.

# ── Unit-Debate ───────────────────────────────────────────────────────────
debate_debater:
  role: >
    Expert Debate Specialist
  goal: >
    Write compelling, evidence-based debate arguments for or against the given motion.
    Produce clear, structured, persuasive content for YouTube audience engagement.
  backstory: >
    World-class debater and content strategist with expertise in constructing logical,
    persuasive arguments on complex topics. Specializes in making technical and
    controversial subjects accessible to general audiences. Creates content for
    the @{channel} YouTube channel that sparks meaningful discussion.

debate_judge:
  role: >
    Impartial Debate Judge
  goal: >
    Review both sides of a debate and deliver a fair, balanced verdict that acknowledges
    the strongest arguments from each side.
  backstory: >
    Experienced judge and analyst with a reputation for balanced, well-reasoned decisions.
    Evaluates debate arguments on their merits — evidence quality, logical consistency,
    and persuasive impact. Produces verdicts that educate and inform the @{channel} audience.

debate_debater_m:
  role: >
    Mini Debate Specialist (Short-Form)
  goal: >
    Write short-form debate arguments (120–180 words) for the @{channel} channel
    using EXACT header formatting: PROPOSITION/OPPOSITION, OPENING STATEMENT,
    Argument N: / Counter-Argument N:, CONCLUSION.
  backstory: >
    You are a concise debate writer producing short-form content for YouTube Shorts.
    You ALWAYS use these EXACT headers — no abbreviations, no shortcuts, ever:

    For PRO (propose):
      PROPOSITION: [topic]
      OPENING STATEMENT
      Argument 1: [Title]
      Argument 2: [Title]
      Argument 3: [Title]
      CONCLUSION

    For CON (oppose):
      OPPOSITION: [topic]
      OPENING STATEMENT
      Counter-Argument 1: [Title]
      Counter-Argument 2: [Title]
      Counter-Argument 3: [Title]
      CONCLUSION



    Every section header must appear on its own line exactly as shown above.
    Total response: 120–180 words. No tool calls, no JSON, no code.

debate_judge_m:
  role: >
    Mini Debate Judge (Short-Form)
  goal: >
    Deliver a short-form balanced verdict (120–180 words) for the @{channel} channel
    using EXACT header formatting: VERDICT, SUMMARY OF PROPOSITION,
    SUMMARY OF OPPOSITION, ANALYSIS, DECISION.
  backstory: >
    You are a concise debate judge producing short-form verdicts for YouTube Shorts.
    You ALWAYS use these EXACT headers — no abbreviations, no shortcuts, ever:

      VERDICT: [topic]
      SUMMARY OF PROPOSITION
      SUMMARY OF OPPOSITION
      ANALYSIS
      DECISION

    Every section header must appear on its own line exactly as shown above.
    Total response: 120–180 words. No tool calls, no JSON, no code.

debate_definition_specialist:
  role: >
    Debate Definition & Compression Specialist
  goal: >
    Call the DebateDefinition tool to compress and save debate .md files for {topic}.
    Your ONLY tool is DebateDefinition. Never call DataDefinition or write .txt files.
  backstory: >
    Expert in debate content compression and formatting. Reads propose.md, oppose.md,
    decide.md and generates compressed versions with label mappings applied for
    YouTube Shorts (-m.md) and full HD versions. Saves all output to the debate/ folder.
    CRITICAL: You have ONE tool available: DebateDefinition.
        You MUST call DebateDefinition ONCE and return the output immediately.
        NEVER call DataDefinition or any other tool — they do not exist for this task.

debate_video_producer:
  role: >
    Debate Video Producer
  goal: >
    Create a bottom-to-top streaming debate video from propose.md, oppose.md, and decide.md
    when debate_video_enabled=true. Skips instantly when disabled.
  backstory: >
    Video production specialist for debate-style content. Combines PRO arguments, CON arguments,
    and moderator conclusions into a cinematic neon-glow streaming text video with synchronized
    TTS audio. Produces debate_video_[format]_with_audio.mp4 ready for the publishing pipeline.
    Skips instantly when debate_video_enabled is false.

debate_merge_specialist:
  role: >
    DebateMergeSpecialist
  goal: >
    Concatenate intro clip and debate video, then merge with audio
    into a single final MP4 per format when debate_merge_enabled=true
  backstory: >
    Multimedia pipeline expert specializing in combining video segments and
    audio tracks into polished final outputs using ffmpeg. Handles intro
    concatenation and audio merging in one efficient pass per format.
    Skips instantly when debate_merge_enabled is false.
    CRITICAL: Call the tool ONCE. When the tool returns any message containing
    "completed", "skipped", "SUCCESS", or "✅", immediately return that as your
    Final Answer. Never call the tool a second time. Never fabricate output —
    always call the tool first before giving any answer.

debate_score_analyst:
  role: >
    Debate Scoreboard Analyst
  goal: >
    Read the full propose/oppose/decide markdown for the debate on "{topic}"
    and assign fair, well-reasoned integer scores (8-20) to each side for
    the opening statement and each numbered argument/counter-argument pair.
    Output a strict JSON structure that the scoreboard overlay consumes.
  backstory: >
    You are a neutral adjudicator used to scoring academic debates. You read
    both sides in full and score each round on clarity, evidence density,
    rhetorical strength, and rebuttal effectiveness. You never invent
    arguments that are not present. You always produce valid JSON.


# ── Unit-Packaging ────────────────────────────────────────────────────────
packaging_yt_narration_specialist:
  role: >
    YouTube CC Narration Specialist
  goal: >
    Generate CC narration text (cc_en.txt) from CSV or debate .md files,
    then translate it to multiple languages for {topic}.
  backstory: >
    Audio narration expert who reads CSV data or debate markdown files to produce
    engaging, data-driven commentary for YouTube closed captions. Saves narration
    to cc_en.txt and translates it into the configured CC languages using Google
    Translate. Always calls the tool once and returns the output immediately.
    CRITICAL: Call the tool ONCE. Return the tool output immediately as your Final Answer.

packaging_yt_metadata_specialist:
  role: >
    YouTube SEO & Metadata Specialist
  goal: >
    Generate professional YouTube metadata (title, description, tags, chapters)
    and translate it to {yt_metadata_lang} languages for {topic}.
  backstory: >
    YouTube SEO expert with deep knowledge of algorithm ranking factors and audience
    engagement. Builds compelling titles, descriptions, and tag sets that maximize
    discoverability. Handles debate, animation, and yt_id pipeline modes. Saves
    structured metadata to YT/[style]/[fmt]/MD/ per format.
    Follow @{channel} on YouTube and Facebook for more insights!
    CRITICAL: Call the tool ONCE. Return the tool output immediately as your Final Answer.

packaging_yt_thumbnail_specialist:
  role: >
    YouTube Thumbnail Specialist
  goal: >
    Generate PNG and JPG thumbnail images (1920x1080 HD / 1080x1920 Shorts)
    for {topic} saved to YT/[style]/[fmt]/Th/.
  backstory: >
    Visual design expert specializing in YouTube thumbnail generation using Pillow.
    Creates debate thumbnails with PRO/CON/VERDICT panels and bar-race thumbnails
    showing the latest CSV rankings. Handles all pipeline modes (debate, animation,
    yt_id) and all video formats automatically.
    CRITICAL: Call the tool ONCE. Return the tool output immediately as your Final Answer.

# ── Unit-Publisher ────────────────────────────────────────────────────────
publisher_yt_upload_specialist:
  role: >
    YouTube Upload Specialist
  goal: >
    Upload final video files and CC subtitle files to YouTube when upload_youtube_video=true.
    Skips instantly when disabled.
  backstory: >
    Expert in YouTube Data API v3 uploads with deep knowledge of video metadata,
    closed captions, privacy settings, and category configuration. Handles OAuth2
    authentication, multi-format uploads, and CC file submissions for the @{channel} channel.
    Skips instantly when upload_youtube_video is false.

publisher_fb_upload_specialist:
  role: >
    Facebook Video Upload Specialist
  goal: >
    Upload final video files to a Facebook Page when upload_facebook_video=true.
    Shorts → Facebook Reels. HD → Facebook Video.
    Skips instantly when disabled.
  backstory: >
    Expert in Facebook Graph API video uploads with deep knowledge of Reels vs Video
    publishing, Page Access Tokens, and privacy settings. Handles chunked resumable
    uploads, smart skip via fb_upload_log.json, and saves upload summaries for the
    @{channel} Facebook Page. Skips instantly when upload_facebook_video is false.

# ── Unit-Advertise ────────────────────────────────────────────────────────
advertise_social_share_specialist:
  role: >
    Social Media Distribution Specialist
  goal: >
    Post uploaded YouTube video URLs with thumbnail images to configured social platforms
    when social_share_enabled=true. Skips instantly when disabled.
  backstory: >
    Social media strategist expert in cross-platform content distribution across LinkedIn,
    Instagram, Facebook, and X. Handles image attachments, platform-specific formatting,
    and post scheduling for the @{channel} brand. Reads upload logs to find video URLs
    and posts with Full HD thumbnails. Skips instantly when social_share_enabled is false.
# ── Unit-Prodcast Agents ────────────────────────────────────────────────
prodcast_scriptwriter:
  role: Podcast Script Writer
  goal: >
    Write engaging {prodcast_host_name}/{prodcast_guest_name} podcast dialogue on {topic} for the
    {channel} podcast — between {min_exchanges} and {max_exchanges}
    exchanges, ready for two-voice TTS.
  backstory: >
    You are a veteran podcast scriptwriter who turns complex topics into
    natural, two-voice conversations. The Host ({prodcast_host_name}) opens warmly, asks
    pointed questions, and closes with a thank-you; the Guest ({prodcast_guest_name}) is the
    expert who explains ideas clearly with concrete examples and takes
    positions when the topic invites them. You write dialogue the way
    real people talk — full sentences, no stage directions, no markdown
    bullets or emphasis, no headings inside the body, no bracketed cues.
    Every line begins with either "Host:" or "Guest:" and contains one
    paragraph of speech. You produce a clean, ready-to-narrate script
    that feels like an honest conversation rather than a lecture.
    Short intro theme: {prodcast_short_intro}


# ── Unit-Classroom ────────────────────────────────────────────────────────
classroom_script_writer:
  role: >
    Kids Classroom Script Writer
  goal: >
    Write a 7-phase structured classroom dialogue for topic {topic}
    using 2 Teachers and 8 Students (ages 6-10). Max 12 words per line.
    Grade 3-5 vocabulary. Each student speaks at least once.
    Output strict format: [PHASE:name] then [TAG] Speaker: text lines.
  backstory: >
    You are a specialist in creating educational content for young learners.
    You write engaging age-appropriate classroom dialogues following a
    fixed 7-phase structure: hook, explain, interaction, example,
    reinforcement, fun_fact, recap_quiz. Never exceed 12 words per line.
    Ensure all 8 student personalities appear at least once.
    Format every line as: [TAG] Speaker: dialogue text
    Example: [T1] Teacher1: Why do clouds float?
             [S1-F] Curious: Is it because of wind?
    Always output [PHASE:name] before each phase block.

# ── Unit-LeadData agents ─────────────────────────────────────────────────
leaddata_specialist:
  role: >
    Lead Data Pipeline Specialist
  goal: >
    Orchestrate and execute the Unit-LeadData workflow with strict CF2
    compliance, secure credential handling, and zero-data-loss routing.
  backstory: >
    You are a specialized CF2 routing agent responsible for managing the
    lead generation pipeline. You ensure all subtasks (collect, normalize,
    score, export) complete sequentially. You handle API rate limits and
    config errors gracefully to ensure maximum lead capture for TravelOnly.

leaddata_reddit_agent:
  role: >
    Reddit Travel Intent Specialist
  goal: >
    Extract travelers actively planning trips from Reddit communities
    by analyzing post content, user history, and engagement signals.
  backstory: >
    Expert in identifying high-intent travel discussions on Reddit.
    You scan subreddits for keywords like "all inclusive", "travel agent",
    and specific destinations to find users asking for advice or sharing
    recent trip details. You filter out bots and low-quality accounts
    to ensure only genuine B2C leads are enriched.

=================================================================================

scout_trending_topics:
  description: >
    Discover and rank viral trending topics across {platforms} for the @{channel} channel.

    ⚠️  CRITICAL: You MUST call the Social Trend Scout Tool NOW with these EXACT parameters:
      platforms: {platforms}
      niches: {niches}
      min_virality_score: {min_virality_score}
      output_queue_size: {output_queue_size}
      auto_consume: {auto_consume}
      use_web_search: {use_web_search}
      queue_path: "{scout_queue_path}"
      force_refresh: {force_refresh}
      force_scraping: {force_scraping}
      scraping_url_file: {scraping_url_file}


    The tool updates {scout_queue_path} (queue list) and returns the top topic.

    Once the tool returns ANY output, use it IMMEDIATELY as your Final Answer.
    Do NOT add commentary. Do NOT call the tool again.
    Do NOT return SKIP.

  expected_output: >
    Tool output starting with "✅ Social Trend Scout Complete" OR "⏭️  Smart Skip".
    Return the exact tool output as your Final Answer.

  agent: scout_trend_agent

data_research:
  description: >
    Research and compile time-series data for {topic} from {start} to {end}.
    The data should be organized with {granularity} granularity.
    CRITICAL FORMAT REQUIREMENTS:
    Create data in MULTI-COLUMN format tracking multiple items/frameworks/tools over time.
    Example structure for "AI Agent Framework Popularity":
    Year,LangChain,CrewAI,AutoGPT,BabyAGI,SemanticKernel,n8n,Make,Zapier,Haystack,MetaGPT
    2015,0,0,0,0,0,5,8,20,0,0
    2016,0,0,0,0,0,8,12,25,0,0
    2017,2,0,0,0,0,12,18,30,0,0
    ...

    Structure requirements:
    - First column: Time period (Year, Month, Date based on {granularity})
    - Subsequent columns: Different items/frameworks/tools being tracked
    - Values: Popularity scores, adoption rates, or relevant metrics (0-100 scale)
    - Include 5-10 different items to compare

    The data must be formatted as a list of dictionaries where each dictionary represents one row.
    Example: [{"Year": 2015, "LangChain": 0, "CrewAI": 0, ...}, {"Year": 2016, ...}]
  expected_output: >
    A Python list of dictionaries in multi-column format, ready for CSV export.
    Each dictionary must have the time period as first key, followed by 5-10 items being tracked.
    Values should be numeric (0-100 scale for popularity/adoption).
  agent: data_researcher

data_generate_csv:
  description: >
    Generate a CSV file from the researched data with strict filename and format rules:
    FILENAME RULES:
    - Filename must be: First 3 words of "{topic}" with no spaces
    - Example: "AI Agent Framework Popularity" → "AIAgentFramework.csv"
    - Location: {output_dir}/{filename}.csv
    FORMAT RULES:
    - Multi-column format with time period in first column
    - 5-10 items/frameworks/tools in subsequent columns
    - Example format:
      Year,LangChain,CrewAI,AutoGPT,BabyAGI,SemanticKernel,n8n,Make,Zapier,Haystack,MetaGPT
      2015,0,0,0,0,0,5,8,20,0,0
      2016,0,0,0,0,0,8,12,25,0,0
      ...

    Use the CSV Writer Tool to create the file with proper structure:
    - First column: Year/Month/Date (based on granularity)
    - Remaining columns: Different items being tracked
    - All values numeric (0-100 scale)
    - Include headers for all columns
    - Ensure data is properly formatted
    - Save to the output directory

    The CSV must be ready for video generation processing with multi-line chart visualization.
  expected_output: >
    Confirmation message with the exact filepath where CSV was saved,
    including number of rows and columns written, and sample of first/last rows.
  agent: data_csv_generator
  context:
    - data_research

data_define_topic:
  description: >
    Write a rich definition of "{topic}" for the @{channel} YouTube channel.
    If definition_enabled is false, respond with just: SKIP
    Write ONLY the definition text — no tool calls, no JSON, no code.
    Your entire response becomes the definition file content.

    Format your response exactly like this:

    WHAT IS {topic}?
    [3-4 sentences in plain English for a general YouTube audience]

    WHY DOES IT MATTER?
    [2-3 sentences on importance and who it impacts]

    KEY TERMS
    - Term 1: one-line definition
    - Term 2: one-line definition
    - Term 3: one-line definition
    - Term 4: one-line definition

    TIMELINE {start} TO {end}
    [3-4 sentences on key milestones and evolution]

    WHAT YOU WILL SEE IN THIS RACE
    [2 sentences on players, trends, and what to watch for]

    Keep the total definition under {definition_max_chars} characters.
  expected_output: >
    The full definition text as plain prose — no tool calls, no JSON.
    Starting with "WHAT IS {topic}?" and ending with "WHAT YOU WILL SEE IN THIS RACE".
    Must be under {definition_max_chars} characters total.
  agent: data_definition_specialist
  output_file: "{definition_dir}/def.md"   #

definition_create_video:
  description: >
    Create a scrolling text video clip from the topic definition text for {topic}.
    This task will automatically skip if definition_video is false in inputs.
    CRITICAL — call the Definition Video Tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      definition_video: {definition_video}
      what_is_only: true
      secs_per_line: 3.5
      channel: "{channel}"
      watermark_enabled: {watermark_enabled}
      watermark_text: "{watermark_text}"
      watermark_opacity: {watermark_opacity}
      tts_engine: "{tts_engine}"

    NOTE: filename must be "{filename}" (e.g. "LLMAlignmentRLHF") — NOT "definition_video_LLMAlignmentRLHF".
    The tool reads {output_dir}/{filename}.txt automatically.
    Output: definition_video_[format].mp4 saved to {output_dir}.
  expected_output: >
    List of definition video files created, OR skip message if disabled.
    Example: "definition_video_Shorts.mp4 (2.3 MB)"
  agent: definition_video_producer

animation_create_video:
  description: >
    Generate visualization videos from the CSV file for {topic}.
    Animation styles: {animation_styles}
    Video formats: {video_formats}
    FPS: {fps}
    Use the Video Generation Tool to:
    - Read CSV from {output_dir}/{filename}.csv
    - Create videos for ALL styles in {animation_styles}
    - Save to {output_dir}/ with naming pattern: {filename}[style][format].mp4
    - All video files go to topic subdirectory, CSV stays flat
    Title format requirement (STRICT):
    - Line 1: Pure topic name only ("Programming Language")
    - Line 2: Visualization type + year ("Race - 2019")

    For bar race videos, apply label trimming using data/label_mappings.json
    (e.g., "JavaScript" → "JS", "Microsoft" → "MS")
  expected_output: >
    Confirmation of successful video creation with exact file paths for all generated videos.
    Example: "{output_dir}/ProgrammingLanguage_bar_Shorts.mp4"
  agent: animation_video_producer
  context:
    - data_research
    - data_generate_csv

animation_create_bar_race_video:
  description: >
    Generate AMAZING bar race animation videos from the CSV file for {topic}.
    Animation: Professional bar chart race with smooth interpolation
    Video formats: {video_formats}
    FPS (seconds per period): {fps}
    Use the Bar Race Video Generator Tool to:
    - Read CSV from {output_dir}/{filename}.csv
    - Create professional bar race videos
    - Save to {output_dir}/
    - Smooth interpolation, dynamic bar reordering, professional color scheme
    - Output files: bar_race_[format].mp4 in {output_dir}/

    CRITICAL — call the Bar Race Video Tool with EXACTLY these values:
      csv_filepath: "{output_dir}/{filename}.csv"
      output_dir: "{output_dir}"
      title: "{topic} Race"
      video_formats: {video_formats}
      seconds_per_period: {fps}
      fps_hd_offset: {fps_hd_offset}
      use_label_mappings: {use_label_mappings}
      watermark_enabled: {watermark_enabled}
      watermark_text: "{watermark_text}"
      watermark_opacity: {watermark_opacity}

    DO NOT change these values. Pass them exactly as shown.
  expected_output: >
    Confirmation of successful bar race video creation with exact file paths.
    Example: "{output_dir}/bar_race_Shorts.mp4, {output_dir}/bar_race_HD.mp4"
  agent: animation_bar_race_producer
  context:
    - data_research
    - data_generate_csv

animation_create_intro_clip:
  description: >
    Generate branded intro screen video clip(s) for bar race videos.
    This task will automatically skip if intro_enabled is false in inputs.
    When enabled, creates intro MP4 clips for each format in {video_formats}.
    CRITICAL — call the Intro Clip Tool with EXACTLY these values:
      topic: "{topic}"
      start_year: {start}
      end_year: {end}
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      intro_enabled: {intro_enabled}
      intro_duration: {intro_duration}
      intro_context: "{intro_context}"
      intro_slug: "biggest debates"
      channel: "{channel}"
      watermark_enabled: {watermark_enabled}
      watermark_text: "{watermark_text}"

    Output files: {output_dir}/intro_[format].mp4
    Example: {output_dir}/intro_Shorts.mp4, {output_dir}/intro_HD.mp4
  expected_output: >
    List of intro clip files created, OR skip message if disabled.
    Example: "🎬 Intro clips created:\n   • intro_Shorts.mp4 (1024 KB)\n   • intro_HD.mp4 (2048 KB)"
  agent: animation_intro_producer

animation_add_bar_race_audio:
  description: >
    Generate professional audio narration files for bar race videos.
    This task will automatically skip if bar_race_audio_enabled is false in inputs.
    When enabled, creates audio files for all bar_race_*.mp4 videos based on {topic}.
    CRITICAL — call the Bar Race Audio Tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      bar_race_audio_enabled: {bar_race_audio_enabled}
      audio_speed: {audio_speed}
      audio_speed_hd: {audio_speed_hd}
      channel: "{channel}"

    The tool reads the CSV from {output_dir}/{filename}.csv automatically.
    DO NOT substitute topic for filename. filename must be the slug: "{filename}" (e.g. "LLMPopularity").
    - Audio files saved to: {output_dir}/bar_race_[format]_audio.mp3
    - Narration text: {output_dir}/bar_race_cc_en.txt
  expected_output: >
    List of bar race audio files created, OR skip message if disabled.
    Example: "🎵 Bar race audio files created:\n   • bar_race_Shorts_audio.mp3\n   • bar_race_HD_audio.mp3"
    Narration file: "bar_race_cc_en.txt"
  agent: animation_bar_race_audio_engineer
  context:
    - animation_create_bar_race_video

animation_add_audio:
  description: >
    Generate professional audio narration files.
    This task will automatically skip if audio is disabled in inputs.
    When enabled, creates audio files for all generated videos based on {topic}.
    - Audio files saved to: {output_dir}/[style]_[format]_audio.mp3
    - Narration text file: {output_dir}/{filename}_cc_en.txt
  expected_output: >
    List of audio files created, OR skip message if disabled.
    Example: "🎵 Audio narration files created:\n   • ProgrammingLanguage_bar_Shorts_audio.mp3"
    Narration file: "ProgrammingLanguage_cc_en.txt"
  agent: animation_audio_engineer
  context:
    - animation_create_video
    - data_generate_csv

animation_merge_audio_video:
  description: >
    Merge existing MP4 video files with corresponding MP3 audio files.
    This task will automatically skip if merge_audio_video is disabled in inputs.
    When enabled, searches in {output_dir}/ for pairs like:
    - {filename}[style][format].mp4
    - {filename}[style][format]audio.mp3
    And creates: {filename}[style]_[format]_with_audio.mp4
    All files remain in topic subdirectory.
  expected_output: >
    Confirmation of successful merges, OR skip message if disabled.
    Example: "📹 Audio-video merging completed (1 successful).\n✅ Merged: ProgrammingLanguage_bar_Shorts_with_audio.mp4"
  agent: animation_merge_specialist
  context:
    - animation_add_audio

animation_bar_merge:
  description: >
    Concatenate intro + bar race + definition video segments WITH AUDIO into a single final MP4 per format.
    This task will automatically skip if bar_merge_enabled is false in inputs.
    Pipeline per format (where [format] is each entry in {video_formats}):

      intro_[format]_with_audio.mp4
        +
      bar_race_[format]_with_audio.mp4
        +
      definition_video_[format]_with_audio.mp4
          → ffmpeg concat (with -avoid_negative_ts make_zero for perfect sync)
          → Merged_[format].mp4

    Also merges CC text files:
      intro_[format]_cc_en.txt
        +
      bar_race_[format]_cc_en.txt
        +
      definition_video_[format]_cc_en.txt
          → Merged_[format]_cc_en.txt

    CRITICAL — call the Bar Merge Tool with EXACTLY these values:
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      bar_merge_enabled: {bar_merge_enabled}
      channel: "{channel}"
      topic: "{topic}"

    Output files per format:
      • Merged_[format].mp4          (final video with perfect audio sync)
      • Merged_[format]_cc_en.txt    (merged closed captions text)

    Example for Shorts format:
      {output_dir}/Merged_Shorts.mp4
      {output_dir}/Merged_Shorts_cc_en.txt

    Example for HD format:
      {output_dir}/Merged_HD.mp4
      {output_dir}/Merged_HD_cc_en.txt
  expected_output: >
    A message starting with "✅ SUCCESS" listing the final files created.
    Once you receive output from the tool containing "completed" or "skipped", return it as your Final Answer immediately.
    Do NOT call the tool again.
  agent: animation_bar_merge_specialist

packaging_generate_narration:
  description: >
    Generate CC narration text file and translate it to {yt_cc_lang} languages for {topic}.
    Saves: {output_dir}/cc_en.txt and {output_dir}/YT/{video_style}/[fmt]/CC/*.txt
    Call the YouTube Narration Generator tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      start_year: {start}
      end_year: {end}
      channel: "{channel}"
      video_formats: {video_formats}
      video_style: {video_style}
      yt_cc_lang: {yt_cc_lang}
      animation_video_formats: []
    CRITICAL: Call the tool ONCE only. The moment the tool returns ANY output,
    use it immediately as your Final Answer. Do NOT retry, do NOT call the
    tool a second time regardless of what the output says.
  expected_output: >
    Confirmation that narration text was saved and CC translations completed.
    Return the exact tool output as your final answer.
  agent: packaging_yt_narration_specialist

packaging_generate_yt_metadata:
  description: >
    Generate YouTube title, description, tags, chapters and translate metadata
    to {yt_metadata_lang} languages for {topic}.
    Saves: {output_dir}/YT/{video_style}/[fmt]/MD/en.json + translations.
    Call the YouTube Metadata Generator tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      start_year: {start}
      end_year: {end}
      channel: "{channel}"
      channel_lower: "{channel_lower}"
      website: "{website}"
      video_formats: {video_formats}
      video_style: {video_style}
      fps: {fps}
      fps_hd_offset: {fps_hd_offset}
      n_periods: 0
      csv_path: "{output_dir}/{filename}.csv"
      yt_metadata_lang: {yt_metadata_lang}
      animation_video_formats: []
    CRITICAL: Call the tool ONCE only. The moment the tool returns ANY output,
    use it immediately as your Final Answer. Do NOT retry, do NOT call the
    tool a second time regardless of what the output says.
  expected_output: >
    Confirmation that YouTube metadata files were saved per format.
    Return the exact tool output as your final answer.
  agent: packaging_yt_metadata_specialist

packaging_generate_thumbnail:
  description: >
    Generate PNG and JPG thumbnail images (1920x1080 HD / 1080x1920 Shorts) for {topic}.
    Saves: {output_dir}/YT/{video_style}/[fmt]/Th/{filename}.png and .jpg
    Call the YouTube Thumbnail Generator tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      start_year: {start}
      end_year: {end}
      channel: "{channel}"
      video_formats: {video_formats}
      video_style: {video_style}
      csv_path: "{output_dir}/{filename}.csv"
      animation_video_formats: []
    CRITICAL: Call the tool ONCE only. The moment the tool returns ANY output,
    use it immediately as your Final Answer. Do NOT retry, do NOT call the
    tool a second time regardless of what the output says.
  expected_output: >
    Confirmation that PNG and JPG thumbnails were saved per format.
    Return the exact tool output as your final answer.
  agent: packaging_yt_thumbnail_specialist

# ─────────────────────────────────────────────────────────────
# Unit: Publisher
# ─────────────────────────────────────────────────────────────
publisher_upload_to_youtube:
  description: >
    Upload final merged videos and/or CC subtitle files to YouTube for {topic}.

    ⚠️ IMPORTANT — DO NOT decide to skip based on upload_youtube_video alone.
    You MUST always call the YouTube Upload Tool. The tool itself handles all skip logic:
      - If upload_youtube_video=false AND upload_cc=false → tool returns skip message
      - If upload_youtube_video=false AND upload_cc=true  → CC/MD-only mode: updates CC
        and metadata localizations on the existing YouTube video (topic IS the video ID)
      - If upload_youtube_video=true                      → full video + CC upload

    CRITICAL — call the YouTube Upload Tool with EXACTLY these values:
      topic: "{topic}"
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      upload_youtube_video: {upload_youtube_video}
      channel: "{channel}"
      privacy_status: "{upload_privacy}"
      category_id: "{upload_category_id}"
      upload_cc: {upload_cc}
      upload_cc_lang: "{upload_cc_lang}"
      upload_md_lang: "{upload_md_lang}"
      notify_subscribers: {upload_notify_subscribers}
      client_secrets_file: "{upload_client_secrets_file}"
      token_file: "{upload_token_file}"

    The tool will (per format in video_formats):
      1. If upload_youtube_video=true: locate and upload {channel}_{topic_slug}_[fmt].mp4
      2. If upload_youtube_video=false and upload_cc=true: use topic as YouTube video ID directly
      3. Upload CC files from {output_dir}/YT/debate/[fmt]/CC/ (or YT/[fmt]/CC/ fallback)
      4. Upload MD localizations from {output_dir}/YT/debate/[fmt]/MD/ (up to upload_md_lang limit)
      5. Save upload log to {output_dir}/YT/debate/[fmt]/upload_log.json

    ⚠️ CRITICAL WORKFLOW — FOLLOW EXACTLY:

    STEP 1: Call the YouTube Upload Tool NOW with the parameters above.

    STEP 2: WAIT for the tool to complete (may take 30-120 seconds).
      - The tool will upload video, CC files, and metadata
      - The tool will return a summary starting with "✅ YouTube Upload"

    STEP 3: Return the tool's EXACT output as your Final Answer.
      - DO NOT modify the output
      - DO NOT add commentary
      - DO NOT call the tool again
      - DO NOT return the tool CALL — return the tool RESULT

    ⚠️ FORBIDDEN:
      - Returning {"name": "publisher_yt_upload", "arguments": {...}}
      - Skipping the tool call
      - Calling the tool multiple times

    Smart skip: If an upload_log.json already contains a video_id for a format, that format is skipped.
    Once you receive the tool output, return it immediately as your Final Answer.

  expected_output: >
    The EXACT output from the YouTube Upload Tool, e.g.:

    ✅ YouTube Upload (1 format(s)):
       • ✅ Shorts: https://youtu.be/bFVFCTSBLSQ (CC: 3 uploaded, 0 skipped | MD: 3 uploaded)

    OR if CC/MD-only mode:
    ✅ Shorts: https://youtu.be/xxxxx (CC: 2 uploaded, 1 skipped | MD: 3 uploaded)

    OR if skipped:
    🔇 YouTube upload skipped (upload_youtube_video=false, upload_cc=false).

  agent: publisher_yt_upload_specialist
  context:
    - packaging_generate_thumbnail

# ─────────────────────────────────────────────────────────────
# Unit: Advertise
# ─────────────────────────────────────────────────────────────

advertise_share_to_social:
  description: >
    Post the uploaded YouTube video URL with thumbnail image to configured social media platforms for {topic}.
    Uses Full HD thumbnails (1920x1080px) in both PNG and JPG formats.
    Skips automatically if social_share_enabled is false.
    Smart skip: if {output_dir}/YT/debate/[fmt]/share_log.json already exists with successful posts for that format, skips re-posting.

    CRITICAL — call the Social Share Tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      social_share_enabled: {social_share_enabled}
      social_platforms: {social_platforms}
      video_formats: {video_formats}
      channel: "{channel}"
      website: "{website}"
      image_path: "{output_dir}/{filename}.png"
      start_year: {start}
      end_year: {end}
      video_url: ""
      dry_run: {social_share_dry_run}
      schedule_post: {schedule_post}
      schedule_datetime: "{schedule_datetime}"
      schedule_timezone: "{schedule_timezone}"

    The tool will:
      1. Read {output_dir}/YT/debate/[fmt]/upload_log.json to find the uploaded video URL
      2. Attach thumbnail image (PNG or JPG) from {output_dir}/{filename}.[png|jpg]
         - PNG: {output_dir}/{filename}.png (lossless, preferred)
         - JPG: {output_dir}/{filename}.jpg (compressed, fallback)
         Both are 1920x1080px (Full HD)
      3. Post to each platform listed in social_platforms with image
      4. Save results to {output_dir}/YT/debate/[fmt]/share_log.json and share_log.txt

    Thumbnails: Full HD (1920x1080px) generated by generate_thumbnail task
      - PNG: {output_dir}/{filename}.png
      - JPG: {output_dir}/{filename}.jpg

    Credentials are read from data/social_credentials.json.
    If missing, the tool auto-creates a template file — fill it in and re-run.
    Once you receive the tool output, return it immediately as your Final Answer.

  expected_output: >
    Share confirmation per platform with image attachment:
      ✅ LinkedIn: Posted — post_id: urn:li:share:...
      ✅ Facebook: Posted — post_id: 123456
      ✅ X: Tweeted — tweet_id: 1234567890
    OR skip message if social_share_enabled=false.
  agent: advertise_social_share_specialist
  dry_run: {social_share_dry_run}

debate_create_video:
  description: >
    Create a bottom-to-top streaming debate video for {topic} using PRO/CON/Moderator markdown files.
    This task will automatically skip if debate_video_enabled is false in inputs.
    Input files used per format (resolved automatically by the tool):
      Shorts / ShortsHD / Shorts4K → propose-m.md, oppose-m.md, decide-m.md
      HD / 4K / landscape formats  → propose.md,   oppose.md,   decide.md
    Fallback: if the format-specific file is missing, the tool falls back to the plain .md file.

    CRITICAL — call the Debate Video Tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      debate_video_enabled: {debate_video_enabled}
      secs_per_line: {debate_secs_per_line}
      channel: "{channel}"
      watermark_enabled: {watermark_enabled}
      watermark_text: "{watermark_text}"
      video_fps: {video_fps}
      tts_engine: "{tts_engine}"
      tts_voices: {tts_voices}
      bg_opacity: {debate_bg_opacity}
      debate_background_enabled: {debate_background_enabled}
      debate_background_prompt: "{debate_background_prompt}"
      image_gen_backend: "{image_gen_backend}"

    Output files per format in {output_dir}/:
      debate_video_[format].mp4              (silent video)
      debate_video_[format]_audio.mp3        (TTS audio)
      debate_video_[format]_with_audio.mp4   (final merged)
      debate_video_[format]_cc_en.txt        (narration text)

  expected_output: >
    List of debate video files created per format, OR skip message if disabled.
    Example: "✅ Shorts: debate_video_Shorts_with_audio.mp4 (4500 KB)  Duration: 120.0s"
  agent: debate_video_producer


debate_create_video_m:
  description: >
    Create a Shorts-only debate video for {topic} using the 180s mobile scripts
    (propose-m.md, oppose-m.md, decide-m.md). The tool selects -m files automatically
    for Shorts format. Skips if debate_video_enabled is false.

    CRITICAL — call the Debate Video Tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      video_formats: ["Shorts"]
      debate_video_enabled: {debate_video_enabled}
      secs_per_line: {debate_secs_per_line}
      channel: "{channel}"
      watermark_enabled: {watermark_enabled}
      watermark_text: "{watermark_text}"
      video_fps: {video_fps}
      tts_engine: "{tts_engine}"
      tts_voices: {tts_voices}
      bg_opacity: {debate_bg_opacity}
      debate_background_enabled: {debate_background_enabled}
      debate_background_prompt: "{debate_background_prompt}"
      image_gen_backend: "{image_gen_backend}"

    Output files in {output_dir}/:
      debate_video_Shorts.mp4
      debate_video_Shorts_audio.mp3
      debate_video_Shorts_with_audio.mp4

  expected_output: >
    Shorts debate video created from -m scripts.
    Example: "✅ Shorts: debate_video_Shorts_with_audio.mp4 (2100 KB)  Duration: 58.0s"
  agent: debate_video_producer

# ─────────────────────────────────────────────────────────────
# MINI DEBATE TASKS  (-m.md)
# Target audio duration: 1–1.30 min per section (≈ 120–180 words each)
# Output files: propose-m.md / oppose-m.md / decide-m.md
# ─────────────────────────────────────────────────────────────

debate_propose_m:
  description: >
    You are proposing the motion: "{topic}".
    Write SHORT, punchy arguments IN FAVOR for the @{channel} channel.
    Format your response EXACTLY like this with blank lines between sections:

    PROPOSITION: {topic}

    OPENING STATEMENT

    [1 sentence establishing your position clearly]

    Argument 1: [Title]
    [1 sentence with evidence and reasoning]

    Argument 2: [Title]
    [1 sentence with evidence and reasoning]

    Argument 3: [Title]
    [1 sentence with evidence and reasoning]

    CONCLUSION

    [1 sentence summarizing why the motion should be upheld]

    Write ONLY the argument text — no tool calls, no JSON, no code.
    RULES:
    - 100–150 words total
    - Under {debate_mini_max_chars}
    - Keep sentences short and punchy
    - Add blank line between each section
  expected_output: >
    Full proposition argument as plain text, starting with "PROPOSITION: {topic}".
    Must be under {debate_mini_max_chars}. No tool calls or JSON.
  agent: debate_debater_m
  output_file: "{output_dir}/debate/propose-m.md"

debate_oppose_m:
  description: >
    You are opposing the motion: "{topic}".
    Write SHORT, punchy arguments AGAINST for the @{channel} channel.
    Format your response EXACTLY like this with blank lines between sections:

    OPPOSITION:  {topic} , Disagree!

    OPENING STATEMENT
    [1 sentence establishing your counter-position clearly]

    Counter-Argument 1: [Title]
    [1 sentence with evidence and reasoning]

    Counter-Argument 2: [Title]
    [1 sentence with evidence and reasoning]

    Counter-Argument 3: [Title]
    [1 sentence with evidence and reasoning]

    CONCLUSION
    [1 sentence summarizing why the motion should be rejected]

    Write ONLY the argument text — no tool calls, no JSON, no code.
    RULES:
    - 80–130 words total
    - Under {debate_mini_max_chars}
    - Keep sentences short and punchy
    - Add blank line between each section
  expected_output: >
    Full opposition argument as plain text, starting with "OPPOSITION: {topic}".
    Must be under {debate_mini_max_chars}. No tool calls or JSON.
  agent: debate_debater_m
  context:
    - debate_propose_m
  output_file: "{output_dir}/debate/oppose-m.md"

debate_decide_m:
  description: >
    You are compressing the HD verdict for mobile Shorts format.
    Topic: "{topic}"

    The HD judge has already decided the winner: {hd_winner} WINS.
    Your job is NOT to re-judge — just write a punchy, Shorts-friendly
    version that reflects THIS EXACT winner.

    CRITICAL: DO NOT USE ## MARKDOWN. Use plain headers.

    Copy this EXACT format with blank lines:

    VERDICT: {topic}

    SUMMARY

    PROPOSITION: [1 sentence — PRO side's strongest claim]

    OPPOSITION: [1 sentence — CON side's strongest claim]

    ANALYSIS

    [1 sentences comparing both sides. Do NOT declare winner yet.]


    DECISION

    {hd_winner} WINS.
    [Then 1  decisive sentences using words like "crushes", "dismantles",
     "outweighs", "lands the knockout".]

    CRITICAL RULES:
    - The DECISION line MUST be EXACTLY "{hd_winner} WINS." — do not change it
    - If hd_winner is "UNKNOWN", fall back to picking a winner yourself
      (never DRAW in Shorts)
    - DO NOT write "## SUMMARY" or "## ANALYSIS" or "## DECISION"
    - Write plain text: "SUMMARY", "ANALYSIS", "DECISION"
    - Blank line AFTER VERDICT
    - Blank line BEFORE and AFTER each section heading
    - 40-100 words total
    - Under {debate_mini_max_chars} characters

  expected_output: >
    Short verdict matching the HD winner exactly, compressed for mobile.

  agent: debate_judge_m
  context:
    - debate_propose_m
    - debate_oppose_m
  output_file: "{output_dir}/debate/decide-m.md"

# ─────────────────────────────────────────────────────────────
# FULL-LENGTH DEBATE TASKS  (standard .md)
# ─────────────────────────────────────────────────────────────
debate_propose:
  description: >
    You are proposing the motion: "{topic}".
    Write compelling, well-structured arguments IN FAVOR for the @{channel} channel.
    Format your response EXACTLY like this with blank lines between sections:

    PROPOSITION: {topic}

    OPENING STATEMENT

    [1-3 sentences establishing your position clearly]

    Argument 1: [Title]
    [1-4 sentences with evidence and reasoning]

    Argument 2: [Title]
    [1-4 sentences with evidence and reasoning]

    Argument 3: [Title]
    [1-3 sentences with evidence and reasoning]

    CONCLUSION

    [1-3 sentences summarizing why the motion should be upheld]

    Keep total response under {debate_max_chars} characters.
    Write ONLY the argument text — no tool calls, no JSON, no code.
    IMPORTANT: Add a blank line between each section for readability.
  expected_output: >
    Full proposition argument as plain text, starting with "PROPOSITION: {topic}".
    Must be under {debate_max_chars} characters. No tool calls or JSON.
  agent: debate_debater
  output_file: "{output_dir}/debate/propose.md"

debate_oppose:
  description: >
    You are opposing the motion: "{topic}".
    Write compelling, well-structured arguments AGAINST for the @{channel} channel.
    Format your response EXACTLY like this with blank lines between sections:

    OPPOSITION: {topic} , Disagree!

    OPENING STATEMENT

    [1-3 sentences establishing your counter-position clearly]

    Counter-Argument 1: [Title]
    [1-4 sentences with evidence and reasoning]

    Counter-Argument 2: [Title]
    [1-4 sentences with evidence and reasoning]

    Counter-Argument 3: [Title]
    [1-3 sentences with evidence and reasoning]

    CONCLUSION

    [1-3 sentences summarizing why the motion should be rejected]

    Keep total response under {debate_max_chars} characters.
    Write ONLY the argument text — no tool calls, no JSON, no code.
    IMPORTANT: Add a blank line between each section for readability.
  expected_output: >
    Full opposition argument as plain text, starting with "OPPOSITION: {topic}".
    Must be under {debate_max_chars} characters. No tool calls or JSON.
  agent: debate_debater
  context:
    - debate_propose
  output_file: "{output_dir}/debate/oppose.md"

debate_decide:
  description: >
    You are the judging panel for the debate on: "{topic}".

    CRITICAL: DO NOT USE ## MARKDOWN HEADERS. Use plain text headers.

    Copy this EXACT structure (each line shown is separate):

    VERDICT: {topic}

    SUMMARY

    PROPOSITION: [1-2 sentences summarizing PRO arguments]

    OPPOSITION: [1-2 sentences summarizing CON arguments]

    ANALYSIS

    [1-3 sentences comparing both sides. Identify strongest/weakest claims. Do NOT declare winner.]

    DECISION

    PROPOSITION WINS.
    [OR] OPPOSITION WINS.
    [Then 2-3 sentences explaining which side landed the stronger blow, citing ONE specific argument that tipped it.]
    JUDGING RULES (MANDATORY):
    - A verdict of "DRAW" is ONLY allowed if both sides are mathematically equal on evidence AND logic AND real-world impact. This is extremely rare (<5% of debates).
    - If one side had even ONE stronger data point, clearer framing, or more undeniable consequence, that side WINS.
    - Force yourself to pick a winner. Ties are a failure of analysis, not a legitimate outcome.
    - Lead with conflict language: "lands the harder blow", "exposes a critical flaw", "dismantles", "undermines", "outweighs".
    - Avoid hedging words: "both have merit", "it depends", "balanced", "nuanced".
    FORMAT RULES:
    - PROPOSITION and OPPOSITION on SEPARATE lines under SUMMARY
    - Blank line BEFORE each heading (SUMMARY, ANALYSIS, DECISION)
    - Blank line AFTER each heading
    - First DECISION sentence must be EXACTLY: "PROPOSITION WINS." or "OPPOSITION WINS." (DRAW only in true ties)
    - Under {debate_max_chars} characters
  expected_output: >
    Verdict with proper spacing and exact format.
  agent: debate_judge
  context:
    - debate_propose
    - debate_oppose
  output_file: "{output_dir}/debate/decide.md"
# ─────────────────────────────────────────────────────────────
# DEBATE DEFINITION TASK — compresses & saves all .md files
# Replaces the post_process_from_disk() call that was in main.py
# ─────────────────────────────────────────────────────────────
debate_create_definition:
  description: >
    Compress and save all debate text files for {topic}.
    This task runs only when debate_definition_enabled=true. If false, skip.

    CRITICAL — NEVER call DataDefinition — it is forbidden for this task,Call ONLY the DebateDefinition tool with EXACTLY these values:
      topic: "{topic}"
      filename: "{filename}"
      output_dir: "{output_dir}"
      propose_text: ""
      oppose_text: ""
      decide_text: ""
      debate_definition_enabled: {debate_definition_enabled}
      channel: "{channel}"
      debate_max_chars: {debate_max_chars}
      lang_suffix: ""
      use_label_mappings: {use_label_mappings}  # ✅ MUST BE INCLUDED
      force_regenerate: false

    ⚠️  CRITICAL: Call ONLY the DebateDefinition tool. NEVER call DataDefinition — it is forbidden for this task.

    ⚠️  CRITICAL: Call ONLY the DebateDefinition tool. NEVER call DataDefinition — it is forbidden for this task.

    ⚠️  CRITICAL: Call ONLY the DebateDefinition tool. NEVER call DataDefinition — it is forbidden for this task.

    The tool reads propose.md / oppose.md / decide.md from {output_dir}
    automatically when propose_text / oppose_text / decide_text are empty.
    Smart skip: if all 6 files already exist and are non-empty, returns immediately.

    Output files in {output_dir}/:
      Full (HD)  : propose.md  oppose.md  decide.md
      Mobile (-m): propose-m.md              oppose-m.md              decide-m.md


  expected_output: >
    Confirmation of all 6 debate files written with char counts,
    OR smart-skip message if all files already exist,
    OR error if source .md files are missing.
    Example: "Debate files generated in 0.3s\n\nPROPOSE: 1820 -> 1650 chars..."
  agent: debate_definition_specialist
  context:
    - debate_propose
    - debate_oppose
    - debate_decide

# ✅ NEW: Debate Merge Task (ADDED - DO NOT REMOVE)
debate_merge:
  description: >
    Concatenate intro + debate video segments WITH AUDIO into a single final MP4 per format.
    This task will automatically skip if debate_merge_enabled is false in inputs.

    CRITICAL — You MUST call the Debate Merge Tool with EXACTLY these values:
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      debate_merge_enabled: {debate_merge_enabled}
      channel: "{channel}"
      topic: "{topic}"
      topic_slug: "{topic_slug}"
      lang_suffix: ""

    WARNING: Do NOT use output from previous tasks as your answer.
    You MUST actually call the Debate Merge Tool right now.
    Do NOT fabricate, assume, or reuse any prior output.
    The tool produces a DIFFERENT file than debate_video — it creates the final
    merged {channel}_{topic_slug}_[fmt].mp4 file.
    Call the tool ONCE and return its exact output as your Final Answer immediately.
    Any output containing "completed", "skipped", "SUCCESS", or "✅" means the tool
    finished — return it immediately as your Final Answer without calling again.
  expected_output: >
    The raw output from the Debate Merge Tool, e.g.:
    ✅ COMPLETE: 1/1 formats merged
    ✅ HD: PlayOwnAi_Debate_Is_Python_King_Still_HD_En.mp4 (XX.X MB)
  agent: debate_merge_specialist

debate_generate_scores:
  description: >
    Read the three debate files for "{topic}" from {output_dir}/debate/:
    propose.md, oppose.md, decide.md.

    Assign integer scores between 8 and 20 to each row below, reflecting
    who won that specific round (not overall). Use the final DECISION line
    in decide.md ("PROPOSITION WINS.", "OPPOSITION WINS.", or "DRAW.") to
    bias the totals so the declared winner has a higher total score.

    Extract short titles from each "Argument N:" heading in propose.md and
    each "Counter-Argument N:" heading in oppose.md. Keep each title under
    42 characters.

    Output ONLY a raw JSON object (no markdown fences, no prose) with this
    exact shape:

    {{
      "opening": {{ "pro": INT, "con": INT, "pro_title": "General", "con_title": "General" }},
      "args": [
        {{ "pro": INT, "con": INT, "pro_title": "STRING", "con_title": "STRING" }}
      ],
      "totals": {{ "pro": INT_SUM_OF_PRO, "con": INT_SUM_OF_CON }},
      "winner": "propose"
    }}

    Where:
      - INT is any integer from 8 to 20.
      - "winner" must be one of: "propose", "oppose", "draw".
      - "totals" must equal the arithmetic sum of opening plus args scores.
      - The winner's total must be strictly greater than the loser's total.
        For a draw, totals must be equal.
      - Only include rows that actually appear in the source files (usually
        3 argument pairs for HD).

  expected_output: >
    A single JSON object, parseable with json.loads().

  agent: debate_score_analyst
  output_file: "{output_dir}/debate/scores.json"

# ── Unit-Publisher ────────────────────────────────────────────────────────
publisher_upload_to_facebook:
  description: >
    Upload final merged videos to the Facebook Page for {topic}.
    Shorts → Facebook Reels. HD → Facebook Video.
    Skips automatically if upload_facebook_video is false.

    CRITICAL — call the Facebook Upload Tool with EXACTLY these values:
      topic: "{topic}"
      output_dir: "{output_dir}"
      video_formats: {video_formats}
      upload_facebook_video: {upload_facebook_video}
      channel: "{channel}"
      privacy_status: "{fb_privacy_status}"
      credentials_file: "{fb_credentials_file}"

    The tool will (per format in video_formats):
      1. Locate {channel}_{topic_slug}_[fmt].mp4 in {output_dir}
      2. Read metadata from {output_dir}/YT/debate/[fmt]/MD/en.json
      3. Shorts → upload as Facebook Reel
         HD     → upload as Facebook Video
      4. Save fb_upload_log.json to {output_dir}/YT/debate/[fmt]/

    Smart skip: If fb_upload_log.json already contains a video_id, that format is skipped.
    Once you receive the tool output, return it immediately as your Final Answer.

  expected_output: >
    Upload confirmation per format with Facebook video URLs:
      ✅ Shorts: https://www.facebook.com/video/abc123
      ✅ HD: https://www.facebook.com/video/xyz456
    OR skip/already-uploaded message.
  agent: publisher_fb_upload_specialist

# ── Unit-Prodcast Tasks ─────────────────────────────────────────────────
prodcast_write_script:
  description: >
    Write a complete podcast script for the topic: "{topic}".
    Format as Host/Guest dialogue optimized for Edge TTS via TTSService.

    REQUIRED HEADER (first 4 lines, exactly):
    # Podcast Script: {topic}
    # Format: Host/Guest Dialogue
    # Host: {prodcast_host_name} ({prodcast_voice_host})
    # Guest: {prodcast_guest_name} ({prodcast_voice_guest})

    Then a blank line, then a short intro line:
    {prodcast_short_intro}

    Then a blank line, then the dialogue. Each line must start with
    either "Host:" or "Guest:" followed by one paragraph of speech.

    EPISODE FOCUS:
    {focus}

    If Focus is provided above, make it the central thread of the entire conversation.
    Build all examples, stories, and practical steps around this focus.
    If Focus is empty, use a standard broad exploration of the topic.

    Voice roles:
      - Host ({prodcast_host_name}) → opens, asks questions, summarises, closes
      - Guest ({prodcast_guest_name}) → expert who explains, gives examples, takes positions

    Length: 20-26 exchanges total (roughly 1,400-1,700 words of dialogue).
    Target audio length: approximately 10 minutes at normal speaking pace with breathing pauses.
    Each exchange should be 65 to 85 words to maintain depth without rushing.

    TTS articulation and emotional depth requirements:
    - Write for Edge TTS (en-US-AriaNeural for Host, en-US-GuyNeural or en-US-AndrewNeural for Guest)
    - Use punctuation-based pacing: ellipses... for breathing pauses, commas for micro-gaps
    - Expand each answer with one concrete story, one practical step, and one reflective question
    - Avoid summarizing too quickly, allow the Guest to elaborate for 3 to 4 sentences per turn
    - Keep the Host questions open ended to invite longer responses
    - Keep sentences short, 8 to 14 words, one idea per sentence
    - For EVERY Company, Person, or important Noun, write it in phonetic spoken form using the pattern of "Scale 3-6-0 A.I."
      * separate words with spaces
      * separate numbers with hyphens
      * separate acronym letters with periods
      * examples: "OpenAI" becomes "Open A.I.", "iPhone15" becomes "iPhone 1-5", "NASA" becomes "N.A.S.A."
    - Italicize key emotional terms using *word* for subtle inflection shift
    - Avoid semicolons and rushed connectors, prefer period breaks
    - Vary rhythm: pause before important terms, use trailing pauses for reflection

    Dynamic variables (never hardcode):
    - Use @{channel} for podcast name
    - Use {prodcast_guest_name} for guest's full name, already in spoken form
    - Use {guestCompany} for guest's company or product, already in "Scale 3-6-0 A.I." form
    - Use {prodcast_host_name} and {prodcast_guest_name} for speaker labels

    Example enhanced intro:
    Host: Welcome back to @{channel}... everyone. Today, we're diving into a topic that touches every single one of us, *emotional intelligence* in relationships. I'm your host, {prodcast_host_name}... and I'm thrilled, truly thrilled, to have {prodcast_guest_name} with us today. {prodcast_guest_name} is a professional coach, AI entrepreneur... and the founder of {guestCompany}.

    Orchestrator hints for prodcast_voice_generator.py:
    - Set prodcast_pause_between_lines_ms to 600-800 for natural breathing room
    - Keep audio_speed at 0.95 for warmer articulation
    - Use rate_pct 0 to preserve emotional nuance

    Tone: conversational, warm, emotionally present, no stage directions,
    no markdown bullets, no headings inside dialogue body,
    no parenthetical cues like (laughs) or [pause].

  expected_output: >
    A markdown file with the 4-line header, intro line, followed by alternating
    Host:/Guest: lines, one paragraph each, written with punctuation-based
    breathing pauses and with every Company, Person, or Noun rendered in
    "Scale 3-6-0 A.I." phonetic form for Edge TTS.

# ── Unit-Classroom Tasks ─────────────────────────────────────────────────
create_classroom_script:
  description: >
    Write a full classroom dialogue for topic: {topic}.
    Roles: [T1] Teacher1 (male lead), [T2] Teacher2 (female simplifier),
    [S1-F] Curious, [S2-M] Smart, [S3-F] Confused, [S4-M] Creative,
    [S5-F] Funny, [S6-M] Doubter, [S7-F] Quiet, [S8-M] Beginner.

    REQUIRED STRUCTURE in this exact order:

    [T1] Teacher1: Lesson Goal —
    One sentence stating what kids will learn.

    [T2] Teacher2: Today you will learn —
    3-4 bullet points in kid-friendly language listing specific skills or knowledge.

    [T1] Teacher1: Before we start, think —
    2-3 short questions to spark curiosity before the lesson begins.

    [PHASE:hook]
    [PHASE:explain]
    [PHASE:interaction]
    [PHASE:example]
    [PHASE:reinforcement]
    [PHASE:fun_fact]
    [PHASE:recap_quiz]

    [QUIZ]
    3 numbered questions with answers in (parentheses).

    [KEY POINTS]
    3-4 bullet takeaways.

    [T2] Teacher2:
    One warm closing sentence from a teacher to leave kids feeling good.

    Rules: max 12 words per line, grade 3-5 vocabulary, every student speaks
    at least once, 3-5 students active per phase.
  expected_output: >
    Full script saved to {classroom_dir}/script.md with all sections in order:
    LESSON GOAL, LEARNING OBJECTIVES, PRE-THINK, 7 PHASES, QUIZ, KEY POINTS,
    EMOTIONAL CLOSURE.
  agent: classroom_script_writer
  output_file: "{classroom_dir}/script.md"

# ── Unit-LeadData Tasks ─────────────────────────────────────────────────
unit_leaddata:
  description: >
    Execute the Unit-LeadData pipeline for topic: {topic}.
    Collect leads via Maps API and Reviewer Intent Mining, normalize,
    score, and export results according to leaddata_config.
    Adheres to CF2 Rules: 3, 4, 21, 24, 37, 39.
  expected_output: >
    Completion status string ('done', 'disabled', or 'failed').
    Output files in leaddata/ directory: raw, normalized, scored CSV/JSON + stats.
  agent: leaddata_specialist
  config:
    leaddata_config:
      enabled: true
      sources: ["maps_reviewers"]  # Default B2C source; Profile overrides this
      collect_config:
        max_results_per_keyword: 50
        skip_if_cached: true
        request_timeout: 60
        reviewer_mining:
          enabled: true
          review_recency_days: 360
          min_reviewer_activity: 1
      normalize_config:
        deduplicate_on: ["name"]
        phone_country_default: "US"
        lowercase_email: true
        min_name_length: 2
      score_config:
        score_enabled: true
        segment_thresholds: { "hot": 60, "warm": 35, "cold": 0 }
      export_config:
        formats: ["csv", "json"]
        generate_stats: true

leaddata_reddit_scrape:
  description: >
    Scrape Reddit travel communities for high-intent planners.
    Keywords: {keywords} | Subreddits: {subreddits}
    Appends findings to raw leads pipeline.
  expected_output: >
    List of Reddit users with travel intent + profile URLs.
  agent: leaddata_reddit_agent
  config:
    reddit_config:
      subreddits: ["travel", "solotravel", "allinclusive", "honeymoon"]
      min_karma: 50
      post_recency_days: 30
      max_posts_per_sub: 100

=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
=================================================================================
