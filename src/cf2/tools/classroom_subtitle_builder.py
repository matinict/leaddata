"""
cf2/tools/classroom_subtitle_builder.py
subUnitSubtitle: script.md + audio.mp3 → .srt + cc_en.txt
Equal-duration estimation per dialogue line.
"""
from pathlib import Path
import re

_SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+(\w[\w\s\-]*?):\s+(.+)$")


def _ts(sec: float) -> str:
    h  = int(sec // 3600)
    m  = int((sec % 3600) // 60)
    s  = int(sec % 60)
    ms = int((sec - int(sec)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def run(
    script_path: str,
    audio_path: str,
    srt_out: str,
    cc_out: str,
) -> None:
    from cf2.core.services.audio_service import AudioService

    audio_svc  = AudioService(logger=lambda m: None)
    total_dur  = audio_svc.get_duration(audio_path) or 60.0
    script_txt = Path(script_path).read_text("utf-8")

    lines = [
        (m.group(1), m.group(2).strip(), m.group(3).strip())
        for line in script_txt.splitlines()
        if (m := _SPEAKER_RE.match(line.strip()))
    ]
    if not lines:
        return

    seg_dur  = total_dur / len(lines)
    srt_blks, cc_rows = [], []

    for i, (tag, speaker, text) in enumerate(lines):
        start = i * seg_dur
        end   = start + seg_dur - 0.05
        label = f"[{tag}] {speaker}: {text}"
        srt_blks.extend([str(i + 1), f"{_ts(start)} --> {_ts(end)}", label, ""])
        cc_rows.append(label)

    Path(srt_out).write_text("\n".join(srt_blks), encoding="utf-8")
    Path(cc_out).write_text("\n".join(cc_rows),  encoding="utf-8")
