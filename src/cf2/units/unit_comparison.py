from pathlib import Path
from cf2.crews.crew import CF2Crew

def run(topic: str, inputs: dict):
    topic_dir = Path(inputs["_workspace"])
    (topic_dir / "comparison").mkdir(parents=True, exist_ok=True)
    inputs["output_dir"] = str(topic_dir)
    inputs["filename"] = inputs.get("_slug", topic_dir.name)
    factory = CF2Crew(inputs)
    return factory.crew().kickoff(
        agents=[factory.debate_debater(), factory.debate_debater(), factory.debate_judge()],
        tasks=[factory.debate_propose(), factory.debate_oppose(), factory.debate_decide()],
        inputs=inputs)
