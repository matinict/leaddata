"""🔥 subUnitScript: Convert structured content → natural podcast conversation"""

from pathlib import Path
from cf2.crews.crew import CF2Crew

def run(context: dict, output_path: str, inputs: dict) -> str:
    """
    Generate podcast script from debate/definition/comparison MD files.
    Smart Skip: Returns early if output already exists.
    """
    output_file = Path(output_path)

    # Rule 32: Smart Skip mandatory
    if output_file.exists() and output_file.stat().st_size > 100:
        return f"⏭️ Skipped — script already exists: {output_path}"

    # Rule 14: Explicit agent/task selection via factory
    factory = CF2Crew()

    # Only run if script is needed
    agents = [factory.prodcast_scriptwriter()]
    tasks = [factory.prodcast_generate_script()]

    # Prepare inputs for Crew (Rule 28: no hardcoded values)
    crew_inputs = {
        **context,
        "channel": inputs.get("channel", "PlayOwnAi"),
        "tone": inputs.get("prodcast", {}).get("tone", "conversational"),
        **inputs
    }

    result = factory.crew().kickoff(agents=agents, tasks=tasks, inputs=crew_inputs)

    # Save output (Rule 20: idempotent writes)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(str(result))

    return f"✅ Script generated: {output_path} ({output_file.stat().st_size} chars)"
