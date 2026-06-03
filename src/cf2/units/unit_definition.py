from pathlib import Path
from cf2.crews.crew import CF2Crew

def run(topic: str, inputs: dict):
    inputs["output_dir"] = inputs["_workspace"]
    factory = CF2Crew(inputs)
    agents, tasks = [], []

    if inputs.get("definition_enabled"):
        agents += [factory.data_definition_specialist()]; tasks += [factory.data_define_topic()]
    if inputs.get("definition_video"):
        agents += [factory.definition_video_producer()];  tasks += [factory.definition_create_video()]

    if not tasks:
        print("⚠️  Unit-Definition: no tasks enabled"); return
    from crewai import Crew
    return Crew(agents=agents, tasks=tasks, verbose=False).kickoff(inputs=inputs)
