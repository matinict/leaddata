"""
cf2/tools/classroom_script_generator.py
subUnitScript: LLM generates classroom script.md + script-m.md + quiz.json
Called by unit_data.py when Unit-Classroom=true (Rule D-6).
Mirrors: prodcast_script_generator.py
"""
import json, re
from pathlib import Path


def run(topic: str, workspace_dir: str, inputs: dict) -> str:
    from cf2.crews.crew import CF2Crew

    classroom_dir = Path(workspace_dir) / "classroom"
    classroom_dir.mkdir(parents=True, exist_ok=True)
    script_path = classroom_dir / "script.md"

    if script_path.exists() and script_path.stat().st_size > 200 and inputs.get("classroom_skip_if_cached", True):
        return f"⏭️ Skipped — script exists: {script_path}"

    factory = CF2Crew(inputs=inputs)
    crew_inputs = {
        **inputs,
        "topic":         topic,
        "classroom_dir": str(classroom_dir),
    }
    result = factory.crew().kickoff(
        agents=[factory.classroom_script_writer()],
        tasks=[factory.create_classroom_script()],
        inputs=crew_inputs,
    )
    raw = str(result)
    script_path.write_text(raw, encoding="utf-8")

    mini = _compress(raw)
    (classroom_dir / "script-m.md").write_text(mini, encoding="utf-8")

    quiz = _extract_quiz(raw)
    (classroom_dir / "quiz.json").write_text(
        json.dumps(quiz, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return f"✅ script.md written ({script_path.stat().st_size} chars)"


def _compress(raw: str) -> str:
    skip = {"reinforcement", "fun_fact"}
    lines, skipping = [], False
    for line in raw.splitlines():
        m = re.match(r"^\[PHASE:(\w+)\]", line.strip(), re.IGNORECASE)
        if m:
            skipping = m.group(1).lower() in skip
        if not skipping:
            lines.append(line)
    return "\n".join(lines)


def _extract_quiz(raw: str) -> dict:
    block = re.search(r"\[QUIZ\](.*?)(\[KEY|\Z)", raw, re.DOTALL | re.IGNORECASE)
    if not block:
        return {"question": "", "options": {}}
    text  = block.group(1).strip()
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    q     = lines[0] if lines else ""
    opts  = {}
    for l in lines[1:]:
        m = re.match(r"^([A-C])[.)]\s+(.+)$", l)
        if m:
            opts[m.group(1)] = m.group(2)
    return {"question": q, "options": opts}
