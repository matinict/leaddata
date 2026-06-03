"""
🔊 subUnitVoice — prodcast_voice_generator.py Multi-voice TTS for podcast scripts
Thin orchestrator that delegates the actual work to the core services.
Rule alignment: R28 (Config-driven), R32 (Smart-skip)
"""
from __future__ import annotations
import logging
import re
import shutil
import sys
import tempfile
import json
from pathlib import Path
from typing import Any, Iterable
from cf2.core.services.tts_service import TTSService
from cf2.core.services.audio_service import AudioService
from cf2.core.services.ffmpeg_service import FFmpegService


logger = logging.getLogger(__name__)
DIALOGUE_RE = re.compile(r"^(Host|Guest):\s*(.+?)\s*$")

# -- XTTS global model cache (unchanged) --
_XTTS_MODEL = None
_XTTS_CONFIG = None
_XTTS_LATENTS = {}

# -- XTTS fail-fast state (NEW) --
_xtts_tested: bool = False
_xtts_ok: bool = False
_xtts_reason: str = ""


# ============================================================================
# XTTS Transformers Compatibility Patch
# ============================================================================
# Fixes: "Could not import module 'GPT2PreTrainedModel'"
# Cause: transformers >= 4.41 moved GPT2PreTrainedModel to a new path.
# Coqui XTTS internally calls importlib.import_module("transformers.GPT2PreTrainedModel")
# which fails on newer transformers. This patch registers the class at the
# expected path so XTTS can find it.
# ============================================================================

def _patch_xtts_transformers() -> bool:
    """
    Monkey-patch sys.modules so XTTS can find GPT2PreTrainedModel.
    Returns True if patch applied or not needed, False if unfixable.
    """
    # 1. Already available — no patch needed
    try:
        from transformers import GPT2PreTrainedModel  # noqa: F401
        return True
    except ImportError:
        pass

    # 2. Find in new location (transformers >= 4.41)
    try:
        from transformers.models.gpt2.modeling_gpt2 import (
            GPT2PreTrainedModel as _GPT2Class,
        )
    except ImportError:
        # 3. Alternate location
        try:
            from transformers.models.gpt2 import modeling_gpt2 as _gpt2_mod
            _GPT2Class = _gpt2_mod.GPT2PreTrainedModel
        except ImportError:
            return False

    # 4. Register at the path XTTS expects
    target = "transformers.GPT2PreTrainedModel"
    if target not in sys.modules:
        mod = type(sys)(target)
        mod.GPT2PreTrainedModel = _GPT2Class
        sys.modules[target] = mod

    # 5. Also attach to top-level transformers (some code paths use getattr)
    try:
        import transformers as _tf
        if not hasattr(_tf, "GPT2PreTrainedModel"):
            _tf.GPT2PreTrainedModel = _GPT2Class
    except Exception:
        pass

    return True


# ============================================================================
# XTTS Health Check (Fail-Fast — test ONCE, never retry per segment)
# ============================================================================

def _test_xtts_health(speaker_wav: str) -> bool:
    """
    Test XTTS availability once. Caches result in module-level state.
    Returns True if XTTS can synthesize, False if unavailable.

    This prevents wasting ~2s per guest segment on guaranteed failures.
    """
    global _xtts_tested, _xtts_ok, _xtts_reason

    # Return cached result if already tested
    if _xtts_tested:
        return _xtts_ok

    _xtts_tested = True

    # Step 1: Apply transformers patch
    if not _patch_xtts_transformers():
        _xtts_ok = False
        _xtts_reason = (
            "transformers patch failed — GPT2PreTrainedModel not found. "
            "Fix: pip install 'transformers<4.41' or check transformers version"
        )
        return False

    # Step 2: Check speaker WAV exists
    if not speaker_wav or not Path(speaker_wav).exists():
        _xtts_ok = False
        _xtts_reason = f"Speaker WAV not found: {speaker_wav}"
        return False

    # Step 3: Try actual model load (the real test)
    try:
        import torch  # noqa: F401
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        model_dir = Path("models/xtts")

        # Validate model files exist
        for f in ("config.json", "model.pth"):
            if not (model_dir / f).exists():
                _xtts_ok = False
                _xtts_reason = f"Missing XTTS file: {model_dir / f}"
                return False

        config = XttsConfig()
        config.load_json(str(model_dir / "config.json"))
        model = Xtts.init_from_config(config)
        model.load_checkpoint(config, checkpoint_dir=str(model_dir), eval=True)
        model.cpu()

        # Cache the loaded model for immediate use by _synthesize_xtts
        global _XTTS_MODEL, _XTTS_CONFIG
        _XTTS_MODEL = model
        _XTTS_CONFIG = config

        _xtts_ok = True
        _xtts_reason = "ok"
        logger.info("[XTTS] health check PASSED — model loaded and ready")
        return True

    except Exception as e:
        _xtts_ok = False
        _xtts_reason = str(e)
        logger.error("[XTTS] health check FAILED: %s", e)
        return False


# ============================================================================
# Public Entry
# ============================================================================

def run(
    script_path: str,
    output_path: str,
    voice_host: str,
    voice_guest: str,
    inputs: dict,
    fmt: str = "HD",
) -> str:
    src = Path(script_path)
    dst = Path(output_path)

    if dst.exists() and dst.stat().st_size > 1000:
        return f"⏭️ Skipped — audio already exists: {dst}"
    if not src.exists():
        raise FileNotFoundError(f"script not found: {src}")

    pause_ms = int(inputs.get("prodcast_pause_between_lines_ms", 350))
    bitrate = str(inputs.get("prodcast_audio_bitrate", "128k"))
    engine = str(inputs.get("prodcast_tts_engine", "edge")).lower()
    if engine in ("edge-tts", "edgetts"):
        engine = "edge"

    text = src.read_text(encoding="utf-8")
    segments = list(_parse_segments(text, voice_host, voice_guest))
    if not segments:
        raise RuntimeError(f"no Host:/Guest: lines found in {src.name}")

    pcfg = inputs.get("prodcast_config", {})
    speeds = pcfg.get("audio_speed", {})
    audio_speed = (
        speeds.get(fmt, speeds.get("default", 1.0))
        if isinstance(speeds, dict)
        else float(speeds)
    )
    rate_pct = _speed_to_rate_pct(audio_speed)

    logger.info(
        "[ProdcastVoice] %d segments, host=%s, guest=%s, rate=%+d%%, engine=%s, fmt=%s",
        len(segments), voice_host, voice_guest, rate_pct, engine, fmt,
    )

    # ── XTTS fail-fast: test ONCE before the segment loop ─────────────────
    needs_xtts = any(
        isinstance(v, str) and v.startswith("xtts:")
        for v, _ in segments
    )

    xtts_ok = True
    if needs_xtts:
        # Find speaker_wav from the first xtts segment
        for v, _ in segments:
            if isinstance(v, str) and v.startswith("xtts:"):
                sw = v.split("xtts:", 1)[1].strip()
                xtts_ok = _test_xtts_health(sw)
                break

        if not xtts_ok:
            logger.warning(
                "[ProdcastVoice] XTTS unavailable: %s", _xtts_reason
            )
            logger.warning(
                "[ProdcastVoice] All guest segments will use host voice fallback"
            )

    # ── Generate segments ─────────────────────────────────────────────────
    tts = TTSService()
    audio = AudioService()
    tmp_dir = Path(tempfile.mkdtemp(prefix="prodcast_tts_"))
    seg_files: list[str] = []
    seg_meta: list[dict] = []

    try:
        total = len(segments)
        seg_idx = 0
        for i, (voice, line) in enumerate(segments):
            seg_path = tmp_dir / f"seg_{i:04d}.mp3"
            ok = False
            logger.info("[ProdcastVoice] segment %d/%d", i + 1, total)

            try:
                # --- voice routing with fail-fast fallback ---
                if isinstance(voice, str) and voice.startswith("xtts:"):
                    if xtts_ok:
                        # XTTS available — try it
                        speaker_wav = voice.split("xtts:", 1)[1].strip()
                        ok = _synthesize_xtts(
                            tts, text=line,
                            output_path=str(seg_path),
                            speaker_wav=speaker_wav,
                        )
                        if not ok:
                            # First real failure — kill XTTS permanently
                            xtts_ok = False
                            logger.warning(
                                "[ProdcastVoice] XTTS failed at seg %d/%d — "
                                "disabling for remaining segments", i + 1, total
                            )
                            ok = tts.generate_edge(
                                text=line, output_path=str(seg_path),
                                voice=voice_host, rate=rate_pct, timeout=120,
                            )
                    else:
                        # XTTS already dead — instant fallback, zero waste
                        ok = tts.generate_edge(
                            text=line, output_path=str(seg_path),
                            voice=voice_host, rate=rate_pct, timeout=120,
                        )
                else:
                    ok = tts.generate_edge(
                        text=line, output_path=str(seg_path),
                        voice=voice, rate=rate_pct, timeout=120,
                    )
            except Exception as e:
                logger.error(
                    "[ProdcastVoice] exception seg %d/%d (%s): %s",
                    i + 1, total, voice, e, exc_info=False,
                )
                try:
                    ok = tts.generate_edge(
                        text=line, output_path=str(seg_path),
                        voice=voice_host, rate=rate_pct, timeout=120,
                    )
                except Exception:
                    ok = False

            if not ok:
                logger.warning("[ProdcastVoice] segment %d/%d FAILED — skipping", i + 1, total)
                continue

            dur = FFmpegService.get_duration(str(seg_path))
            speaker = "Host" if voice == voice_host else "Guest"
            seg_meta.append({
                "index": seg_idx, "speaker": speaker, "duration": dur,
            })
            seg_files.append(str(seg_path))
            seg_idx += 1

        if not seg_files:
            raise RuntimeError("all TTS segments failed")

        playlist = _build_playlist(
            seg_files=seg_files, audio=audio,
            tmp_dir=tmp_dir, pause_ms=pause_ms,
        )
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.unlink()

        ok = FFmpegService.concat_mp3_safe(
            input_paths=playlist, output_path=str(dst), bitrate=bitrate,
            logger=lambda msg: logger.info("[ProdcastVoice] %s", msg),
        )
        if not ok:
            raise RuntimeError("FFmpegService.concat_mp3_safe failed")
        if not dst.exists() or dst.stat().st_size == 0:
            raise RuntimeError(f"audio not produced at {dst}")

        sidecar = dst.with_suffix(".segments.json")
        with open(sidecar, "w") as f:
            json.dump(
                {"segments": seg_meta, "pause_s": pause_ms / 1000.0, "fmt": fmt},
                f, indent=2,
            )
        logger.info(
            "[ProdcastVoice] %s written (%d entries)",
            sidecar.name, len(seg_meta),
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    size_kb = dst.stat().st_size / 1024
    return f"✅ Audio generated: {dst} ({size_kb:.1f} KB)"


# ============================================================================
# XTTS Synthesis (unchanged logic, added patch safety net)
# ============================================================================

def _synthesize_xtts(
    tts_service, text: str, output_path: str, speaker_wav: str,
) -> bool:
    """XTTS voice clone with auto-split — saves direct MP3, never raises."""

    # Safety net: re-apply patch before any TTS imports
    _patch_xtts_transformers()

    try:
        import torch
        import torchaudio
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        if not Path(speaker_wav).exists():
            logger.error("[XTTS] speaker wav not found: %s", speaker_wav)
            return False

        # --- split long text ---
        def split_text(t, max_chars=240):
            sentences = re.split(r'(?<=[.!?])\s+', t.strip())
            chunks, cur = [], ""
            for s in sentences:
                if len(cur) + len(s) + 1 <= max_chars:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        chunks.append(cur)
                    if len(s) > max_chars:
                        for i in range(0, len(s), max_chars):
                            chunks.append(s[i:i + max_chars])
                        cur = ""
                    else:
                        cur = s
            if cur:
                chunks.append(cur)
            return chunks or [t[:max_chars]]

        chunks = split_text(text)

        # --- load model (cached after first call or by health check) ---
        global _XTTS_MODEL, _XTTS_CONFIG
        try:
            _XTTS_MODEL
        except NameError:
            _XTTS_MODEL = None

        if _XTTS_MODEL is None:
            model_dir = Path("models/xtts")
            _XTTS_CONFIG = XttsConfig()
            _XTTS_CONFIG.load_json(str(model_dir / "config.json"))
            _XTTS_MODEL = Xtts.init_from_config(_XTTS_CONFIG)
            _XTTS_MODEL.load_checkpoint(
                _XTTS_CONFIG, checkpoint_dir=str(model_dir), eval=True,
            )
            _XTTS_MODEL.cpu()
            logger.info("[XTTS] model loaded (CPU)")

        if speaker_wav not in _XTTS_LATENTS:
            logger.info("[XTTS] computing latents for %s (once)", speaker_wav)
            _XTTS_LATENTS[speaker_wav] = _XTTS_MODEL.get_conditioning_latents(
                audio_path=[speaker_wav],
                gpt_cond_len=15,
                max_ref_length=30,
            )
        gpt_cond, speaker_emb = _XTTS_LATENTS[speaker_wav]

        wavs = []
        for chunk in chunks:
            out = _XTTS_MODEL.inference(
                text=chunk, language="en",
                gpt_cond_latent=gpt_cond,
                speaker_embedding=speaker_emb,
                temperature=0.3,
                speed=1.1,
            )
            wavs.append(torch.tensor(out["wav"]))

        full_wav = torch.cat(wavs) if len(wavs) > 1 else wavs[0]
        torchaudio.save(output_path, full_wav.unsqueeze(0), 24000, format="mp3")
        return True

    except Exception as e:
        logger.error("[XTTS] synthesis failed: %s", e, exc_info=False)
        return False


# ============================================================================
# Helpers (unchanged)
# ============================================================================

def _parse_segments(
    text: str, voice_host: str, voice_guest: str,
) -> Iterable[tuple[str, str]]:
    voice_for = {"Host": voice_host, "Guest": voice_guest}
    current_voice: str | None = None
    current_buf: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = DIALOGUE_RE.match(line)
        if m:
            if current_voice is not None and current_buf:
                yield current_voice, " ".join(current_buf).strip()
            speaker, body = m.group(1), m.group(2)
            current_voice = voice_for[speaker]
            current_buf = [body]
        else:
            if current_voice is not None:
                current_buf.append(line)
    if current_voice is not None and current_buf:
        yield current_voice, " ".join(current_buf).strip()


def _speed_to_rate_pct(speed: Any) -> int:
    if speed is None:
        return 0
    if isinstance(speed, str):
        m = re.fullmatch(r"([+-]?)(\d+)%", speed.strip())
        if m:
            return int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
        try:
            speed = float(speed)
        except ValueError:
            return 0
    try:
        pct = int(round((float(speed) - 1.0) * 100))
    except (TypeError, ValueError):
        return 0
    return max(-50, min(pct, 100))


def _build_playlist(
    seg_files: list[str], audio: AudioService, tmp_dir: Path, pause_ms: int,
) -> list[str]:
    if pause_ms <= 0 or len(seg_files) < 2:
        return list(seg_files)
    silence = tmp_dir / "_silence.mp3"
    duration = pause_ms / 1000.0
    if not audio.create_silence(str(silence), duration=duration):
        logger.warning(
            "[ProdcastVoice] silence track failed — concatenating without pauses"
        )
        return list(seg_files)
    playlist: list[str] = []
    for i, seg in enumerate(seg_files):
        playlist.append(seg)
        if i < len(seg_files) - 1:
            playlist.append(str(silence))
    return playlist
