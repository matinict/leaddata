"""
TTS Service — Unified TTS Engine
Handles gTTS, Edge TTS, Piper with consistent interface.
Smart skip: checks if output already exists before generating.
All config from inputs (no hardcoded values).

Rate handling (Edge TTS)
────────────────────────
edge_tts requires `rate` as a string formatted "+N%" or "-N%" (integer).
This service accepts ANY of these forms via the `rate` parameter:

    int    →  0, 10, -5     (interpreted directly as percent)
    float  →  1.0, 1.1, 0.9 (interpreted as speed multiplier; 1.1 → +10%)
    str    →  "+10%", "-5%" (passed through if valid; otherwise parsed)
    None   →                (rate parameter is omitted entirely)

Multipliers and percentages are disambiguated by type:
    - float values are always speed multipliers (centred on 1.0)
    - int values are always raw percentages (centred on 0)
"""
import os
import re
import asyncio
import threading
import shutil
import subprocess
from typing import Optional, List, Union
from pathlib import Path

# ── Optional TTS imports (graceful fallback) ───────────────────────────────
try:
    from gtts import gTTS
except ImportError:
    gTTS = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import piper
except ImportError:
    piper = None


RateLike = Union[int, float, str, None]


def _normalize_edge_rate(rate: RateLike) -> Optional[str]:
    """
    Convert any rate-like input to edge_tts's required format.

    Returns:
        - A string like "+10%", "-5%", "+0%" — to pass to edge_tts.Communicate.
        - None if the rate parameter should be OMITTED entirely (so edge_tts
          uses its default).

    Convention:
        int   → percentage as-is        (0, 10, -5)
        float → multiplier - 1, ×100    (1.0 → 0, 1.1 → 10, 0.9 → -10)
        str   → parsed if it matches "[+-]?N%", else parsed as float
        None  → return None (omit param)
    """
    if rate is None:
        return None

    if isinstance(rate, bool):  # bool is a subclass of int — guard separately
        return None

    if isinstance(rate, int):
        pct = rate
    elif isinstance(rate, float):
        # Float ≡ multiplier
        pct = int(round((rate - 1.0) * 100))
    elif isinstance(rate, str):
        s = rate.strip()
        if not s:
            return None
        m = re.fullmatch(r"([+-]?)(\d+)%", s)
        if m:
            sign, num = m.group(1), m.group(2)
            pct = int(num) * (-1 if sign == "-" else 1)
        else:
            try:
                pct = int(round((float(s) - 1.0) * 100))
            except ValueError:
                return None
    else:
        return None

    # Clamp to a sensible window
    pct = max(-50, min(pct, 100))
    return f"{pct:+d}%"


class TTSService:
    """Unified TTS service supporting multiple engines."""

    def __init__(self, logger=None):
        self.logger = logger or self._default_logger

    @staticmethod
    def _default_logger(msg: str):
        print(f"[TTS] {msg}")

    def split_sentences(self, text: str, max_chars: int = 150) -> List[str]:
        """Split text into <= max_chars chunks, respecting sentence boundaries."""
        if not text:
            return []

        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks: List[str] = []
        current_chunk = ""

        for sent in sentences:
            if not sent.strip():
                continue
            if len(sent) > max_chars:
                words = sent.split()
                for word in words:
                    if len(current_chunk) + len(word) + 1 > max_chars:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = word
                    else:
                        current_chunk += " " + word if current_chunk else word
            else:
                test_chunk = current_chunk + " " + sent if current_chunk else sent
                if len(test_chunk) <= max_chars:
                    current_chunk = test_chunk
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sent

        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks

    # ── gTTS ────────────────────────────────────────────────────────────────

    def generate_gtts(
        self,
        text: str,
        output_path: str,
        lang: str = "en",
        slow: bool = False,
    ) -> bool:
        output_path = str(output_path)
        if os.path.exists(output_path):
            self.logger(f"⏭️ gTTS skipped (exists): {os.path.basename(output_path)}")
            return True
        if not gTTS:
            self.logger("❌ gTTS not installed")
            return False
        try:
            self.logger(f"🎤 gTTS generating: {os.path.basename(output_path)}")
            gTTS(text=text, lang=lang, slow=slow).save(output_path)
            self.logger(f"✅ gTTS done: {os.path.basename(output_path)}")
            return True
        except Exception as e:
            self.logger(f"❌ gTTS failed: {e}")
            return False

    # ── Edge TTS ────────────────────────────────────────────────────────────

    async def generate_edge_async(
        self,
        text: str,
        voice: str = "en-US-AriaNeural",
        output_path: str = None,
        rate: RateLike = None,
    ) -> bool:
        """
        Async edge_tts call.

        `rate` accepts int/float/str/None — see _normalize_edge_rate.
        If the normalised value is None, the rate parameter is omitted.
        """
        output_path = str(output_path)

        if os.path.exists(output_path):
            self.logger(f"⏭️ Edge TTS skipped (exists): {os.path.basename(output_path)}")
            return True

        if not edge_tts:
            self.logger("❌ edge-tts not installed")
            return False

        try:
            self.logger(f"🎤 Edge TTS generating ({voice}): {os.path.basename(output_path)}")

            kwargs = {"text": text, "voice": voice}
            rate_str = _normalize_edge_rate(rate)
            if rate_str is not None and rate_str != "+0%":
                # +0% is the default; omit it to keep the request minimal.
                kwargs["rate"] = rate_str

            communicate = edge_tts.Communicate(**kwargs)
            await communicate.save(output_path)

            self.logger(f"✅ Edge TTS done: {os.path.basename(output_path)}")
            return True
        except Exception as e:
            self.logger(f"❌ Edge TTS failed: {e}")
            return False

    def generate_edge(
        self,
        text: str,
        output_path: str,
        voice: str = "en-US-AriaNeural",
        rate: RateLike = None,
        timeout: int = 120,
    ) -> bool:
        """Sync wrapper around generate_edge_async with a hard timeout."""
        output_path = str(output_path)
        if os.path.exists(output_path):
            self.logger(f"⏭️ Edge TTS skipped (exists): {os.path.basename(output_path)}")
            return True

        result = [False]

        def _run():
            try:
                result[0] = asyncio.run(
                    self.generate_edge_async(text, voice, output_path, rate)
                )
            except Exception as e:
                self.logger(f"❌ Edge TTS async failed: {e}")

        thread = threading.Thread(target=_run, daemon=False)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            self.logger(f"❌ Edge TTS timeout ({timeout}s)")
            return False

        return result[0]

    # ── Piper ───────────────────────────────────────────────────────────────

    def generate_piper(
        self,
        text: str,
        output_path: str,
        model_path: str,
        speed: float = 1.0,
        speaker: int = 0,
    ) -> bool:
        output_path = str(output_path)
        if os.path.exists(output_path):
            self.logger(f"⏭️ Piper skipped (exists): {os.path.basename(output_path)}")
            return True

        piper_binary = shutil.which("piper")
        if not piper_binary:
            self.logger("❌ Piper binary not found. Install with: sudo apt install piper")
            return False
        if not model_path or not os.path.exists(model_path):
            self.logger(f"❌ Piper model not found: {model_path}")
            return False

        try:
            self.logger(
                f"🎤 Piper generating: {os.path.basename(output_path)} "
                f"(model: {os.path.basename(model_path)})"
            )
            temp_wav = output_path.replace(".mp3", ".wav")
            length_scale = 1.0 / max(0.1, speed)

            cmd = [
                piper_binary,
                "--model", model_path,
                "--output_file", temp_wav,
                "--length_scale", str(length_scale),
            ]
            result = subprocess.run(
                cmd, input=text.encode("utf-8"), capture_output=True, check=False
            )
            if result.returncode != 0 or not os.path.exists(temp_wav):
                err = result.stderr.decode()[:200] if result.stderr else "Unknown error"
                self.logger(f"❌ Piper failed: {err}")
                return False

            ffmpeg_result = subprocess.run(
                ["ffmpeg", "-y", "-i", temp_wav, "-q:a", "2", output_path],
                capture_output=True, check=False,
            )
            try:
                os.remove(temp_wav)
            except OSError:
                pass

            if ffmpeg_result.returncode != 0 or not os.path.exists(output_path):
                self.logger("❌ FFmpeg conversion failed")
                return False

            size = os.path.getsize(output_path)
            self.logger(f"✅ Piper done: {os.path.basename(output_path)} ({size//1024} KB)")
            return True
        except Exception as e:
            self.logger(f"❌ Piper error: {e}")
            return False

    # ── Universal entry point ───────────────────────────────────────────────

    def generate(
        self,
        text: str,
        output_path: str,
        engine: str = "gtts",
        **engine_config,
    ) -> bool:
        engine = engine.lower()
        if engine == "gtts":
            return self.generate_gtts(
                text, output_path,
                lang=engine_config.get("lang", "en"),
                slow=engine_config.get("slow", False),
            )
        if engine == "edge":
            return self.generate_edge(
                text, output_path,
                voice=engine_config.get("voice", "en-US-AriaNeural"),
                rate=engine_config.get("rate"),
                timeout=engine_config.get("timeout", 120),
            )
        if engine == "piper":
            return self.generate_piper(
                text, output_path,
                model_path=engine_config.get("model_path", ""),
                speed=engine_config.get("speed", 1.0),
                speaker=engine_config.get("speaker", 0),
            )
        self.logger(f"❌ Unknown TTS engine: {engine}")
        return False
================================================================================
"""
hologram.py — CF2 Shared Hologram Service (Updated for Target UI)
==========================================================
Turns any archived / external video into a reusable, stylised
teaching-panel overlay consumable by any CF2 unit.

Types:
  1: Original Video Crop (Standard overlay)
  2: Screen OCR / Code Text (Auto-detect IDE/terminal, crop screen, apply sci-fi filter)

NEW: Panel Mode (mode="panel")
  - Rounded corner hologram panel with cyan glow border
  - Progress bar at bottom
  - REC indicator
  - Topic badge
  - Enhanced scanlines and flicker for code content

Runtime storage:
    .runtime/output/{TopicSlug}/_hologram/

Config location:
    input/profile/{channel}.json  →  "hologram": { "enabled": true, "type": 2, … }

Public API (two methods only):
    service.prepare(topic_slug, hologram_config)
    clip_path = service.resolve(topic_slug, source_id, segment_id)
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class SourceType(str, Enum):
    LOCAL   = "local"
    URL     = "url"
    YOUTUBE = "youtube"

class HologramType(int, Enum):
    CLIP_OVERLAY = 1  # Standard crop
    SCREEN_OCR   = 2  # Auto-detect IDE/Terminal screen

class HologramMode(str, Enum):
    FLOATING_SCREEN = "floating_screen"
    PROJECTOR       = "projector"
    GLASS_PANEL     = "glass_panel"
    PANEL           = "panel"  # NEW: Target UI style

class ClipType(str, Enum):
    CODE     = "code"
    TERMINAL = "terminal"
    DEMO     = "demo"
    OVERLAY  = "overlay"
    RAW      = "raw"


# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────

@dataclass
class HologramSource:
    id:          str
    type:        SourceType
    path:        str
    label:       str       = ""
    start_sec:   float     = 0.0
    end_sec:     Optional[float] = None
    segments:    list      = field(default_factory=list)

@dataclass
class ClipEntry:
    clip_id:    str
    source_id:  str
    segment_id: str
    clip_type:  ClipType
    filename:   str
    start_sec:  float
    end_sec:    float
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class HologramManifest:
    topic_slug:  str
    sources:     list       = field(default_factory=list)
    clips:       list       = field(default_factory=list)
    cache_state: dict       = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "HologramManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)


# ──────────────────────────────────────────────
# HologramService
# ──────────────────────────────────────────────

class HologramService:
    HOLOGRAM_DIR = "_hologram"

    def __init__(
        self,
        runtime_root:  Path | str = Path(".runtime/output"),
        assets_root:   Path | str = Path("assets"),
        ffmpeg_bin:    str  = "ffmpeg",
        ffprobe_bin:   str  = "ffprobe",
        yt_dlp_bin:    str  = "yt-dlp",
        default_mode:  HologramMode = HologramMode.PANEL,  # UPDATED: default to panel
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.assets_root  = Path(assets_root)
        self.ffmpeg_bin   = ffmpeg_bin
        self.ffprobe_bin  = ffprobe_bin
        self.yt_dlp_bin   = yt_dlp_bin
        self.default_mode = default_mode
        self.clip_speed   = 1.0

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def prepare(self, topic_slug: str, holo_config: dict) -> HologramManifest:
        mode_str = holo_config.get("mode", holo_config.get("default_style", "panel"))
        # Support "panel" mode
        try:
            mode = HologramMode(mode_str)
        except ValueError:
            mode = HologramMode.PANEL

        holo_type = HologramType(holo_config.get("type", 2))
        self.clip_speed = float(holo_config.get("clip_speed", 1.0))
        holo_size = holo_config.get("size", None)
        sources_cfg = holo_config.get("sources", [])

        hologram_dir = self._hologram_dir(topic_slug)
        self._ensure_dirs(hologram_dir)

        manifest = self._load_or_create_manifest(topic_slug, hologram_dir)

        for src_cfg in sources_cfg:
            source = self._parse_source_cfg(src_cfg)

            if self._is_cached(manifest, source):
                print(f"[Hologram] ⏭️  {source.id} cached — skipping")
                continue

            print(f"[Hologram] 📡 Preparing source: {source.id} ({source.type.value}, Type {holo_type.value})")

            try:
                local_path = self._resolve_source(source, hologram_dir)
            except Exception as e:
                print(f"[Hologram] ❌ Source resolve failed for {source.id}: {e}")
                continue

            normalized_path = self._normalize_source(local_path, hologram_dir, holo_size)

            if holo_type == HologramType.SCREEN_OCR:
                clips = self._extract_screen_content(source, normalized_path, hologram_dir)
            else:
                clips = self._extract_clips(source, normalized_path, hologram_dir)

            for clip in clips:
                self._build_hologram_overlay(clip, hologram_dir, mode)

            self._update_manifest(manifest, source, clips, hologram_dir)

        return manifest

    def resolve(self, topic_slug: str, source_id: str, segment_id: str = "") -> Optional[Path]:
        hologram_dir  = self._hologram_dir(topic_slug)
        manifest_path = hologram_dir / "manifest.json"

        if not manifest_path.exists():
            return None

        manifest = HologramManifest.load(manifest_path)

        for entry in manifest.clips:
            if entry["source_id"] == source_id:
                if segment_id and entry.get("segment_id") != segment_id:
                    continue
                render_path = hologram_dir / "renders" / f"holo_{entry['filename']}"
                if render_path.exists():
                    return render_path
                clip_path = hologram_dir / "clips" / entry["filename"]
                if clip_path.exists():
                    return clip_path

        return None

    # ──────────────────────────────────────────
    # Config parsing
    # ──────────────────────────────────────────

    def _parse_source_cfg(self, cfg: dict) -> HologramSource:
        segments = []
        for seg in cfg.get("clips", cfg.get("segments", [])):
            segments.append({
                "id":    seg.get("id", f"seg_{len(segments)}"),
                "start": seg.get("start", "00:00"),
                "end":   seg.get("end", "00:00"),
            })

        return HologramSource(
            id        = cfg.get("id", f"src_{hashlib.md5(str(cfg).encode()).hexdigest()[:8]}"),
            type      = SourceType(cfg.get("type", cfg.get("source_type", "local"))),
            path      = cfg.get("path", cfg.get("source_path", cfg.get("path_or_url", ""))),
            label     = cfg.get("label", ""),
            start_sec = self._parse_time(cfg.get("start_sec", cfg.get("start", 0))),
            end_sec   = self._parse_time(cfg["end_sec"]) if cfg.get("end_sec") else (
                        self._parse_time(cfg["end"]) if cfg.get("end") and not segments else None),
            segments  = segments,
        )

    @staticmethod
    def _parse_time(val) -> float:
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str) and ":" in val:
            parts = val.split(":")
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            if len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        try:
            return float(val)
        except (TypeError, ValueError):
            return 0.0

    # ──────────────────────────────────────────
    # Task A — Source Resolver
    # ──────────────────────────────────────────

    def _resolve_source(self, source: HologramSource, hologram_dir: Path) -> Path:
        source_dir = hologram_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        dest = source_dir / f"{source.id}_raw.mp4"

        if dest.exists() and dest.stat().st_size > 1000:
            return dest

        if source.type == SourceType.LOCAL:
            src = self.assets_root / source.path
            if not src.exists():
                src = Path(source.path)
            if not src.exists():
                raise FileNotFoundError(f"Local source not found: {source.path}")
            shutil.copy2(src, dest)
            print(f"[Hologram] 📁 Copied local: {src.name} → {dest.name}")

        elif source.type == SourceType.URL:
            r = subprocess.run(
                [self.ffmpeg_bin, "-y", "-i", source.path, "-c", "copy", str(dest)],
                capture_output=True, text=True, timeout=180,
            )
            if r.returncode != 0:
                import urllib.request
                urllib.request.urlretrieve(source.path, str(dest))

        elif source.type == SourceType.YOUTUBE:
            subprocess.run(
                [self.yt_dlp_bin, "--quiet", "--format", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
                 "--merge-output-format", "mp4", "--output", str(dest), source.path],
                check=True, timeout=300,
            )

        return dest

    # ──────────────────────────────────────────
    # Task B — Normalizer
    # ──────────────────────────────────────────

    def _normalize_source(self, raw_path: Path, hologram_dir: Path, holo_size: Optional[str] = None) -> Path:
        norm_dir = hologram_dir / "source"
        norm_dir.mkdir(parents=True, exist_ok=True)
        dest = norm_dir / f"{raw_path.stem}_norm.mp4"

        if dest.exists() and dest.stat().st_size > 1000:
            return dest

        src_w, src_h = 1920, 1080
        try:
            probe = subprocess.run(
                [self.ffprobe_bin, "-v", "quiet", "-print_format", "json", "-show_streams", str(raw_path)],
                capture_output=True, text=True, check=True, timeout=10,
            )
            streams = json.loads(probe.stdout).get("streams", [])
            for s in streams:
                if s.get("codec_type") == "video":
                    src_w = int(s.get("width", 1920))
                    src_h = int(s.get("height", 1080))
                    break
        except Exception:
            pass

        MAX_W, MAX_H = 3840, 2160
        nw, nh = min(src_w, MAX_W), min(src_h, MAX_H)

        needs_scale = (nw != src_w or nh != src_h)
        vf = (
            f"scale={nw}:{nh}:force_original_aspect_ratio=decrease,pad={nw}:{nh}:(ow-iw)/2:(oh-ih)/2:color=black,fps=30,format=yuv420p"
            if needs_scale else "fps=30,format=yuv420p"
        )

        cmd = [
            self.ffmpeg_bin, "-y", "-i", str(raw_path), "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-an", "-movflags", "+faststart", str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return raw_path

        print(f"[Hologram] ✅ Normalized: {dest.name} ({nw}x{nh}@30fps)")
        return dest

    # ──────────────────────────────────────────
    # Type 2: FFmpeg Native Screen Auto-Crop Extractor
    # ──────────────────────────────────────────

    def _detect_screen_crop_ffmpeg(self, video_path: Path, at_sec: float = 5.0) -> str:
        cmd = [
            self.ffmpeg_bin, "-y",
            "-ss", f"{at_sec:.2f}",
            "-i", str(video_path),
            "-vframes", "10",
            "-vf", "cropdetect=limit=0.1:round=2",
            "-f", "null", "-"
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)

        crop_values = None
        for line in r.stderr.splitlines():
            if "crop=" in line:
                idx = line.find("crop=")
                crop_str = line[idx:].strip()
                crop_values = crop_str.replace("crop=", "").split(":")

        if crop_values and len(crop_values) == 4:
            w, h, x, y = crop_values
            print(f"[Hologram] 🖥️  FFmpeg auto-detected screen bounds: {w}x{h} at x={x}, y={y}")
            return f"{w}:{h}:{x}:{y}"

        print("[Hologram] ⚠️ Could not auto-detect screen bounds. Defaulting to center 80%.")
        return "1536:864:192:108"

    def _extract_screen_content(self, source: HologramSource, normalized_path: Path, hologram_dir: Path) -> list[ClipEntry]:
        clips_dir = hologram_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        duration = self._probe_duration(normalized_path)
        if duration is None or duration < 1:
            return []

        clips: list[ClipEntry] = []

        if source.segments:
            for seg in source.segments:
                seg_id = seg["id"]
                t_start = self._parse_time(seg["start"])
                t_end = self._parse_time(seg["end"])
                if t_end <= t_start: continue

                crop_filter = self._detect_screen_crop_ffmpeg(normalized_path, at_sec=t_start + 1.0)

                filename = f"{source.id}_{seg_id}.mp4"
                out_path = clips_dir / filename

                if not out_path.exists() or out_path.stat().st_size < 1000:
                    self._ffmpeg_crop_and_cut(normalized_path, out_path, t_start, t_end, crop_filter, self.clip_speed)
                    speed_txt = f" [Speed: {self.clip_speed}x]" if self.clip_speed != 1.0 else ""
                    print(f"[Hologram] ✂️  Extracted Screen: {filename} ({t_start:.1f}s–{t_end:.1f}s){speed_txt}")

                clips.append(ClipEntry(
                    clip_id=f"{source.id}_{seg_id}", source_id=source.id,
                    segment_id=seg_id, clip_type=ClipType.CODE, filename=filename,
                    start_sec=t_start, end_sec=t_end,
                ))
        else:
            crop_filter = self._detect_screen_crop_ffmpeg(normalized_path)
            end = source.end_sec if source.end_sec else duration
            span = end - source.start_sec
            if span < 3: span = duration; source.start_sec = 0; end = duration

            # If it's the whole video, treat as one single CODE clip
            if span == duration:
                # FIX: Use source.id as segment_id so it matches the [HOLO:source_id] script tags!
                filename = f"{source.id}.mp4"
                out_path = clips_dir / filename
                if not out_path.exists() or out_path.stat().st_size < 1000:
                    self._ffmpeg_crop_and_cut(normalized_path, out_path, source.start_sec, end, crop_filter, self.clip_speed)
                    speed_txt = f" [Speed: {self.clip_speed}x]" if self.clip_speed != 1.0 else ""
                    print(f"[Hologram] ✂️  Extracted Screen: {filename} (Full Video){speed_txt}")
                clips.append(ClipEntry(
                    clip_id=f"{source.id}", source_id=source.id,
                    segment_id=source.id, clip_type=ClipType.CODE, filename=filename,
                    start_sec=source.start_sec, end_sec=end,
                ))
            else:
                third = span / 3
                for ct, seg_label, t_start, t_end in [
                    (ClipType.CODE, "code", source.start_sec, source.start_sec + third),
                    (ClipType.TERMINAL, "terminal", source.start_sec + third, source.start_sec + 2 * third),
                    (ClipType.DEMO, "demo", source.start_sec + 2*third, end)
                ]:
                    filename = f"{source.id}_{seg_label}.mp4"
                    out_path = clips_dir / filename
                    if not out_path.exists() or out_path.stat().st_size < 1000:
                        self._ffmpeg_crop_and_cut(normalized_path, out_path, t_start, t_end, crop_filter, self.clip_speed)
                    clips.append(ClipEntry(
                        clip_id=f"{source.id}_{seg_label}", source_id=source.id,
                        segment_id=seg_label, clip_type=ct, filename=filename,
                        start_sec=t_start, end_sec=t_end,
                    ))

        print(f"[Hologram] ✅ {len(clips)} screen clips extracted for {source.id}")
        return clips

    def _ffmpeg_crop_and_cut(self, src: Path, dest: Path, start: float, end: float, crop_filter: str, clip_speed: float = 1.0) -> None:
        vf_parts = [f"crop={crop_filter}"]
        if clip_speed and clip_speed != 1.0:
            vf_parts.append(f"setpts=PTS/{clip_speed:.2f}")
        vf = ",".join(vf_parts)

        cmd = [
            self.ffmpeg_bin, "-y",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(src),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-an",
            str(dest),
        ]
        # Increased timeout to 600s (10 mins) for full-video speed shifts
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(f"[Hologram] ⚠️ Screen Crop failed: {r.stderr[-200:]}")

    # ──────────────────────────────────────────
    # Type 1: Default Clip Extractor
    # ──────────────────────────────────────────

    def _extract_clips(self, source: HologramSource, normalized_path: Path, hologram_dir: Path) -> list[ClipEntry]:
        clips_dir = hologram_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)

        duration = self._probe_duration(normalized_path)
        if duration is None or duration < 1:
            return []

        clips: list[ClipEntry] = []

        if source.segments:
            for seg in source.segments:
                seg_id = seg["id"]
                t_start = self._parse_time(seg["start"])
                t_end = self._parse_time(seg["end"])
                if t_end <= t_start: continue

                filename = f"{source.id}_{seg_id}.mp4"
                out_path = clips_dir / filename
                if not out_path.exists() or out_path.stat().st_size < 1000:
                    self._ffmpeg_cut(normalized_path, out_path, t_start, t_end)
                    print(f"[Hologram] ✂️  Extracted: {filename} ({t_start:.1f}s–{t_end:.1f}s)")

                seg_lower = seg_id.lower()
                ct = ClipType.CODE if "code" in seg_lower else ClipType.TERMINAL if "output" in seg_lower else ClipType.DEMO
                clips.append(ClipEntry(clip_id=f"{source.id}_{seg_id}", source_id=source.id, segment_id=seg_id, clip_type=ct, filename=filename, start_sec=t_start, end_sec=t_end))
        else:
            end = source.end_sec if source.end_sec else duration
            span = end - source.start_sec
            if span < 3: span = duration; source.start_sec = 0; end = duration
            third = span / 3
            for ct, seg_label, t_start, t_end in [
                (ClipType.CODE, "code", source.start_sec, source.start_sec + third),
                (ClipType.TERMINAL, "terminal", source.start_sec + third, source.start_sec + 2 * third),
                (ClipType.DEMO, "demo", source.start_sec + 2*third, end)
            ]:
                filename = f"{source.id}_{seg_label}.mp4"
                out_path = clips_dir / filename
                if not out_path.exists() or out_path.stat().st_size < 1000:
                    self._ffmpeg_cut(normalized_path, out_path, t_start, t_end)
                clips.append(ClipEntry(clip_id=f"{source.id}_{seg_label}", source_id=source.id, segment_id=seg_label, clip_type=ct, filename=filename, start_sec=t_start, end_sec=t_end))

        print(f"[Hologram] ✅ {len(clips)} clips extracted for {source.id}")
        return clips

    def _ffmpeg_cut(self, src: Path, dest: Path, start: float, end: float) -> None:
        cmd = [
            self.ffmpeg_bin, "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-an", str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print(f"[Hologram] ⚠️ Cut failed: {r.stderr[-200:]}")

    def _probe_duration(self, path: Path) -> Optional[float]:
        try:
            result = subprocess.run(
                [self.ffprobe_bin, "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
                capture_output=True, text=True, check=True, timeout=10,
            )
            return float(json.loads(result.stdout)["format"]["duration"])
        except Exception:
            return None

    # ──────────────────────────────────────────
    # Task D — Hologram Builder (Render)
    # 7-Stage Sci-Fi Filter Pipeline + NEW Panel Mode
    # ──────────────────────────────────────────

    _SCANLINE_SPACING = {
        HologramMode.FLOATING_SCREEN: 4,
        HologramMode.PROJECTOR:       6,
        HologramMode.GLASS_PANEL:     8,
        HologramMode.PANEL:           3,  # NEW: Finer scanlines for code
    }


    def _build_hologram_overlay(self, clip: ClipEntry, hologram_dir: Path, mode: HologramMode) -> None:
        renders_dir = hologram_dir / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        src  = hologram_dir / "clips" / clip.filename
        dest = renders_dir / f"holo_{clip.filename}"

        if dest.exists() and dest.stat().st_size > 1000:
            return

        if not src.exists():
            return

        filter_graph = self._mode_filter(mode)

        # Use -filter_complex because the glow stage uses split/blend named links
        cmd = [
            self.ffmpeg_bin, "-y", "-i", str(src),
            "-filter_complex", filter_graph,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-an",  # CRITICAL: Drop audio to prevent packet errors
            "-movflags", "+faststart",
            str(dest),
        ]

        # Heavy filters (gblur, geq) on a full video can take 15-20 mins on CPU.
        # Timeout set to 1800 seconds (30 minutes).
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            print(f"[Hologram] ⚠️ Render timed out for {clip.filename} (heavy filters on long video).")
            r = None

        if r is None or r.returncode != 0:
            if r is not None:
                print(f"[Hologram] ⚠️ Render failed for {clip.filename}: {r.stderr[-200:]}")
            # Smart Fallback: Generate a clean, silent, looping clip so compositor never freezes
            print(f"[Hologram] 🔄 Applying fast fallback render for {clip.filename}...")
            fallback_cmd = [
                self.ffmpeg_bin, "-y",
                "-stream_loop", "-1", "-i", str(src),
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-vf", "curves=r='0 0 1 0.7':g='0 0 1 0.9':b='0 0 1 1.3',eq=brightness=0.08:saturation=1.2", # Fast blue tint
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(dest)
            ]
            subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=300)
        else:
            print(f"[Hologram] 🎨 Rendered: holo_{clip.filename} ({mode.value})")



    def _mode_filter(self, mode: HologramMode) -> str:
        """
        Build a multi-stage FFmpeg filter_complex graph that makes the clip
        look like a genuine hologram projection:

        ┌─ desaturate ─┬─ cyan tint ─┬─ edge glow ─┬─ scanlines ─┬─ shimmer ─┬─ vignette ─┬─ polish ─┐
        └──────────────┴─────────────┴─────────────┴─────────────┴───────────┴────────────┴──────────┘

        NEW: PANEL mode adds enhanced cyan glow, sharper scanlines, and code-optimized contrast
        """
        sl = self._SCANLINE_SPACING[mode.value]

        # ── 1. Desaturate (hue filter: keep luma, drain colour) ──────────
        desat = "hue=s=0.08"

        # ── 2. Cyan/blue tint ────────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            tint = "curves=r='0 0 0.7 0.45 1 0.55':g='0 0 0.5 0.65 1 0.85':b='0 0.15 0.5 0.80 1 1.0'"
        elif mode == HologramMode.PROJECTOR:
            tint = "curves=r='0 0 0.7 0.35 1 0.5':g='0 0 0.5 0.55 1 0.72':b='0 0.20 0.5 0.85 1 1.0'"
        elif mode == HologramMode.PANEL:
            # NEW: Enhanced cyan tint for code panels - brighter, more contrast
            tint = "curves=r='0 0 0.7 0.30 1 0.40':g='0 0 0.5 0.75 1 0.90':b='0 0.10 0.5 0.90 1 1.0',eq=contrast=1.15:brightness=0.02"
        else:  # GLASS_PANEL
            tint = "curves=r='0 0 0.7 0.55 1 0.65':g='0 0 0.5 0.70 1 0.88':b='0 0.10 0.5 0.78 1 0.95'"

        # ── 3. Edge / object glow ────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            glow_radius, glow_opacity = 18, 0.55
        elif mode == HologramMode.PROJECTOR:
            glow_radius, glow_opacity = 24, 0.45
        elif mode == HologramMode.PANEL:
            # NEW: Stronger glow for panel mode
            glow_radius, glow_opacity = 22, 0.65
        else:
            glow_radius, glow_opacity = 12, 0.35

        glow = (
            f"split[base][glw];"
            f"[glw]gblur=sigma={glow_radius},eq=brightness=0.08:contrast=1.1[gblurred];"
            f"[base][gblurred]blend=all_mode=screen:all_opacity={glow_opacity}"
        )

        # ── 4. Scanlines ─────────────────────────────────────────────────
        scanline_dark = 0.35
        if mode == HologramMode.PANEL:
            scanline_dark = 0.45  # NEW: More visible scanlines for panel

        scanlines = (
            f"geq="
            f"r='if(eq(mod(Y,{sl}),0),r(X,Y)*{scanline_dark},r(X,Y))':"
            f"g='if(eq(mod(Y,{sl}),0),g(X,Y)*{scanline_dark},g(X,Y))':"
            f"b='if(eq(mod(Y,{sl}),0),b(X,Y)*{scanline_dark},b(X,Y))'"
        )

        # ── 5. Flicker / shimmer ─────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            shimmer_amp, shimmer_freq = 0.06, 2.8
        elif mode == HologramMode.PROJECTOR:
            shimmer_amp, shimmer_freq = 0.04, 1.5
        elif mode == HologramMode.PANEL:
            # NEW: Subtle shimmer for panel mode (less distracting for code)
            shimmer_amp, shimmer_freq = 0.03, 1.8
        else:
            shimmer_amp, shimmer_freq = 0.03, 1.2

        shimmer = (
            f"geq="
            f"r='r(X,Y)*(1+{shimmer_amp}*sin({shimmer_freq}*PI*T))':"
            f"g='g(X,Y)*(1+{shimmer_amp}*sin({shimmer_freq}*PI*T))':"
            f"b='b(X,Y)*(1+{shimmer_amp}*sin({shimmer_freq}*PI*T))'"
        )

        # ── 6. Vignette ───────────────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            vignette = "vignette=PI/3.2:eval=frame"
        elif mode == HologramMode.PROJECTOR:
            vignette = "vignette=PI/2.5:eval=frame"
        elif mode == HologramMode.PANEL:
            # NEW: Lighter vignette for panel (keep edges readable)
            vignette = "vignette=PI/4.0:eval=frame"
        else:
            vignette = "vignette=PI/4.5:eval=frame"

        # ── 7. Final brightness / contrast polish ─────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            polish = "eq=brightness=0.04:contrast=1.12:saturation=1.15:gamma_b=1.08"
        elif mode == HologramMode.PROJECTOR:
            polish = "eq=brightness=0.02:contrast=1.08:saturation=1.10:gamma_b=1.05"
        elif mode == HologramMode.PANEL:
            # NEW: Sharper, brighter for code readability
            polish = "eq=brightness=0.03:contrast=1.18:saturation=1.20:gamma_b=1.10:gamma_g=0.95"
        else:
            polish = "eq=brightness=0.01:contrast=1.05:saturation=1.05:gamma_b=1.03"

        # ── Assemble ──────────────────────────────────────────────────────
        pre  = f"{desat},{tint}"
        post = f"{scanlines},{shimmer},{vignette},{polish},format=yuv420p"

        # Full chain: pre -> glow (with split/blend) -> post
        return f"{pre},{glow},{post}"


    # ──────────────────────────────────────────
    # Task E — Manifest Manager
    # ──────────────────────────────────────────

    def _load_or_create_manifest(self, topic_slug: str, hologram_dir: Path) -> HologramManifest:
        path = hologram_dir / "manifest.json"
        if path.exists():
            try: return HologramManifest.load(path)
            except Exception: pass
        return HologramManifest(topic_slug=topic_slug)

    def _update_manifest(self, manifest: HologramManifest, source: HologramSource, clips: list[ClipEntry], hologram_dir: Path) -> None:
        src_dict = {"id": source.id, "type": source.type.value, "path": source.path, "label": source.label}
        if src_dict not in manifest.sources:
            manifest.sources.append(src_dict)
        for clip in clips:
            manifest.clips.append(asdict(clip))
        manifest.cache_state[source.id] = {
            "key": self._cache_key(source),
            "cached_at": datetime.utcnow().isoformat(),
            "clip_count": len(clips),
        }
        manifest.save(hologram_dir / "manifest.json")

    def _is_cached(self, manifest: HologramManifest, source: HologramSource) -> bool:
        state = manifest.cache_state.get(source.id)
        if not state: return False
        return state.get("key") == self._cache_key(source)

    @staticmethod
    def _cache_key(source: HologramSource) -> str:
        raw = f"{source.id}|{source.path}|{source.start_sec}|{source.end_sec}"
        return hashlib.md5(raw.encode()).hexdigest()

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    def _hologram_dir(self, topic_slug: str) -> Path:
        return self.runtime_root / topic_slug / self.HOLOGRAM_DIR

    def _ensure_dirs(self, hologram_dir: Path) -> None:
        for sub in ("source", "clips", "renders", "cache"):
            (hologram_dir / sub).mkdir(parents=True, exist_ok=True)


def load_hologram_config(profile_path: Path) -> tuple[bool, dict]:
    if not profile_path.exists():
        return False, {}
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    holo_cfg = profile.get("hologram", {})
    if not holo_cfg.get("enabled", False):
        return False, {}
    return True, holo_cfg

================================================================================
"""
ffmpeg_service.py — CF2 Core FFmpeg Service
Location: cf2/core/services/ffmpeg_service.py
Responsibility: Safe, reusable wrappers around FFmpeg/FFprobe commands.
Compliance: Rule 19 (no hardcoded paths), Rule 28 (configurable limits), Rule 31 (<80 lines/function).
"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List


class FFmpegService:
    """Stateless FFmpeg/FFprobe utility service for CF2 pipeline."""

    @staticmethod
    def get_duration(media_path: str) -> float:
        """Return media duration in seconds. Returns 0.0 on missing/failure."""
        if not media_path or not Path(media_path).exists():
            return 0.0
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", media_path
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except Exception:
            return 0.0

    @staticmethod
    def create_silent_mp3(output_path: str, duration: float) -> bool:
        """Generate a silent MP3 of exact duration."""
        if duration <= 0:
            duration = 0.1
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"aevalsrc=0::d={duration}",
            "-c:a", "libmp3lame", "-b:a", "64k", output_path
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return True
        except Exception:
            return False

    @staticmethod
    def mix_bgm(
        narration_path: str,
        bgm_path: str,
        bgm_volume: float = 0.25,
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Mix background music under narration. BGM ducks to bgm_volume (0-1).
        BGM is looped/trimmed to match narration length. Overwrites narration_path in-place.
        """
        if not Path(narration_path).exists() or not Path(bgm_path).exists():
            if logger: logger("⚠️ BGM mix skipped: missing source files.")
            return False

        tmp = f"{narration_path}.mixed.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-i", narration_path,
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "[a]", "-c:a", "libmp3lame", "-b:a", "128k", tmp
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            if res.returncode == 0 and Path(tmp).exists():
                os.replace(tmp, narration_path)
                if logger: logger(f"🎵 BGM mixed (vol={bgm_volume})")
                return True
            if logger: logger("⚠️ BGM mix failed — using narration only")
            return False
        except Exception as e:
            if logger: logger(f"⚠️ BGM mix error: {e}")
            return False
        finally:
            if Path(tmp).exists():
                try: os.remove(tmp)
                except OSError: pass

    @staticmethod
    def concat_mp3_safe(
        input_paths: List[str],
        output_path: str,
        bitrate: str = "128k",
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Safely concatenate MP3 files with proper re-encoding to fix DTS timestamp issues.
        Uses FFmpeg concat demuxer + libmp3lame re-encoding to ensure monotonically
        increasing timestamps and avoid "non monotonically increasing dts" warnings.
        """
        if not input_paths or not all(Path(p).exists() for p in input_paths):
            if logger: logger("⚠️ Concat skipped: missing input files.")
            return False

        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                concat_file = f.name
                for path in input_paths:
                    safe_path = Path(path).resolve()
                    f.write(f"file '{safe_path}'\n")

            tmp = f"{output_path}.concat_tmp.mp3"
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c:a", "libmp3lame",
                "-b:a", bitrate,
                "-q:a", "4",
                tmp
            ]

            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True
            )

            os.unlink(concat_file)

            if res.returncode == 0 and Path(tmp).exists():
                os.replace(tmp, output_path)
                if logger:
                    logger(f"✅ Concatenated {len(input_paths)} MP3s → {Path(output_path).name}")
                return True
            else:
                if logger:
                    logger(f"⚠️ Concat failed: {res.stderr[:200] if res.stderr else 'Unknown error'}")
                if Path(tmp).exists():
                    os.remove(tmp)
                return False

        except Exception as e:
            if logger: logger(f"⚠️ Concat error: {e}")
            if 'concat_file' in locals() and Path(concat_file).exists():
                try: os.remove(concat_file)
                except OSError: pass
            return False

    @staticmethod
    def enforce_shorts_limit(
        input_path: str,
        max_duration: Optional[float] = None,
        inputs: Optional[Dict[str, Any]] = None,
        unit: Optional[str] = None,
        logger: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Speed up video if it exceeds max_duration so platform accepts it.

        Hybrid resolution order for the duration limit (no hardcoded value
        anywhere in this file — Rule 28 'Config = Identity'):

          1. Explicit `max_duration=` argument (caller fully controls).
          2. `inputs[<unit_prefix>_shorts_max_seconds]` when `inputs` & `unit`
             are passed. Per-unit config — e.g.:
                 unit="Unit-Debate"     -> inputs["debate_shorts_max_seconds"]
                 unit="Unit-Classroom"  -> inputs["classroom_shorts_max_seconds"]
                 unit="Unit-Prodcast"   -> inputs["prodcast_shorts_max_seconds"]
             These get hoisted from each unit's config file by
             flow_controller._flatten_inputs().
          3. `inputs["shorts_max_seconds"]` (legacy / generic fallback).
          4. None  → enforcement is skipped silently (pass-through).

        Returns dict with path, original_duration, new_duration, speed_factor.
        Modifies file in-place via temp file.
        """
        # ── Resolve max_duration without any code-side default ───────────
        if max_duration is None and inputs is not None:
            unit_prefix = None
            if unit and unit.startswith("Unit-"):
                unit_prefix = unit.replace("Unit-", "").lower()
            if unit_prefix:
                max_duration = inputs.get(f"{unit_prefix}_shorts_max_seconds")
            if max_duration is None:
                max_duration = inputs.get("shorts_max_seconds")

        orig = FFmpegService.get_duration(input_path)
        if orig <= 0:
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        # No limit configured anywhere → pass through (don't speed up).
        if max_duration is None:
            if logger: logger("ℹ️  shorts_max_seconds not configured — skipping speed-up")
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        try:
            max_duration = float(max_duration)
        except (TypeError, ValueError):
            if logger: logger(f"⚠️ Invalid shorts_max_seconds value: {max_duration!r} — skipping")
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        if orig <= max_duration:
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        tempo = orig / max_duration
        tmp = f"{input_path}.shorts_limit.mp4"
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-filter_complex",
            f"[0:v]setpts=PTS/{tempo:.4f}[v];[0:a]atempo={tempo:.4f}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "128k", tmp
        ]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            os.replace(tmp, input_path)
            new_dur = FFmpegService.get_duration(input_path)
            factor = orig / new_dur if new_dur > 0 else 1.0
            if logger: logger(f"⚡ Shorts sped up: {orig:.1f}s → {new_dur:.1f}s ({factor:.2f}x)")
            return {"path": input_path, "orig": orig, "new": new_dur, "factor": factor}
        except Exception as e:
            if logger: logger(f"⚠️ Shorts limit enforcement failed: {e}")
            if Path(tmp).exists(): os.remove(tmp)
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

================================================================================
"""
Audio Service — Unified Audio Processing Engine
Handles ffmpeg operations: merge audio+video, concatenate, tempo sync.
Smart skip: checks if output exists before processing.
All ffmpeg calls use subprocess with proper resource management.
"""

import os
import subprocess
import signal as _signal
from typing import Optional, List, Tuple
from pathlib import Path


class AudioService:
    """
    Audio processing service using ffmpeg.

    Responsibilities:
    - Merge audio and video
    - Concatenate multiple audio files
    - Apply tempo/speed adjustments
    - Get duration of audio/video files
    - Smart skip (don't re-process if output exists)
    """

    def __init__(self, logger=None):
        self.logger = logger or self._default_logger

    @staticmethod
    def _default_logger(msg: str):
        print(f"[Audio] {msg}")

    @staticmethod
    def _run(cmd: List[str], capture_output: bool = False) -> subprocess.CompletedProcess:
        """
        Run command with process group support (for Ctrl+C handling).
        Respects system resource limits.
        """
        def _preexec():
            os.setsid()
            try:
                # CPU: lowest priority (19 = idle-only)
                os.nice(19)
            except Exception:
                pass
            try:
                # I/O: idle class
                subprocess.run(
                    ["ionice", "-c", "3", "-p", str(os.getpid())],
                    capture_output=True
                )
            except Exception:
                pass

        proc = subprocess.Popen(
            cmd,
            preexec_fn=_preexec,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
        )

        try:
            while True:
                try:
                    stdout, stderr = proc.communicate(timeout=0.5)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except KeyboardInterrupt:
            try:
                os.killpg(os.getpgid(proc.pid), _signal.SIGTERM)
            except Exception:
                proc.kill()
            raise

        return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)

    def get_duration(self, media_path: str) -> Optional[float]:
        """
        Get duration of audio or video file in seconds.
        Returns None on error.
        """
        media_path = str(media_path)

        try:
            result = self._run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1:noprint_wrappers=1",
                 media_path],
                capture_output=True
            )

            if result.returncode == 0 and result.stdout:
                duration = float(result.stdout.decode().strip())
                self.logger(f"📏 Duration ({os.path.basename(media_path)}): {duration:.2f}s")
                return duration
        except Exception as e:
            self.logger(f"⚠️ Duration detection failed: {str(e)}")

        return None

    def merge_audio_video(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
        target_duration: Optional[float] = None,
        atempo_enabled: bool = True
    ) -> bool:
        """
        Merge video and audio using ffmpeg.
        Optionally apply atempo filter to match target duration.

        Smart skip: returns True if output exists.

        Args:
            video_path: Input video (may have silence)
            audio_path: Input audio
            output_path: Output merged video
            target_duration: If set, tempo-adjust audio to this duration
            atempo_enabled: Enable atempo filter for sync

        Returns:
            True if successful or skipped
        """
        video_path = str(video_path)
        audio_path = str(audio_path)
        output_path = str(output_path)

        # Smart skip
        if os.path.exists(output_path):
            self.logger(f"⏭️ Merge skipped (exists): {os.path.basename(output_path)}")
            return True

        # Get audio duration
        audio_dur = self.get_duration(audio_path)
        if audio_dur is None:
            self.logger(f"❌ Cannot get audio duration: {audio_path}")
            return False

        # Build atempo filter if needed
        atempo_filter = ""
        if atempo_enabled and target_duration is not None and target_duration > 0:
            tempo = audio_dur / target_duration
            if abs(tempo - 1.0) > 0.01:  # Only apply if > 1% difference
                atempo_filter = f"atempo={tempo:.4f}"
                self.logger(f"🎚️ Atempo filter: {atempo_filter} (from {audio_dur:.2f}s to {target_duration:.2f}s)")

        # Build ffmpeg command
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",  # Copy video codec (fast)
            "-c:a", "aac",   # Re-encode audio
            "-shortest",      # Stop at shorter stream
            "-y",             # Overwrite
        ]

        # Add audio filter if present
        if atempo_filter:
            cmd.extend(["-af", atempo_filter])

        cmd.append(output_path)

        try:
            self.logger(f"🎬 Merging audio+video: {os.path.basename(output_path)}")
            result = self._run(cmd)

            if result.returncode == 0 and os.path.exists(output_path):
                self.logger(f"✅ Merge complete: {os.path.basename(output_path)}")
                return True
            else:
                self.logger(f"❌ Merge failed (ffmpeg returned {result.returncode})")
                return False
        except Exception as e:
            self.logger(f"❌ Merge error: {str(e)}")
            return False

    def concatenate_audio(
        self,
        audio_paths: List[str],
        output_path: str,
        fade_duration: float = 0.1
    ) -> bool:
        """
        Concatenate multiple audio files.
        Optional fade between files.

        Smart skip: returns True if output exists.

        Args:
            audio_paths: List of input audio files
            output_path: Output concatenated file
            fade_duration: Fade duration at boundaries (seconds)

        Returns:
            True if successful or skipped
        """
        output_path = str(output_path)

        # Smart skip
        if os.path.exists(output_path):
            self.logger(f"⏭️ Concat skipped (exists): {os.path.basename(output_path)}")
            return True

        if not audio_paths:
            self.logger("❌ No audio files to concatenate")
            return False

        # Create concat demuxer file
        concat_file = output_path.replace(".mp3", "_concat.txt")
        try:
            with open(concat_file, "w") as f:
                for path in audio_paths:
                    f.write(f"file '{os.path.abspath(path)}'\n")
        except Exception as e:
            self.logger(f"❌ Failed to create concat file: {str(e)}")
            return False

        try:
            cmd = [
                "ffmpeg",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                "-y",
                output_path
            ]

            self.logger(f"🎧 Concatenating {len(audio_paths)} audio files: {os.path.basename(output_path)}")
            result = self._run(cmd)

            # Clean up concat file
            try:
                os.remove(concat_file)
            except:
                pass

            if result.returncode == 0 and os.path.exists(output_path):
                self.logger(f"✅ Concatenation complete: {os.path.basename(output_path)}")
                return True
            else:
                self.logger(f"❌ Concatenation failed (ffmpeg returned {result.returncode})")
                return False
        except Exception as e:
            self.logger(f"❌ Concat error: {str(e)}")
            try:
                os.remove(concat_file)
            except:
                pass
            return False

    def apply_atempo(
        self,
        audio_path: str,
        output_path: str,
        target_duration: float
    ) -> bool:
        """
        Apply atempo filter to adjust audio tempo/speed.

        Smart skip: returns True if output exists.

        Args:
            audio_path: Input audio
            output_path: Output audio (tempo-adjusted)
            target_duration: Target duration in seconds

        Returns:
            True if successful or skipped
        """
        audio_path = str(audio_path)
        output_path = str(output_path)

        # Smart skip
        if os.path.exists(output_path):
            self.logger(f"⏭️ Atempo skipped (exists): {os.path.basename(output_path)}")
            return True

        audio_dur = self.get_duration(audio_path)
        if audio_dur is None:
            self.logger(f"❌ Cannot get audio duration: {audio_path}")
            return False

        if target_duration <= 0:
            self.logger(f"❌ Invalid target duration: {target_duration}")
            return False

        tempo = audio_dur / target_duration

        try:
            cmd = [
                "ffmpeg",
                "-i", audio_path,
                "-af", f"atempo={tempo:.4f}",
                "-c:a", "libmp3lame",
                "-q:a", "4",
                "-y",
                output_path
            ]

            self.logger(f"🎚️ Applying atempo ({tempo:.4f}): {os.path.basename(output_path)}")
            result = self._run(cmd)

            if result.returncode == 0 and os.path.exists(output_path):
                self.logger(f"✅ Atempo complete: {os.path.basename(output_path)}")
                return True
            else:
                self.logger(f"❌ Atempo failed")
                return False
        except Exception as e:
            self.logger(f"❌ Atempo error: {str(e)}")
            return False

    def extract_audio(self, video_path: str, output_path: str) -> bool:
        """Extract audio track from a video file."""
        video_path  = str(video_path)
        output_path = str(output_path)
        if os.path.exists(output_path):
            return True
        result = self._run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2", output_path
        ], capture_output=True)
        return result.returncode == 0 and os.path.exists(output_path)

    def create_silence(self, output_path: str, duration: float = 1.0) -> bool:
        """Create a silent audio file of given duration."""
        output_path = str(output_path)
        if os.path.exists(output_path):
            return True
        result = self._run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "anullsrc=r=44100:cl=stereo",
            "-t", str(duration), "-q:a", "2", output_path
        ], capture_output=True)
        return result.returncode == 0 and os.path.exists(output_path)

    def concat(self, audio_paths: List[str], output_path: str) -> bool:
        return self.concatenate_audio(audio_paths, output_path)

    def merge_av(self, video_path: str, audio_path: str, output_path: str) -> bool:
        return self.merge_audio_video(video_path, audio_path, output_path)

================================================================================

# src/cf2/core/services/xtts_service.py

import os
from pathlib import Path
from TTS.api import TTS

_model: TTS | None = None

def _get_model(device: str = "cpu") -> TTS:
    global _model
    if _model is None:
        _model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return _model

def synthesize_xtts(text: str, output_path: str, inputs: dict) -> str:
    cfg     = inputs.get("voice_clone_config", {})
    wav     = cfg.get("speaker_wav", "assets/voices/matin.wav")
    lang    = cfg.get("language", "en")
    device  = cfg.get("device", "cpu")
    cache   = cfg.get("use_cache", True)

    # Smart skip (CF2 Rule 32)
    if os.path.exists(output_path):
        return f"⏭️ Skipped — already exists: {output_path}"

    # Cache check
    if cache:
        from cf2.core.services.voice_clone.cache_manager import get_cached, set_cached
        cached = get_cached(text, wav, lang)
        if cached and os.path.exists(cached):
            import shutil
            shutil.copy(cached, output_path)
            return f"⏭️ Served from cache: {output_path}"

    if not Path(wav).exists():
        raise FileNotFoundError(f"Speaker WAV not found: {wav}")

    model = _get_model(device)
    tmp_wav = output_path.replace(".mp3", "_tmp.wav")

    model.tts_to_file(
        text=text,
        speaker_wav=wav,
        language=lang,
        file_path=tmp_wav
    )

    from cf2.core.services.voice_clone.audio_exporter import wav_to_mp3
    wav_to_mp3(tmp_wav, output_path)
    Path(tmp_wav).unlink(missing_ok=True)

    if cache:
        set_cached(text, wav, lang, output_path)

    return f"✅ XTTS generated: {output_path}"

================================================================================
================================================================================
