"""
cf2/tools/classroom_roles_generator.py
subUnitRoles: generate roles.json from classroom_config.
Called by unit_data.py (Rule D-6). Zero LLM calls.
"""
import json
from pathlib import Path

_PERSONALITIES = {
    "S1": {"personality": "curious",  "speech": "Asks what/how/why — eager short questions"},
    "S2": {"personality": "smart",    "speech": "Confident concise correct answers"},
    "S3": {"personality": "confused", "speech": "I don't understand — gentle clarification"},
    "S4": {"personality": "creative", "speech": "Imaginative real-life connections"},
    "S5": {"personality": "funny",    "speech": "Playful brief humor"},
    "S6": {"personality": "doubter",  "speech": "But I thought — mild non-aggressive"},
    "S7": {"personality": "quiet",    "speech": "1-2 word impactful insights"},
    "S8": {"personality": "beginner", "speech": "Very simple vocabulary"},
}

_VOICE_DEFAULTS = {
    "T1": "en-US-AndrewNeural",
    "T2": "en-US-JennyNeural",
    "S1": "en-US-AnaNeural",
    "S2": "en-US-BrianNeural",
    "S3": "en-US-EmmaNeural",
    "S4": "en-US-ChristopherNeural",
    "S5": "en-US-MichelleNeural",
    "S6": "en-US-GuyNeural",
    "S7": "en-US-AriaNeural",
    "S8": "en-US-EricNeural",
}

_LABEL_COLORS = {
    "T1": "#4FC3F7", "T2": "#F48FB1",
    "S1": "#FFD54F", "S2": "#81C784",
    "S3": "#FF8A65", "S4": "#64B5F6",
    "S5": "#F06292", "S6": "#A1887F",
    "S7": "#90A4AE", "S8": "#CE93D8",
}


def run(workspace_dir: str, classroom_cfg: dict) -> str:
    classroom_dir = Path(workspace_dir) / "classroom"
    classroom_dir.mkdir(parents=True, exist_ok=True)
    roles_path = classroom_dir / "roles.json"

    if roles_path.exists():
        return "⏭️ Skipped — roles.json exists"

    vm     = classroom_cfg.get("voice_mapping", {})
    gd     = classroom_cfg.get("gender_distribution", {})
    male   = set(gd.get("male",   ["S2", "S4", "S6", "S8"]))
    stu_vm = vm.get("students", {})
    count  = classroom_cfg.get("student_count", 8)

    roles = {
        "teachers": {
            "T1": {
                "role": "lead_teacher", "gender": "M",
                "voice": vm.get("teacher_1", _VOICE_DEFAULTS["T1"]),
                "speech": "Clear structured question-driven",
                "label_color": _LABEL_COLORS["T1"],
                "personality": "Lead Teacher",
            },
            "T2": {
                "role": "helper_teacher", "gender": "F",
                "voice": vm.get("teacher_2", _VOICE_DEFAULTS["T2"]),
                "speech": "Warm relatable real-life analogies",
                "label_color": _LABEL_COLORS["T2"],
                "personality": "Helper Teacher",
            },
        },
        "students": {
            f"S{i}": {
                **_PERSONALITIES.get(f"S{i}", {"personality": "beginner", "speech": "Simple vocabulary"}),
                "gender":      "M" if f"S{i}" in male else "F",
                "voice":       stu_vm.get(f"S{i}", _VOICE_DEFAULTS.get(f"S{i}", "en-US-JennyNeural")),
                "label_color": _LABEL_COLORS.get(f"S{i}", "#FFFFFF"),
            }
            for i in range(1, count + 1)
        },
    }

    roles_path.write_text(json.dumps(roles, indent=2, ensure_ascii=False), encoding="utf-8")
    return f"✅ roles.json written: {roles_path}"
