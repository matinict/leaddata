import sys
from pathlib import Path
from cf2.crews.crew import CF2Crew

def run(topic: str, inputs: dict):
    topic_dir = Path(inputs["_workspace"])
    csv_file  = topic_dir / "animation" / "data.csv"
    if not csv_file.exists():
        print(f"❌ Missing: {csv_file}"); raise RuntimeError(f"Missing: {csv_file} — run Unit-Data first")
    inputs["csv_file"]   = str(csv_file)
    inputs["output_dir"] = str(topic_dir)
    inputs["filename"] = inputs.get("_slug", topic_dir.name)
    factory = CF2Crew(inputs)
    agents, tasks = [], []

    if inputs.get("intro_enabled"):
        agents += [factory.animation_intro_producer()];       tasks += [factory.animation_create_intro_clip()]
    if inputs.get("bar_race_video_enabled"):
        agents += [factory.animation_bar_race_producer()];    tasks += [factory.animation_create_bar_race_video()]
    if inputs.get("bar_race_audio_enabled"):
        agents += [factory.animation_bar_race_audio_engineer()]; tasks += [factory.animation_add_audio()]
    if inputs.get("bar_merge_enabled"):
        agents += [factory.animation_bar_merge_specialist()]; tasks += [factory.animation_bar_merge()]

    if not tasks:
        print("⚠️  Unit-Animation: no tasks enabled"); return
    from crewai import Crew
    return Crew(agents=agents, tasks=tasks, verbose=False).kickoff(inputs=inputs)
