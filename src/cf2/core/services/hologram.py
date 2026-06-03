"""
hologram.py — CF2 Shared Hologram Service (Premium UI Edition)
==========================================================
Turns any archived / external video into a reusable, stylised
teaching-panel overlay consumable by any CF2 unit.

Types:
  1: Original Video Crop (Standard overlay)
  2: Screen OCR / Code Text (Auto-detect IDE/terminal, crop screen, apply sci-fi filter)

Panel Mode (mode="panel"):
  - Premium "Apple Vision Pro / Iron Man UI" aesthetic
  - Glass panel border with corner accents
  - Preserves syntax highlighting for educational readability
  - Subtle futuristic effects (high CTR, mobile friendly)
  - Brand identity elements (drawbox HUD frame)
  - FAST RENDER: Uses only native FFmpeg filters (no per-pixel `geq`)

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
import re
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
    CLIP_OVERLAY = 1
    SCREEN_OCR   = 2

class HologramMode(str, Enum):
    FLOATING_SCREEN = "floating_screen"
    PROJECTOR       = "projector"
    GLASS_PANEL     = "glass_panel"
    PANEL           = "panel"

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
    render_keys: dict       = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "HologramManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        if "render_keys" not in data:
            data["render_keys"] = {}
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
        default_mode:  HologramMode = HologramMode.PANEL,
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
        try:
            mode = HologramMode(mode_str)
        except ValueError:
            mode = HologramMode.PANEL

        try:
            holo_type = HologramType(holo_config.get("type", 2))
        except ValueError:
            holo_type = HologramType.SCREEN_OCR

        self.clip_speed = float(holo_config.get("clip_speed", 1.0))
        sources_cfg = holo_config.get("sources", [])

        hologram_dir = self._hologram_dir(topic_slug)
        self._ensure_dirs(hologram_dir)

        manifest = self._load_or_create_manifest(topic_slug, hologram_dir)

        for src_cfg in sources_cfg:
            source = self._parse_source_cfg(src_cfg)
            source_cached = self._is_cached(manifest, source)

            if source_cached:
                print(f"[Hologram] ⏭️  Source cached — skipping extraction for {source.id}")
                # FIX: Hydrate ClipType Enum properly instead of leaving it as a string
                clips = [
                    ClipEntry(**{**c, "clip_type": ClipType(c.get("clip_type", "CODE"))})
                    for c in manifest.clips
                    if c.get("source_id") == source.id
                ]
            else:
                print(f"[Hologram] 📡 Preparing source: {source.id} ({source.type.value}, Type {holo_type.value})")

                try:
                    local_path = self._resolve_source(source, hologram_dir)
                except Exception as e:
                    print(f"[Hologram] ❌ Source resolve failed for {source.id}: {e}")
                    continue

                normalized_path = self._normalize_source(local_path, hologram_dir)

                if holo_type == HologramType.SCREEN_OCR:
                    clips = self._extract_screen_content(source, normalized_path, hologram_dir)
                else:
                    clips = self._extract_clips(source, normalized_path, hologram_dir)

                self._update_manifest(manifest, source, clips, hologram_dir)

            if not clips:
                continue

            for clip in clips:
                self._build_hologram_overlay(
                    clip,
                    hologram_dir,
                    mode,
                    manifest=manifest,
                )

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

        try:
            src_type = SourceType(cfg.get("type", cfg.get("source_type", "local")))
        except ValueError:
            src_type = SourceType.LOCAL

        return HologramSource(
            id        = cfg.get("id", f"src_{hashlib.md5(str(cfg).encode()).hexdigest()[:8]}"),
            type      = src_type,
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
            try:
                src_path = Path(source.path)
                if src_path.exists():
                    src_mtime  = src_path.stat().st_mtime
                    dest_mtime = dest.stat().st_mtime
                    if dest_mtime >= src_mtime:
                        return dest
                    print(f"[Hologram] 🔄 Source updated — re-copying {source.id}")
                else:
                    return dest
            except Exception:
                pass

        if source.type == SourceType.LOCAL:
            src = Path(source.path)
            if not src.is_absolute():
                src = self.assets_root / source.path

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

    def _normalize_source(self, raw_path: Path, hologram_dir: Path) -> Path:
        norm_dir = hologram_dir / "source"
        norm_dir.mkdir(parents=True, exist_ok=True)
        dest = norm_dir / f"{raw_path.stem}_norm.mp4"

        if dest.exists() and dest.stat().st_size > 1000:
            try:
                if raw_path.exists() and dest.stat().st_mtime >= raw_path.stat().st_mtime:
                    return dest
            except Exception:
                pass

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

        # FIX: Always transcode audio to AAC to guarantee MP4 container compatibility
        # (Opus/Vorbis from MKV/WebM will fail with `-c:a copy` inside MP4)
        cmd = [
            self.ffmpeg_bin, "-y", "-i", str(raw_path), "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart", str(dest),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode != 0:
            return raw_path

        print(f"[Hologram] ✅ Normalized: {dest.name} ({nw}x{nh}@30fps)")
        return dest

    # ──────────────────────────────────────────
    # mtime-aware extraction helper
    # ──────────────────────────────────────────

    def _needs_reextract(self, out_path: Path, normalized_path: Path, filename: str) -> bool:
        if not out_path.exists() or out_path.stat().st_size < 1000:
            return True

        try:
            src_mtime = normalized_path.stat().st_mtime
            out_mtime = out_path.stat().st_mtime

            if out_mtime < src_mtime:
                print(f"[Hologram] 🔄 Source changed — re-extracting {filename}")
                return True
        except Exception:
            return True

        return False

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

        for line in r.stderr.splitlines():
            match = re.search(r"crop=(\d+:\d+:\d+:\d+)", line)
            if match:
                crop_values = match.group(1).split(":")
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

                if self._needs_reextract(out_path, normalized_path, filename):
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

            if span == duration:
                filename = f"{source.id}.mp4"
                out_path = clips_dir / filename

                if self._needs_reextract(out_path, normalized_path, filename):
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

                    if self._needs_reextract(out_path, normalized_path, filename):
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
        af_parts = []

        if clip_speed and clip_speed != 1.0:
            vf_parts.append(f"setpts=PTS/{clip_speed:.2f}")
            af_parts.append(self._build_atempo_filter(clip_speed))

        vf = ",".join(vf_parts)
        af = ",".join(af_parts)

        cmd = [
            self.ffmpeg_bin, "-y",
            "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(src),
            "-vf", vf,
        ]

        # FIX: Properly sync audio when changing speed.
        # Normalization guarantees AAC, so copy is safe when speed=1.0
        if af:
            cmd.extend(["-af", af, "-c:a", "aac", "-b:a", "128k"])
        else:
            cmd.extend(["-c:a", "copy"])

        cmd.extend([
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            str(dest),
        ])

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

                if self._needs_reextract(out_path, normalized_path, filename):
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

                if self._needs_reextract(out_path, normalized_path, filename):
                    self._ffmpeg_cut(normalized_path, out_path, t_start, t_end)

                clips.append(ClipEntry(clip_id=f"{source.id}_{seg_label}", source_id=source.id, segment_id=seg_label, clip_type=ct, filename=filename, start_sec=t_start, end_sec=t_end))

        print(f"[Hologram] ✅ {len(clips)} clips extracted for {source.id}")
        return clips

    def _ffmpeg_cut(self, src: Path, dest: Path, start: float, end: float) -> None:
        # Normalization guarantees AAC, so copy is fast and lossless
        cmd = [
            self.ffmpeg_bin, "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
            "-i", str(src), "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "copy", str(dest),
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
    # ──────────────────────────────────────────

    _SCANLINE_SPACING = {
        HologramMode.FLOATING_SCREEN: 4,
        HologramMode.PROJECTOR:       6,
        HologramMode.GLASS_PANEL:     8,
        HologramMode.PANEL:           3,
    }

    def _build_hologram_overlay(self, clip: ClipEntry, hologram_dir: Path, mode: HologramMode, manifest: Optional[HologramManifest] = None) -> None:
        renders_dir = hologram_dir / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        src  = hologram_dir / "clips" / clip.filename
        dest = renders_dir / f"holo_{clip.filename}"

        if not src.exists():
            return

        render_key = hashlib.md5(
            f"{clip.filename}|{mode.value}|{self.clip_speed}".encode()
        ).hexdigest()

        if dest.exists() and dest.stat().st_size > 1000:
            old_key = ""
            if manifest:
                old_key = manifest.render_keys.get(clip.filename, "")

            src_newer = False
            try:
                src_newer = dest.stat().st_mtime < src.stat().st_mtime
            except Exception:
                pass

            if old_key == render_key and not src_newer:
                return
            else:
                reason = "params" if old_key != render_key else "source updated"
                print(f"[Hologram] 🔄 Render {reason} for {clip.filename} — re-rendering")

        filter_graph = self._mode_filter(mode)

        # Audio is copied losslessly from the extraction step
        cmd = [
            self.ffmpeg_bin, "-y", "-i", str(src),
            "-filter_complex", filter_graph,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(dest),
        ]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        except subprocess.TimeoutExpired:
            print(f"[Hologram] ⚠️ Render timed out for {clip.filename} (heavy filters on long video).")
            r = None

        if r is None or r.returncode != 0:
            if r is not None:
                print(f"[Hologram] ⚠️ Render failed for {clip.filename}: {r.stderr[-200:]}")
            print(f"[Hologram] 🔄 Applying fast fallback render for {clip.filename}...")
            fallback_cmd = [
                self.ffmpeg_bin, "-y",
                "-i", str(src),
                "-vf", "curves=r='0 0 1 0.7':g='0 0 1 0.9':b='0 0 1 1.3',eq=brightness=0.08:saturation=1.2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                str(dest)
            ]
            try:
                subprocess.run(fallback_cmd, capture_output=True, text=True, timeout=300)
            except subprocess.TimeoutExpired:
                print(f"[Hologram] ❌ Fallback render also timed out for {clip.filename}. Skipping.")
        else:
            print(f"[Hologram] 🎨 Rendered: holo_{clip.filename} ({mode.value})")

        if manifest:
            manifest.render_keys[clip.filename] = render_key
            manifest.save(hologram_dir / "manifest.json")

    def _mode_filter(self, mode: HologramMode) -> str:
        """
        Build a multi-stage FFmpeg filter_complex graph.

        PANEL MODE: Premium "Apple Vision Pro / Iron Man UI" aesthetic.
        - Glass panel border with corner accents (Iron Man HUD frame)
        - Preserves syntax highlighting for educational readability
        - FAST RENDER: Skips expensive per-pixel `geq` scanlines/shimmer entirely.
          Uses optimized native filters (eq, colorbalance, unsharp, vignette).
        """

        sl = self._SCANLINE_SPACING.get(mode, 3)

        # ── 1. Desaturate ────────────────────────────────────────────
        desat = "hue=s=0.75" if mode == HologramMode.PANEL else "hue=s=0.08"

        # ── 2. Tint ──────────────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            tint = "curves=r='0 0 0.7 0.45 1 0.55':g='0 0 0.5 0.65 1 0.85':b='0 0.15 0.5 0.80 1 1.0'"
        elif mode == HologramMode.PROJECTOR:
            tint = "curves=r='0 0 0.7 0.35 1 0.5':g='0 0 0.5 0.55 1 0.72':b='0 0.20 0.5 0.85 1 1.0'"
        elif mode == HologramMode.PANEL:
            tint = (
                "colorbalance=rs=-0.05:gs=0.02:bs=0.10,"
                "eq=contrast=1.05:brightness=0.01:saturation=1.02"
            )
        else:
            tint = "curves=r='0 0 0.7 0.55 1 0.65':g='0 0 0.5 0.70 1 0.88':b='0 0.10 0.5 0.78 1 0.95'"

        # ── 3. Edge / object glow ────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            glow_radius, glow_opacity = 18, 0.55
        elif mode == HologramMode.PROJECTOR:
            glow_radius, glow_opacity = 24, 0.45
        elif mode == HologramMode.PANEL:
            glow_radius, glow_opacity = 4, 0.10
        else:
            glow_radius, glow_opacity = 12, 0.35

        glow = (
            f"split[base][glw];"
            f"[glw]gblur=sigma={glow_radius},eq=brightness=0.08:contrast=1.1[gblurred];"
            f"[base][gblurred]blend=all_mode=screen:all_opacity={glow_opacity}"
        )

        # ── 4. Scanlines & 5. Shimmer ───────────────────────────────
        # FIX: Skip expensive/unsupported `geq` for PANEL mode entirely.
        # This guarantees fast rendering and no FFmpeg crashes for long videos.
        if mode == HologramMode.PANEL:
            scanlines_and_shimmer = "null" # No-op; handled by fast native filters below
        else:
            if mode == HologramMode.FLOATING_SCREEN:
                scanline_dark = 0.35
            elif mode == HologramMode.PROJECTOR:
                scanline_dark = 0.40
            else:
                scanline_dark = 0.45

            if mode == HologramMode.FLOATING_SCREEN:
                shimmer_amp, shimmer_freq = 0.06, 2.8
            elif mode == HologramMode.PROJECTOR:
                shimmer_amp, shimmer_freq = 0.04, 1.5
            else:
                shimmer_amp, shimmer_freq = 0.03, 1.2

            scanlines_and_shimmer = (
                f"geq="
                f"r='if(eq(mod(Y,{sl}),0),r(X,Y)*{scanline_dark},r(X,Y))':"
                f"g='if(eq(mod(Y,{sl}),0),g(X,Y)*{scanline_dark},g(X,Y))':"
                f"b='if(eq(mod(Y,{sl}),0),b(X,Y)*{scanline_dark},b(X,Y))',"
                f"geq="
                f"r='r(X,Y)*(1+{shimmer_amp}*sin({shimmer_freq}*PI*T))':"
                f"g='g(X,Y)*(1+{shimmer_amp}*sin({shimmer_freq}*PI*T))':"
                f"b='b(X,Y)*(1+{shimmer_amp}*sin({shimmer_freq}*PI*T))'"
            )

        # ── 6. Vignette ──────────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            vignette = "vignette=PI/3.2:eval=frame"
        elif mode == HologramMode.PROJECTOR:
            vignette = "vignette=PI/2.5:eval=frame"
        elif mode == HologramMode.PANEL:
            vignette = "vignette=PI/14.0:eval=frame"
        else:
            vignette = "vignette=PI/4.5:eval=frame"

        # ── 7. Final polish ──────────────────────────────────────────
        if mode == HologramMode.FLOATING_SCREEN:
            polish = "eq=brightness=0.04:contrast=1.12:saturation=1.15:gamma_b=1.08"
        elif mode == HologramMode.PROJECTOR:
            polish = "eq=brightness=0.02:contrast=1.08:saturation=1.10:gamma_b=1.05"
        elif mode == HologramMode.PANEL:
            # Strong unsharp for crisp mobile text readability
            polish = (
                "eq=brightness=0.01:contrast=1.04:saturation=1.02,"
                "unsharp=5:5:1.8:5:5:0.0"
            )
        else:
            polish = "eq=brightness=0.01:contrast=1.05:saturation=1.05:gamma_b=1.03"

        # ── Assemble base chain ───────────────────────────────────────
        pre  = f"{desat},{tint}"
        post = f"{scanlines_and_shimmer},{vignette},{polish}"

        # ── 8. HUD Frame Overlay (PANEL only) ────────────────────────
        if mode == HologramMode.PANEL:
            hud = (
                "drawbox=x=14:y=14:w=iw-28:h=ih-28:color=cyan@0.15:thickness=2,"
                "drawbox=x=14:y=14:w=50:h=3:color=cyan@0.65:t=fill,"
                "drawbox=x=14:y=14:w=3:h=50:color=cyan@0.65:t=fill,"
                "drawbox=x=iw-64:y=14:w=50:h=3:color=cyan@0.65:t=fill,"
                "drawbox=x=iw-17:y=14:w=3:h=50:color=cyan@0.65:t=fill,"
                "drawbox=x=14:y=ih-17:w=50:h=3:color=cyan@0.65:t=fill,"
                "drawbox=x=14:y=ih-64:w=3:h=50:color=cyan@0.65:t=fill,"
                "drawbox=x=iw-64:y=ih-17:w=50:h=3:color=cyan@0.65:t=fill,"
                "drawbox=x=iw-17:y=ih-64:w=3:h=50:color=cyan@0.65:t=fill"
            )
            return f"{pre},{glow},{post},{hud},format=yuv420p"

        return f"{pre},{glow},{post},format=yuv420p"


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
        manifest.sources = [
            s for s in manifest.sources
            if s.get("id") != source.id
        ]
        manifest.clips = [
            c for c in manifest.clips
            if c.get("source_id") != source.id
        ]

        src_dict = {"id": source.id, "type": source.type.value, "path": source.path, "label": source.label}
        manifest.sources.append(src_dict)

        for clip in clips:
            manifest.clips.append(asdict(clip))

        resolved_path = Path(source.path)
        manifest.cache_state[source.id] = {
            "key": self._cache_key(source, resolved_path),
            "cached_at": datetime.utcnow().isoformat(),
            "clip_count": len(clips),
        }
        manifest.save(hologram_dir / "manifest.json")

    def _is_cached(self, manifest: HologramManifest, source: HologramSource) -> bool:
        state = manifest.cache_state.get(source.id)
        if not state: return False
        resolved_path = Path(source.path)
        return state.get("key") == self._cache_key(source, resolved_path)

    @staticmethod
    def _cache_key(source: HologramSource, path: Optional[Path] = None) -> str:
        mtime = ""
        if path and path.exists():
            mtime = str(path.stat().st_mtime)

        raw = (
            f"{source.id}|"
            f"{source.path}|"
            f"{source.start_sec}|"
            f"{source.end_sec}|"
            f"{mtime}"
        )
        return hashlib.md5(raw.encode()).hexdigest()

    # ──────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _build_atempo_filter(speed: float) -> str:
        """
        Build an FFmpeg atempo filter chain.
        atempo only accepts values between 0.5 and 2.0.
        For speeds outside this range, chain multiple filters.
        """
        if speed <= 0.0:
            return ""
        filters = []
        remaining = speed
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        if remaining != 1.0:
            filters.append(f"atempo={remaining:.4f}")
        return ",".join(filters)

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
