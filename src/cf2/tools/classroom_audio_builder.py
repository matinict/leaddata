"""
src/cf2/tools/classroom_audio_builder.py
Per-line TTS via cf2.core.tts global resolver.
Fully config-driven — no provider logic here.
"""
from pathlib import Path
import os, subprocess, re
import logging

logger = logging.getLogger(__name__)

_XTTS_MODEL = None
_XTTS_CONFIG = None
_XTTS_LATENTS = {}

def _synthesize_xtts(text: str, output_path: str, speaker_wav: str) -> bool:
    """XTTS voice clone — copied from prodcast_voice_generator"""
    try:
        import torch
        import torchaudio
        from pathlib import Path
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        if not Path(speaker_wav).exists():
            logger.error("[XTTS] speaker wav not found: %s", speaker_wav)
            return False

        # split long text
        def split_text(t, max_chars=240):
            sentences = re.split(r'(?<=[.!?])\s+', t.strip())
            chunks, cur = [], ""
            for s in sentences:
                if len(cur) + len(s) + 1 <= max_chars:
                    cur = (cur + " " + s).strip()
                else:
                    if cur: chunks.append(cur)
                    if len(s) > max_chars:
                        for i in range(0, len(s), max_chars):
                            chunks.append(s[i:i+max_chars])
                        cur = ""
                    else:
                        cur = s
            if cur: chunks.append(cur)
            return chunks or [t[:max_chars]]

        chunks = split_text(text)

        global _XTTS_MODEL, _XTTS_CONFIG
        if _XTTS_MODEL is None:
            model_dir = Path("models/xtts")
            _XTTS_CONFIG = XttsConfig(); _XTTS_CONFIG.load_json(str(model_dir / "config.json"))
            _XTTS_MODEL = Xtts.init_from_config(_XTTS_CONFIG)
            _XTTS_MODEL.load_checkpoint(_XTTS_CONFIG, checkpoint_dir=str(model_dir), eval=True)
            _XTTS_MODEL.cpu()
            logger.info("[XTTS] model loaded (CPU)")

        if speaker_wav not in _XTTS_LATENTS:
            logger.info("[XTTS] computing latents for %s", speaker_wav)
            _XTTS_LATENTS[speaker_wav] = _XTTS_MODEL.get_conditioning_latents(
                audio_path=[speaker_wav], gpt_cond_len=15, max_ref_length=30
            )
        gpt_cond, speaker_emb = _XTTS_LATENTS[speaker_wav]

        wavs = []
        for chunk in chunks:
            out = _XTTS_MODEL.inference(
                text=chunk, language="en",
                gpt_cond_latent=gpt_cond,
                speaker_embedding=speaker_emb,
                temperature=0.3, speed=1.1,
            )
            wavs.append(torch.tensor(out["wav"]))

        full_wav = torch.cat(wavs) if len(wavs) > 1 else wavs[0]
        torchaudio.save(output_path, full_wav.unsqueeze(0), 24000, format="mp3")
        return True
    except Exception as e:
        logger.error("[XTTS] synthesis failed: %s", e, exc_info=False)
        return False

def _is_valid_mp3(path) -> bool:
    """Check MP3 has valid duration > 0.3s via ffprobe."""
    import subprocess
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=5
        )
        if r.returncode != 0:
            return False
        return float(r.stdout.strip() or 0) > 0.3
    except Exception:
        return False



_SECTION_SPEAKER = {
    "LESSON GOAL":         "T1",
    "LEARNING OBJECTIVES": "T2",
    "PRE-THINK":           "T1",
    "QUIZ":                "T1",
    "KEY POINTS":          "T2",
    "EMOTIONAL CLOSURE":   "T2",
}


import re as _re
_QUIZ_KP_RE = _re.compile(r"^\[(QUIZ|KEY POINTS)\]\s*(.+)$", _re.IGNORECASE)

def _expand_sections(script_txt: str) -> str:
    """Convert [SECTION]\ncontent into [Tx] Teacher: content lines."""
    out = []
    current = None
    for line in script_txt.splitlines():
        _qkm = _QUIZ_KP_RE.match(line.strip())
        if _qkm:
            _spk = "T1" if _qkm.group(1).upper() == "QUIZ" else "T2"
            _tn = "Teacher1" if _spk == "T1" else "Teacher2"
            out.append(f"[{_spk}] {_tn}: {_qkm.group(2).strip()}")
            continue
        s = line.strip()
        m = re.match(r"^\[([A-Z][A-Z\s\-_]+)\]\s*(.*)$", s)
        if m and m.group(1) in _SECTION_SPEAKER:
            current = _SECTION_SPEAKER[m.group(1)]
            inline = m.group(2).strip()
            if inline:
                out.append(f"[{current}] Teacher{1 if current=='T1' else 2}: {inline}")
            continue
        if s.startswith("[PHASE:") or s.startswith("[T") or s.startswith("[S"):
            current = None
            out.append(line)
            continue
        if current and s and not s.startswith("["):
            tname = "Teacher1" if current == "T1" else "Teacher2"
            # Split bullet/numbered lines
            cleaned = re.sub(r"^[-*\d.)\s]+", "", s).strip()
            if cleaned:
                out.append(f"[{current}] {tname}: " + ("\u2705 " + cleaned if current=="T2" else cleaned))
            continue
        out.append(line)
    return "\n".join(out)


_SPEAKER_RE = re.compile(r"^\[(\S+?)\]\s+\w[\w\s\-]*?:\s+(.+)$")


def run(
    script_path:    str,
    output_path:    str,
    fmt:            str = "HD",
    voice_mapping:  dict = None,            # legacy, ignored
    audio_speed:    float = 1.05,
    pause_ms:       int = 350,
    tts_tier:       str = None,
    unit_name:      str = "Unit-Classroom",
    audio_cfg:      dict = None,
) -> None:
    audio_cfg = audio_cfg or {}
    from cf2.core.tts import synthesize, resolve_tier_for_unit
    from cf2.core.services.audio_service import AudioService
    from cf2.core.services.ffmpeg_service import FFmpegService

    tier       = tts_tier or resolve_tier_for_unit(unit_name)
    script_txt = Path(script_path).read_text("utf-8")
    script_txt = _expand_sections(script_txt)
    out_path   = Path(output_path)
    seg_dir    = out_path.parent / f"_cls_segs_{fmt}"
    seg_dir.mkdir(parents=True, exist_ok=True)

    audio  = AudioService(logger=lambda m: print(f"[CLS-Audio] {m}"))
    ffmpeg = FFmpegService()

    pause_file = seg_dir / "_pause.mp3"
    if not pause_file.exists() or pause_file.stat().st_size < 100:
        import subprocess as _sp
        _r = _sp.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anullsrc=r=24000:cl=mono",
            "-t", str(pause_ms / 1000.0),
            "-q:a", "9", "-acodec", "libmp3lame",
            str(pause_file)
        ], capture_output=True)
        if _r.returncode != 0:
            print(f"[CLS-Audio] ⚠️ Pause file creation failed: {_r.stderr.decode()[:200]}")

    segments, idx = [], 0
    for raw in script_txt.splitlines():
        m = _SPEAKER_RE.match(raw.strip())
        if not m:
            continue
        tag_base = m.group(1).split("-")[0].upper()
        text     = m.group(2).strip()
        seg_file = seg_dir / f"seg_{idx:04d}.mp3"

        # Re-generate if file missing OR too small OR corrupted
        regenerate = (
            not seg_file.exists()
            or seg_file.stat().st_size < 512
            or not _is_valid_mp3(seg_file)
        )
        if regenerate:
            if seg_file.exists():
                seg_file.unlink()
            voice = None
            if voice_mapping:
                voice = voice_mapping.get(tag_base)
            if isinstance(voice, str) and voice.startswith("xtts:"):
                speaker_wav = voice.split("xtts:", 1)[1].strip()
                ok = _synthesize_xtts(text, str(seg_file), speaker_wav)
                provider = "xtts"
            else:
                ok, provider = synthesize(
                    text=text, output_path=str(seg_file),
                    tier=tier, speaker_tag=tag_base,
                    logger_fn=lambda m: print(f"[CLS-Audio] {m}"),
                )
            # Pitch up student voices to sound younger
            if ok and tag_base.startswith("S") and seg_file.exists():
                _tmp = str(seg_file) + ".pitch.mp3"
                _r = subprocess.run([
                    "ffmpeg", "-y", "-i", str(seg_file),
                    "-af", "asetrate=24000*1.18,aresample=24000,atempo=1/1.05",
                    "-b:a", "128k", _tmp
                ], capture_output=True)
                if _r.returncode == 0 and Path(_tmp).exists():
                    Path(_tmp).replace(seg_file)
            # Verify file is actually valid — corrupt files trigger regeneration
            if ok and not _is_valid_mp3(seg_file):
                print(f"[CLS-Audio] ⚠️  Corrupt seg_{idx:04d}.mp3 — regenerating")
                seg_file.unlink(missing_ok=True)
                voice = None
            if voice_mapping:
                voice = voice_mapping.get(tag_base)
            if isinstance(voice, str) and voice.startswith("xtts:"):
                speaker_wav = voice.split("xtts:", 1)[1].strip()
                ok = _synthesize_xtts(text, str(seg_file), speaker_wav)
                provider = "xtts"
            else:
                ok, provider = synthesize(
                    text=text, output_path=str(seg_file),
                    tier=tier, speaker_tag=tag_base,
                    logger_fn=lambda m: print(f"[CLS-Audio] {m}"),
                )
                # Last resort — silent placeholder
                if not _is_valid_mp3(seg_file):
                    seg_file.unlink(missing_ok=True)
                    est = max(1.0, min(len(text.split()) * 0.35, 6.0))
                    ffmpeg.create_silent_mp3(str(seg_file), duration=est)
                    provider = "silent_fallback"

            label = provider if provider != "silent_fallback" else "🔇 silent"
            print(f"[CLS-Audio] {'✅' if ok else '❌'} [{label}] seg_{idx:04d}.mp3 ({tag_base})")

        segments.extend([str(seg_file), str(pause_file)])
        idx += 1

    if not segments:
        ffmpeg.create_silent_mp3(str(out_path), duration=5.0)
        return

    if not pause_file.exists():
        ffmpeg.create_silent_mp3(str(pause_file), duration=pause_ms / 1000.0)

    audio.concatenate_audio(segments, str(out_path))

    # Config-driven post-processing
    volume      = audio_cfg.get("volume", 1.0)
    normalize   = audio_cfg.get("normalize", False)
    norm_lufs   = audio_cfg.get("normalize_lufs", -16)
    bitrate     = audio_cfg.get("bitrate", "192k")
    sample_rate = audio_cfg.get("sample_rate", 44100)
    channels    = audio_cfg.get("channels", 2)

    af_filters = []
    if normalize:
        af_filters.append(f"loudnorm=I={norm_lufs}:TP=-1.5:LRA=11")
    elif volume and volume != 1.0:
        af_filters.append(f"volume={volume}")
    if audio_speed and audio_speed != 1.0:
        af_filters.append(f"atempo={audio_speed}")

    if af_filters:
        tmp = str(out_path) + ".tmp.mp3"
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_path),
             "-af", ",".join(af_filters),
             "-ar", str(sample_rate), "-ac", str(channels),
             "-b:a", bitrate, tmp],
            capture_output=True
        )
        if r.returncode == 0 and os.path.exists(tmp):
            os.replace(tmp, str(out_path))
        elif os.path.exists(tmp):
            os.remove(tmp)
