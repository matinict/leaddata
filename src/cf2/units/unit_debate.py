from __future__ import annotations

"""
unit_dubbing.py — Unit-Dubbing Orchestrator (CF2 Compliant)
...
"""

# ── FIX 1: Add missing hashlib import ────────────────────────────────────────
import hashlib
# ── FIX 2: Set PaddlePaddle PIR flags HERE, at module load time,
#    BEFORE any paddle/paddleocr code can be imported anywhere in the process.
import os
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_enable_pir_in_executor"] = "0"
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_mkldnn_bfloat16"] = "0"
# ─────────────────────────────────────────────────────────────────────────────

import json
import logging
import shutil
import traceback
from pathlib import Path
from typing import Any, Optional

import torch

from cf2.core.services.tts_service import TTSService
from cf2.core.services.audio_service import AudioService
from cf2.core.services.ffmpeg_service import FFmpegService
from cf2.core.services.crop_service import CropService
from cf2.meta import (
    load_meta, save_meta, mark_unit,
    mark_subtask, should_skip_dubbing_stage, should_skip
)

logger = logging.getLogger(__name__)

MIN_AUDIO_BYTES = 1_000
MIN_VIDEO_BYTES = 500_000

DUBBING_STAGES = [
    "transcribe",
    "screen_ocr",
    "merge_context",
    "synthesize",
    "sync",
    "merge",
    "hologram",
    "crop",
]


def _log(msg: str):
    print(f"[Unit-Dubbing] {msg}")


def _paths(workspace: Path) -> dict:
    d = workspace / "dubbing"
    d.mkdir(parents=True, exist_ok=True)
    return {
        "dir":              d,
        "script":           d / "script.txt",
        "screen_ocr":       d / "screen_ocr.txt",
        "enhanced_script":  d / "enhanced_script.txt",
        "merge_context":    d / "merged_context.json",
        "merge_hash":       d / "merge_hash.txt",
        "dubbed":           d / "dubbed.mp3",
        "synced":           d / "dubbed_synced.mp3",
        "final":            d / "dubbed_final.mp4",
        "holo":             d / "dubbed_holo.mp4",
        "meta_sidecar":     d / "dubbing_meta.json",
    }


def _save_sidecar(p: dict, dub_cfg: dict):
    """Progressively save/update sidecar metadata."""
    fmt_cfg = dub_cfg.get("video_formats", {})
    p["meta_sidecar"].write_text(json.dumps({
        "source_video": dub_cfg.get("source_video", ""),
        "tts_engine":   dub_cfg.get("tts_engine", "xtts"),
        "language":     dub_cfg.get("voice_clone_config", {}).get("language", "en"),
        "hologram":     dub_cfg.get("hologram", {}).get("enabled", False),
        "formats":      list(fmt_cfg.keys()),
        "final":        str(p["final"]) if p["final"].exists() else None,
    }, indent=2), encoding="utf-8")


def _invalidate_downstream(workspace: Path, failed_stage: str):
    """Reset all stages AFTER the failed stage to pending."""
    if failed_stage not in DUBBING_STAGES:
        _log(f"⚠️ Unknown stage '{failed_stage}' — skipping invalidation")
        return
    start_idx = DUBBING_STAGES.index(failed_stage) + 1
    for stage in DUBBING_STAGES[start_idx:]:
        mark_subtask(workspace, "Unit-Dubbing", stage, "pending")


# ══════════════════════════════════════════════════════════════════════════
# subUnitTranscribe
# ══════════════════════════════════════════════════════════════════════════

def _transcribe(
    video_path: str, script_path: Path,
    cfg: dict, workspace: Path, force: bool
) -> bool:
    if should_skip_dubbing_stage(workspace, "transcribe", force):
        _log(f"⏭️ Transcribe skipped (verified): {script_path.name}")
        return True
    try:
        import whisper
        model_size = cfg.get("whisper_model", "base")
        _log(f"🎙️ Whisper transcribing ({model_size}): {Path(video_path).name}")
        model  = whisper.load_model(model_size)
        result = model.transcribe(video_path, fp16=False)
        script_path.write_text(result["text"].strip(), encoding="utf-8")
        _log(f"✅ Transcript saved: {script_path.name} ({len(result['text'])} chars)")
        mark_subtask(workspace, "Unit-Dubbing", "transcribe", "done")
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return True
    except Exception as e:
        _log(f"❌ Transcribe failed: {e}")
        mark_subtask(workspace, "Unit-Dubbing", "transcribe", "failed")
        _invalidate_downstream(workspace, "transcribe")
        return False


# ══════════════════════════════════════════════════════════════════════════
# subUnitScreenOCR
# ══════════════════════════════════════════════════════════════════════════

def _screen_ocr(
    video_path: str, ocr_path: Path,
    cfg: dict, workspace: Path, force: bool
) -> bool:
    """Extract visible code/text from video frames using OCR."""
    if should_skip_dubbing_stage(workspace, "screen_ocr", force):
        _log(f"⏭️ Screen OCR skipped (verified): {ocr_path.name}")
        return True

    ocr_cfg = cfg.get("screen_ocr", {})

    if not ocr_cfg.get("enabled", True):
        _log("⏭️ Screen OCR disabled in config")
        ocr_path.write_text("[OCR_DISABLED]", encoding="utf-8")
        mark_subtask(workspace, "Unit-Dubbing", "screen_ocr", "done")
        return True

    try:
        from cf2.core.services.screen_ocr_service import ScreenOCRService
    except ImportError:
        _log("⏭️ PaddleOCR not installed")
        ocr_path.write_text("[OCR_FAILED: paddleocr_not_installed]", encoding="utf-8")
        mark_subtask(workspace, "Unit-Dubbing", "screen_ocr", "done")
        return True

    try:
        # FIX: Pass all supported config parameters from schema
        ocr_svc = ScreenOCRService(
            base_fps=ocr_cfg.get("fps", 0.5),
            confidence_threshold=ocr_cfg.get("confidence_threshold", 0.70),
            code_confidence_threshold=ocr_cfg.get("code_confidence_threshold", 0.55),
            max_frames=ocr_cfg.get("max_frames", 5),
            lang=ocr_cfg.get("lang", "en"),
        )

        _log(f"🔍 Screen OCR extracting: {Path(video_path).name}")
        text = ocr_svc.extract(
            video_path=video_path,
            output_dir=ocr_path.parent,
            cleanup_frames=ocr_cfg.get("cleanup_frames", True),
        )

        if text.strip():
            ocr_path.write_text(text, encoding="utf-8")
            _log(f"✅ Screen OCR saved: {ocr_path.name} ({len(text)} chars)")
        else:
            ocr_path.write_text("[NO_TEXT_DETECTED]", encoding="utf-8")
            _log("⚠️ Screen OCR: no text detected in video")

        mark_subtask(workspace, "Unit-Dubbing", "screen_ocr", "done")
        return True

    except Exception as e:
        _log(f"⚠️ Screen OCR failed: {e}")
        ocr_path.write_text(f"[OCR_FAILED: {str(e)[:100]}]", encoding="utf-8")
        mark_subtask(workspace, "Unit-Dubbing", "screen_ocr", "done")
        return True


# ══════════════════════════════════════════════════════════════════════════
# subUnitMergeContext
# ══════════════════════════════════════════════════════════════════════════

def _save_merge_metadata(
    context_path: Path,
    hash_path: Path,
    audio_text: str,
    screen_text: str,
    merged_text: str,
    merge_cfg: dict,
    language: str,
    content_hash: str,
    llm_model: Optional[str] = None,
) -> None:
    """Save structured merge metadata for analytics."""
    from datetime import datetime, timezone

    metadata = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hash": content_hash,
        "input": {
            "audio_chars": len(audio_text),
            "ocr_chars": len(screen_text.strip()) if not screen_text.startswith("[") else 0,
            "ocr_status": (
                "disabled" if screen_text.startswith("[OCR_DISABLED]") else
                "failed"   if screen_text.startswith("[OCR_FAILED]")   else
                "no_text"  if screen_text.startswith("[NO_TEXT")       else
                "empty"    if not screen_text.strip()                  else
                "success"
            ),
        },
        "config": {
            "style":       merge_cfg.get("style", "educational"),
            "language":    language,
            "temperature": merge_cfg.get("temperature", 0.7),
            "max_tokens":  merge_cfg.get("max_tokens", 4000),
        },
        "output": {
            "merged_chars":       len(merged_text),
            "compression_ratio":  round(len(merged_text) / max(len(audio_text), 1), 2),
        },
        "llm": {
            "model": llm_model or "unknown",
        },
    }

    context_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def _merge_context(
    script_path: Path,
    ocr_path: Path,
    enhanced_path: Path,
    hash_path: Path,
    context_path: Path,
    cfg: dict,
    inputs: dict,
    workspace: Path,
    force: bool
) -> bool:
    """Merge transcript + screen OCR into enhanced educational script."""
    if should_skip_dubbing_stage(workspace, "merge_context", force):
        _log(f"⏭️ Merge context skipped (verified): {enhanced_path.name}")
        return True

    merge_cfg = cfg.get("context_merge", {})
    if not merge_cfg.get("enabled", True):
        _log("⏭️ Context merge disabled — copying original script")
        shutil.copy2(str(script_path), str(enhanced_path))
        hash_path.write_text("", encoding="utf-8")
        _save_merge_metadata(
            context_path, hash_path,
            script_path.read_text(encoding="utf-8", errors="ignore"),
            ocr_path.read_text(encoding="utf-8", errors="ignore"),
            script_path.read_text(encoding="utf-8", errors="ignore"),
            merge_cfg,
            inputs.get("language", "en"),
            "disabled",
        )
        mark_subtask(workspace, "Unit-Dubbing", "merge_context", "done")
        return True

    audio_text  = script_path.read_text(encoding="utf-8", errors="ignore").strip()
    screen_text = ocr_path.read_text(encoding="utf-8", errors="ignore")

    ocr_is_empty = (
        not screen_text.strip()
        or screen_text.startswith("[OCR")
        or screen_text.startswith("[NO_TEXT")
    )

    if ocr_is_empty:
        _log(f"⏭️ No usable screen text ({screen_text[:50] if screen_text else 'empty'}) — using original script")
        shutil.copy2(str(script_path), str(enhanced_path))
        hash_path.write_text("", encoding="utf-8")
        _save_merge_metadata(
            context_path, hash_path,
            audio_text, screen_text, audio_text,
            merge_cfg, inputs.get("language", "en"), "skipped_no_ocr",
        )
        mark_subtask(workspace, "Unit-Dubbing", "merge_context", "done")
        return True

    if not audio_text.strip():
        _log("⏭️ No audio transcript — using screen text as script")
        enhanced_path.write_text(screen_text, encoding="utf-8")
        hash_path.write_text("", encoding="utf-8")
        _save_merge_metadata(
            context_path, hash_path,
            audio_text, screen_text, screen_text,
            merge_cfg, inputs.get("language", "en"), "skipped_no_audio",
        )
        mark_subtask(workspace, "Unit-Dubbing", "merge_context", "done")
        return True

    language = merge_cfg.get("language", inputs.get("language", "en"))

    merge_signature = json.dumps({
        "audio":       audio_text[:10000],
        "screen":      screen_text[:10000],
        "style":       merge_cfg.get("style", "educational"),
        "language":    language,
        "temperature": merge_cfg.get("temperature", 0.7),
        "max_tokens":  merge_cfg.get("max_tokens", 4000),
    }, sort_keys=True)

    content_hash = hashlib.md5(merge_signature.encode()).hexdigest()

    if not force and enhanced_path.exists() and hash_path.exists():
        old_hash = hash_path.read_text(encoding="utf-8").strip()
        if old_hash == content_hash:
            _log(f"⏭️ Merge context skipped (inputs unchanged, hash={content_hash[:12]}...)")
            return True

    llm_model = "unknown"

    try:
        from cf2.core.services.teaching_merge_service import TeachingMergeService

        merge_svc = TeachingMergeService(
            agent_name=merge_cfg.get("agent_name", "teaching_merge"),
            max_tokens=merge_cfg.get("max_tokens", 4000),
            temperature=merge_cfg.get("temperature", 0.7),
        )

        _log(f"🧠 AI merging transcript + screen OCR (style={merge_cfg.get('style', 'educational')})...")
        merged = merge_svc.merge(
            audio_text=audio_text,
            screen_text=screen_text,
            inputs=inputs,
            output_path=enhanced_path,
            style=merge_cfg.get("style", "educational"),
            language=language,
        )

        # FIX: Removed dead code trying to import get_agent_config.
        # TeachingMergeService handles LLM resolution internally now.
        try:
            llm_cfg = inputs.get("llm_config", {})
            if not llm_cfg and inputs.get("llmconf"):
                from cf2.core.llm_resolver import load_llm_config
                llm_cfg = load_llm_config(inputs.get("llmconf"))

            agent_cfg = llm_cfg.get("agents", {}).get("teaching_merge", {})
            tier_name = agent_cfg.get("tier", "default")
            tier_models = llm_cfg.get("tiers", {}).get(tier_name, {}).get("models", [])
            llm_model = tier_models[0] if tier_models else "unknown"
        except Exception:
            pass

        hash_path.write_text(content_hash, encoding="utf-8")
        _save_merge_metadata(
            context_path, hash_path,
            audio_text, screen_text, merged,
            merge_cfg, language, content_hash, llm_model,
        )
        _log(f"✅ Enhanced script saved: {enhanced_path.name} ({len(merged)} chars, hash={content_hash[:12]}...)")
        mark_subtask(workspace, "Unit-Dubbing", "merge_context", "done")
        return True

    except Exception as e:
        _log(f"⚠️ Context merge failed: {e}")
        _log("⏭️ Falling back to original transcript")
        shutil.copy2(str(script_path), str(enhanced_path))
        hash_path.write_text("", encoding="utf-8")
        _save_merge_metadata(
            context_path, hash_path,
            audio_text, screen_text,
            script_path.read_text(encoding="utf-8", errors="ignore"),
            merge_cfg, language, f"failed_{str(e)[:50]}",
        )
        mark_subtask(workspace, "Unit-Dubbing", "merge_context", "done")
        return True


# ══════════════════════════════════════════════════════════════════════════
# subUnitSynthesize
# ══════════════════════════════════════════════════════════════════════════

def _synthesize(
    script_path: Path, dubbed_path: Path,
    cfg: dict, workspace: Path, force: bool
) -> bool:
    if should_skip_dubbing_stage(workspace, "synthesize", force):
        _log(f"⏭️ Synthesize skipped (verified): {dubbed_path.name}")
        return True

    text = script_path.read_text(encoding="utf-8").strip()
    if not text:
        _log("❌ Script is empty — aborting synthesize")
        return False

    engine = cfg.get("tts_engine", "edge").lower()  # Default to edge to prevent XTTS trap

    # FIX: Infer clone status safely based on engine to avoid XTTS trap
    voice_clone_enabled = cfg.get("voice_clone_enabled", engine == "xtts")

    # Route to edge if explicitly requested or if XTTS clone is disabled
    use_edge = (engine == "edge" or not voice_clone_enabled)

    if use_edge:
        _log(f"🎤 Synthesizing via Edge TTS: {dubbed_path.name} (from {script_path.name})")
        ok = _synthesize_edge(text, dubbed_path, cfg)
    else:
        _log(f"🎤 Synthesizing via XTTS: {dubbed_path.name} (from {script_path.name})")
        ok = _synthesize_xtts(text, dubbed_path, cfg, workspace)

    if ok:
        mark_subtask(workspace, "Unit-Dubbing", "synthesize", "done")
    else:
        mark_subtask(workspace, "Unit-Dubbing", "synthesize", "failed")
        _invalidate_downstream(workspace, "synthesize")
    return ok


def _synthesize_xtts(
    text: str, out: Path, cfg: dict, workspace: Path
) -> bool:
    try:
        import torchaudio
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts

        vc      = cfg.get("voice_clone_config", {})
        spk_wav = vc.get("speaker_wav", "assets/voices/matin.wav")
        lang    = vc.get("language", "en")
        device  = vc.get("device", "cpu")

        if not Path(spk_wav).exists():
            _log(f"❌ Speaker WAV not found: {spk_wav}")
            return False

        model_dir = Path(cfg.get("xtts_model_dir", "models/xtts"))
        xtts_cfg  = XttsConfig()
        xtts_cfg.load_json(str(model_dir / "config.json"))
        model = Xtts.init_from_config(xtts_cfg)
        model.load_checkpoint(xtts_cfg, checkpoint_dir=str(model_dir), eval=True)
        model.to(device)
        _log(f"✅ XTTS model loaded ({device})")

        cache_dir     = workspace / "dubbing" / "xtts_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        gpt_cond_path = cache_dir / "gpt_cond.pt"
        spk_emb_path  = cache_dir / "spk_emb.pt"

        if gpt_cond_path.exists() and spk_emb_path.exists():
            _log("✅ Loading cached conditioning latents")
            gpt_cond = torch.load(gpt_cond_path)
            spk_emb  = torch.load(spk_emb_path)
        else:
            _log("🔄 Computing conditioning latents...")
            gpt_cond, spk_emb = model.get_conditioning_latents(
                audio_path=[spk_wav], gpt_cond_len=15, max_ref_length=30
            )
            torch.save(gpt_cond, gpt_cond_path)
            torch.save(spk_emb,  spk_emb_path)
            _log("✅ Latents cached for future runs")

        chunks  = TTSService().split_sentences(
            text, max_chars=int(cfg.get("chunk_max_chars", 240))
        )
        wavs    = []
        silence = torch.zeros(int(24000 * 0.12))

        for i, chunk in enumerate(chunks):
            _log(f"  chunk {i+1}/{len(chunks)}")
            out_chunk = model.inference(
                text=chunk, language=lang,
                gpt_cond_latent=gpt_cond,
                speaker_embedding=spk_emb,
                temperature=float(cfg.get("xtts_temperature", 0.25)),
                speed=float(cfg.get("xtts_speed", 0.78)),
            )
            wavs.append(torch.tensor(out_chunk["wav"]))
            if i < len(chunks) - 1:
                wavs.append(silence)

        full_wav = torch.cat(wavs) if len(wavs) > 1 else wavs[0]
        torchaudio.save(str(out), full_wav.unsqueeze(0), 24000, format="mp3")
        _log(f"✅ XTTS dubbed: {out.name}")

        del model
        if device == "cuda":
            torch.cuda.empty_cache()

        return True

    except Exception as e:
        _log(f"❌ XTTS synthesis failed: {e}")
        return False


def _synthesize_edge(text: str, out: Path, cfg: dict) -> bool:
    # FIX: Clean config lookup for voice name
    voice = cfg.get("tts_voice", "en-US-JennyNeural")
    ok = TTSService().generate_edge(
        text=text, output_path=str(out),
        voice=voice, rate=cfg.get("audio_speed"), timeout=180
    )
    if ok:
        _log(f"✅ Edge TTS dubbed: {out.name}")
    return ok


# ══════════════════════════════════════════════════════════════════════════
# subUnitSync / subUnitMerge / subUnitHologram / subUnitCrop
# ══════════════════════════════════════════════════════════════════════════

def _sync(
    dubbed_path: Path, synced_path: Path,
    video_path: str, cfg: dict,
    workspace: Path, force: bool
) -> bool:
    if should_skip_dubbing_stage(workspace, "sync", force):
        _log(f"⏭️ Sync skipped (verified): {synced_path.name}")
        return True

    if cfg.get("sync_mode", "atempo") == "none":
        shutil.copy2(str(dubbed_path), str(synced_path))
        _log("⏭️ Sync mode=none — copied as-is")
        mark_subtask(workspace, "Unit-Dubbing", "sync", "done")
        return True

    video_dur = FFmpegService.get_duration(video_path)
    if video_dur <= 0:
        shutil.copy2(str(dubbed_path), str(synced_path))
        mark_subtask(workspace, "Unit-Dubbing", "sync", "done")
        return True

    _log(f"🔄 atempo sync: video={video_dur:.2f}s")
    ok = AudioService().apply_atempo(str(dubbed_path), str(synced_path), video_dur)

    if ok:
        _log(f"✅ Synced: {synced_path.name}")
        mark_subtask(workspace, "Unit-Dubbing", "sync", "done")
    else:
        mark_subtask(workspace, "Unit-Dubbing", "sync", "failed")
        _invalidate_downstream(workspace, "sync")
    return ok


def _merge(
    video_path: str, synced_path: Path,
    final_path: Path, cfg: dict,
    workspace: Path, force: bool
) -> bool:
    if should_skip_dubbing_stage(workspace, "merge", force):
        _log(f"⏭️ Merge skipped (verified): {final_path.name}")
        return True

    import subprocess
    video_dur = FFmpegService.get_duration(video_path)
    audio_dur = FFmpegService.get_duration(str(synced_path))
    _log(f"🎬 Merging → v={video_dur:.1f}s a={audio_dur:.1f}s")

    # FIX: Build commands strictly ensuring options come BEFORE the output path
    if audio_dur > video_dur + 0.5:
        pad = round(audio_dur - video_dur, 3)
        _log(f" → extending video +{pad}s")
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", str(synced_path),
            "-filter_complex", f"[0:v]tpad=stop_mode=clone:stop_duration={pad}[v]",
            "-map", "[v]", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            str(final_path)
        ]
    else:
        # Base command for when audio is shorter or equal
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", str(synced_path),
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k"
        ]

        # Pad audio if video is longer (insert -af strictly before output path)
        if video_dur > audio_dur + 0.2:
            pad = round(video_dur - audio_dur, 3)
            cmd.extend(["-af", f"apad=pad_dur={pad}"])
            _log(f" → padding audio +{pad}s")

        cmd.append(str(final_path))

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        size_kb = final_path.stat().st_size // 1024
        _log(f"✅ Final: {final_path.name} ({size_kb} KB)")
        mark_subtask(workspace, "Unit-Dubbing", "merge", "done")
        return True
    except subprocess.CalledProcessError as e:
        last = e.stderr.splitlines()[-1] if e.stderr else "unknown"
        _log(f"❌ Merge failed: {last}")
        mark_subtask(workspace, "Unit-Dubbing", "merge", "failed")
        _invalidate_downstream(workspace, "merge")
        return False


def _hologram(
    final_path: Path, holo_path: Path,
    topic_slug: str, cfg: dict,
    workspace: Path, force: bool
) -> bool:
    holo_cfg = cfg.get("hologram", {})

    if not holo_cfg.get("enabled", False):
        _log("⏭️ Hologram disabled — marking done")
        mark_subtask(workspace, "Unit-Dubbing", "hologram", "done")
        return True

    if should_skip_dubbing_stage(workspace, "hologram", force):
        _log(f"⏭️ Hologram skipped (verified): {holo_path.name}")
        return True

    try:
        from cf2.core.services.hologram import HologramService
        svc = HologramService()
        svc.prepare(topic_slug=topic_slug, holo_config={
            **holo_cfg,
            "sources": [{"id": topic_slug, "type": "local", "path": str(final_path)}],
        })
        resolved = svc.resolve(topic_slug=topic_slug, source_id=topic_slug)
        if resolved and Path(resolved).exists():
            shutil.copy2(str(resolved), str(holo_path))
            _log(f"✅ Hologram: {holo_path.name}")
            mark_subtask(workspace, "Unit-Dubbing", "hologram", "done")
            return True

        _log("⚠️ Hologram resolve returned None")
        mark_subtask(workspace, "Unit-Dubbing", "hologram", "failed")
        _invalidate_downstream(workspace, "hologram")
        return False

    except Exception as e:
        _log(f"❌ Hologram failed: {e}")
        mark_subtask(workspace, "Unit-Dubbing", "hologram", "failed")
        _invalidate_downstream(workspace, "hologram")
        return False


def _crop(
    p: dict, dub_cfg: dict,
    topic_slug: str, inputs: dict, workspace: Path, force: bool
) -> None:
    if should_skip_dubbing_stage(workspace, "crop", force):
        _log("⏭️ Crop skipped (verified)")
        return

    fmt_cfg = dub_cfg.get("video_formats", {})
    if not fmt_cfg:
        _log("⏭️ No video_formats configured — crop skipped")
        mark_subtask(workspace, "Unit-Dubbing", "crop", "done")
        return

    holo_enabled = dub_cfg.get("hologram", {}).get("enabled", False)
    source_for_crop = (
        str(p["holo"])
        if holo_enabled
        and p["holo"].exists()
        and p["holo"].stat().st_size > MIN_VIDEO_BYTES
        else str(p["final"])
    )

    if not Path(source_for_crop).exists():
        _log(f"❌ CRITICAL: Crop source missing: {source_for_crop}")
        mark_subtask(workspace, "Unit-Dubbing", "crop", "failed")
        return

    _log(f"✂️ Crop source: {Path(source_for_crop).name}")

    # FIX: Pull channel from top-level inputs if missing in dub_cfg
    channel = dub_cfg.get("channel", inputs.get("channel", "@PlayOwnAi"))

    results = CropService(logger=_log).process_all(
        source_video=source_for_crop,
        video_formats_cfg=fmt_cfg,
        output_dir=str(p["dir"]),
        topic=topic_slug,
        channel=channel,
    )

    failed = False
    for fmt, out in results.items():
        if out:
            _log(f"✅ Format ready: {fmt} → {Path(out).name}")
        else:
            _log(f"⚠️ Format failed: {fmt}")
            failed = True

    mark_subtask(
        workspace, "Unit-Dubbing", "crop",
        "failed" if failed else "done"
    )


# ══════════════════════════════════════════════════════════════════════════
# Public Entry Point
# ══════════════════════════════════════════════════════════════════════════

def run(topic: str, workspace: Path, inputs: dict[str, Any], force: bool = False) -> str:
    """Unit entry point. Called by executor.py which already holds the lock."""
    if not inputs.get("Unit-Dubbing", False):
        _log("⏭️ Unit-Dubbing disabled — skipping.")
        return "disabled"

    if should_skip(workspace, "Unit-Dubbing", force, inputs):
        _log("⏭️ Already done (meta verified) — skipping.")
        return "done"

    dub_cfg    = inputs.get("dubbing_config", {})
    video_path = dub_cfg.get("source_video", "")

    if not video_path or not Path(video_path).exists():
        _log(f"❌ source_video not found: {video_path}")
        return "failed"

    p          = _paths(workspace)
    topic_slug = inputs.get("topic_slug", workspace.name)

    meta = load_meta(workspace)
    meta.setdefault("status", {})["Unit-Dubbing"] = "running"
    save_meta(workspace, meta)

    try:
        provided = dub_cfg.get("script_path", "")
        if provided and Path(provided).exists():
            if not p["script"].exists() or p["script"].stat().st_size <= 10:
                shutil.copy2(provided, str(p["script"]))
                _log(f"📄 Using provided script: {provided}")
            mark_subtask(workspace, "Unit-Dubbing", "transcribe", "done")
            _log(f"⏭️ Transcribe skipped (provided): {p['script'].name}")
        else:
            if not _transcribe(video_path, p["script"], dub_cfg, workspace, force):
                return _fail(workspace, meta, "transcribe failed", inputs)

        _screen_ocr(video_path, p["screen_ocr"], dub_cfg, workspace, force)

        if not _merge_context(
            p["script"], p["screen_ocr"], p["enhanced_script"],
            p["merge_hash"], p["merge_context"],
            dub_cfg, inputs, workspace, force
        ):
            _log("⚠️ Context merge failed — using original script")

        synth_script = (
            p["enhanced_script"]
            if p["enhanced_script"].exists()
            and p["enhanced_script"].stat().st_size > 100
            and not p["enhanced_script"].read_text(
                encoding="utf-8", errors="ignore"
            ).startswith("[")
            else p["script"]
        )

        if not _synthesize(synth_script, p["dubbed"], dub_cfg, workspace, force):
            return _fail(workspace, meta, "synthesize failed", inputs)
        _save_sidecar(p, dub_cfg)

        if not _sync(p["dubbed"], p["synced"], video_path, dub_cfg, workspace, force):
            return _fail(workspace, meta, "sync failed", inputs)
        _save_sidecar(p, dub_cfg)

        if not _merge(video_path, p["synced"], p["final"], dub_cfg, workspace, force):
            return _fail(workspace, meta, "merge failed", inputs)
        _save_sidecar(p, dub_cfg)

        if not _hologram(p["final"], p["holo"], topic_slug, dub_cfg, workspace, force):
            return _fail(workspace, meta, "hologram failed", inputs)
        _save_sidecar(p, dub_cfg)

        _crop(p, dub_cfg, topic_slug, inputs, workspace, force)
        _save_sidecar(p, dub_cfg)

        meta = load_meta(workspace)
        crop_status = meta.get("subtasks", {}).get("Unit-Dubbing", {}).get("crop")
        if crop_status == "failed":
            return _fail(workspace, meta, "crop stage failed", inputs)

        # FIX: Use mark_unit instead of manual dict editing so config hashes are correctly saved for Smart Skip
        mark_unit(workspace, "Unit-Dubbing", "done", inputs)
        _log("✅ Done.")
        return "done"

    except Exception as e:
        _log(f"❌ Exception: {e}\n{traceback.format_exc()}")
        return _fail(workspace, meta, str(e), inputs)


# FIX: Added inputs param to _fail so config hashes can be recorded on failure too
def _fail(workspace: Path, meta: dict, reason: str, inputs: dict = None) -> str:
    _log(f"❌ {reason}")
    mark_unit(workspace, "Unit-Dubbing", "failed", inputs)
    meta = load_meta(workspace) # Reload to get mark_unit's changes
    meta.setdefault("errors", {})["Unit-Dubbing"] = reason
    save_meta(workspace, meta)
    return "failed"
