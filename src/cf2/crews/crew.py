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
