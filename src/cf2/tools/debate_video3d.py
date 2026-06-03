"""
tools/debate_video3d.py — Thin CrewAI Tool Wrapper

Responsibility: Expose debate video generation as a CrewAI tool.
ALL logic lives in unit_debate.run() — this file only delegates.

Rule 3: Tools are execution blocks — no intelligence here.
"""
from pathlib import Path
from typing import Type, Dict, Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from cf2.units.unit_debate import run as _debate_run


class DebateVideo3dInput(BaseModel):
    topic:  str              = Field(description="Topic / filename slug")
    inputs: Dict[str, Any]  = Field(description="Full config from data.json")


class DebateVideo3dTool(BaseTool):
    name:        str = "debate_video3d"
    description: str = "Generate 3D debate video with topic overlay and subtitles."
    args_schema: Type[BaseModel] = DebateVideo3dInput

    def _run(self, topic: str, inputs: Dict[str, Any]) -> str:
        workspace = Path(inputs.get("_workspace", f"output/{topic}"))
        return _debate_run(topic=topic, workspace=workspace, inputs=inputs)
