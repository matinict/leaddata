"""
crop_service.py — CF2 Video Crop & Format Service
Location: src/cf2/core/services/crop_service.py

Per-format crop + scale + pad in a single FFmpeg call.
Each format and crop block has its own "enabled" switch.

Smart Auto-Crop (Shorts - Content Aware, NO OpenCV):
    When auto_crop=true, uses Edge Detection (Sobel-like gradient) instead
    of raw brightness to find code boundaries. Prevents cursor/tooltip jumps.
    Caches detection per video. Safe for short videos.

Smart skip: output exists → skip (Rule 24).
Zero hardcoded values (Rule 19).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


_FORMAT_DEFAULTS = {
    "HD": {
        "enabled": True,
        "resolution": "1920x1080",
        "blur_pad": False,
        "auto_crop": False,
        "auto_crop_center_pct": 0.55,
        "crop": {"enabled": True, "top": 0, "bottom": 0, "left": 0, "right": 0},
    },
    "Shorts": {
        "enabled": True,
        "resolution": "1080x1920",
        "blur_pad": True,
        "auto_crop": True,
        "auto_crop_center_pct": 0.55,
        "crop": {"enabled": True, "top": 0, "bottom": 0, "left": 0, "right": 0},
    },
}


class CropService:
    """Per-format video crop, scale, and pad service."""

    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        ffprobe_bin: str = "ffprobe",
        logger=None,
    ):
        self.ffmpeg  = ffmpeg_bin
        self.ffprobe = ffprobe_bin
        self.logger  = logger or (lambda msg: print(f"[CropService] {msg}"))

        # ✅ 5️⃣ Performance: Cache detection results per source video
        self._detection_cache: dict[str, int] = {}
        # ✅ Issue #2: configurable font for portable drawtext
        self.fontfile = "assets/fonts/DejaVuSans-Bold.ttf"

    # ══════════════════════════════════════════════════════════════════════
    # Helpers
    # ══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ffmpeg_escape(text: str) -> str:
        """✅ Issue #6: complete escaping for drawtext."""
        return (
            text.replace("\\", r"\\")
                .replace(":", r"\:")
                .replace("'", r"\'")
                .replace("%", r"\%")
        )

    def process_all(
        self,
        source_video: str,
        video_formats_cfg: dict,
        output_dir: str,
        topic: str = "",
        channel: str = "@PlayOwnAi",
        cta: str = "Follow for more Python tips 🐍",
    ) -> dict[str, Optional[str]]:
        results = {}
        for fmt, fmt_cfg in video_formats_cfg.items():
            if not fmt_cfg.get("enabled", True):
                self.logger(f"⏭️ {fmt}: disabled — skipping")
                results[fmt] = None
                continue
            #results[fmt] = self.process_one(source_video, fmt, fmt_cfg, output_dir)
            results[fmt] = self.process_one(
                source_video,
                fmt,
                fmt_cfg,
                output_dir,
                topic=topic,
                channel=channel,
                cta=cta,
            )
        return results

    def process_one(
        self,
        source_video: str,
        fmt: str,
        fmt_cfg: dict,
        output_dir: str,
        topic: str = "",
        channel: str = "@PlayOwnAi",
        cta: str = "Follow for more Python tips 🐍",
    ) -> Optional[str]:
        out_path = Path(output_dir) / f"dubbed_{fmt}.mp4"

        # Smart skip (Rule 24)
        if out_path.exists() and out_path.stat().st_size > 500_000:
            self.logger(f"⏭️ {fmt}: exists — {out_path.name}")
            return str(out_path)

        src_w, src_h = self._probe_dimensions(source_video)
        if src_w == 0 or src_h == 0:
            self.logger(f"❌ {fmt}: cannot probe source dimensions")
            return None

        defaults   = _FORMAT_DEFAULTS.get(fmt, _FORMAT_DEFAULTS["HD"])
        resolution = fmt_cfg.get("resolution", defaults["resolution"])
        blur_pad   = fmt_cfg.get("blur_pad",   defaults["blur_pad"])
        auto_crop  = fmt_cfg.get("auto_crop",  defaults["auto_crop"])
        center_pct = float(fmt_cfg.get("auto_crop_center_pct",
                                       defaults["auto_crop_center_pct"]))

        crop_cfg     = {**defaults["crop"], **fmt_cfg.get("crop", {})}
        crop_enabled = crop_cfg.get("enabled", True)

        try:
            tgt_w, tgt_h = (int(x) for x in resolution.split("x"))
        except ValueError:
            self.logger(f"❌ {fmt}: bad resolution '{resolution}'")
            return None

        # ── Resolve crop region ───────────────────────────────────────
        if auto_crop and crop_enabled:
            left, top, crop_w, crop_h = self._auto_crop_region(
                source_video=source_video,
                src_w=src_w, src_h=src_h,
                tgt_w=tgt_w, tgt_h=tgt_h,
                center_pct=center_pct,
                top_px=int(crop_cfg.get("top", 0)),
                bottom_px=int(crop_cfg.get("bottom", 0)),
            )
            self.logger(
                f"🤖 {fmt}: auto_crop (edge-aware) "
                f"{src_w}x{src_h} → crop {crop_w}x{crop_h} @ x={left},y={top} "
                f"→ {resolution}"
            )

        elif crop_enabled:
            top    = int(crop_cfg.get("top",    0))
            bottom = int(crop_cfg.get("bottom", 0))
            left   = int(crop_cfg.get("left",   0))
            right  = int(crop_cfg.get("right",  0))
            crop_w = src_w - left - right
            crop_h = src_h - top  - bottom
            if crop_w <= 0 or crop_h <= 0:
                self.logger(f"❌ {fmt}: crop values exceed source ({src_w}x{src_h})")
                return None
            self.logger(
                f"🎬 {fmt}: manual crop [T{top} B{bottom} L{left} R{right}]"
                f" → {crop_w}x{crop_h} → {resolution}"
            )

        else:
            top = left = 0
            crop_w, crop_h = src_w, src_h
            self.logger(f"🎬 {fmt}: crop disabled — scale {src_w}x{src_h} → {resolution}")

        vf = self._build_vf(
            left=left, top=top,
            crop_w=crop_w, crop_h=crop_h,
            tgt_w=tgt_w, tgt_h=tgt_h,
            blur_pad=blur_pad,
            crop_enabled=crop_enabled or auto_crop,
            topic=topic,
            channel=channel,
            cta=cta,
            overlay_enabled=(fmt == "Shorts"),
        )

        ok = self._run_ffmpeg(source_video, str(out_path), vf)
        if ok:
            size_mb = out_path.stat().st_size / (1024 * 1024)
            self.logger(f"✅ {fmt}: {out_path.name} ({size_mb:.1f} MB)")
            return str(out_path)

        self.logger(f"❌ {fmt}: FFmpeg failed")
        return None

    # ══════════════════════════════════════════════════════════════════════
    # Smart Auto-Crop Region (Lightweight: Pillow + Numpy)
    # ══════════════════════════════════════════════════════════════════════

    def _detect_content_center_x(self, video_path: str, src_w: int, fallback_center: int) -> int:
        """
        Detect X-center using edge detection (Sobel-like gradient).
        Ignores bright UI elements, focuses on text density boundaries.
        """
        # ✅ 5️⃣ Return cached result if we already analyzed this video
        if video_path in self._detection_cache:
            return self._detection_cache[video_path]

        tmp_frame = Path("temp_crop_analysis_frame.jpg")
        try:
            # ✅ 3️⃣ Safer percentage-based seek (prevents 10s fail on short clips)
            duration = self._probe_duration(video_path)
            seek_sec = max(1.0, duration * 0.25)

            cmd = [
                self.ffmpeg, "-y",
                "-ss", str(seek_sec),
                "-i", video_path,
                "-frames:v", "1",
                "-q:v", "2",
                str(tmp_frame)
            ]
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15
            )

            if not tmp_frame.exists():
                return fallback_center

            # Convert to Grayscale using Pillow
            img = Image.open(tmp_frame).convert("L")
            arr = np.array(img)

            # ✅ 1️⃣ Safer Approach: Sobel-like gradient detection (pure numpy)
            # Edges = text boundaries. Not brightness. Prevents cursor/tooltip jumps.
            grad = np.abs(np.diff(arr.astype(np.int16), axis=1))
            column_activity = np.sum(grad, axis=0)

            # ✅ 2️⃣ Adaptive kernel proportional to video width
            kernel_size = max(21, src_w // 40)
            kernel = np.ones(kernel_size) / kernel_size
            column_activity = np.convolve(column_activity, kernel, mode='same')

            # Find peak activity center
            center_index = int(np.argmax(column_activity))

            # ✅ 5️⃣ Cache the result before returning
            self._detection_cache[video_path] = center_index
            return center_index

        except Exception as e:
            self.logger(f"⚠️ Content detection failed, using fallback: {e}")
            return fallback_center
        finally:
            # Always clean up temp file
            if tmp_frame.exists():
                tmp_frame.unlink()

    def _auto_crop_region(
        self,
        source_video: str,
        src_w: int, src_h: int,
        tgt_w: int, tgt_h: int,
        center_pct: float,
        top_px: int = 0,
        bottom_px: int = 0,
    ) -> tuple[int, int, int, int]:
        """Compute (left, top, crop_w, crop_h) for landscape→vertical auto-crop."""
        trimmed_h = src_h - top_px - bottom_px
        if trimmed_h <= 0:
            trimmed_h = src_h
            top_px = 0

        # Ideal crop width to match target aspect ratio
        target_ar = tgt_w / tgt_h
        ideal_crop_w = int(trimmed_h * target_ar)
        ideal_crop_w = min(ideal_crop_w, src_w)

        # Mathematical fallback center
        band_w      = int(src_w * center_pct)
        band_start  = (src_w - band_w) // 2
        band_end    = band_start + band_w
        band_center = (band_start + band_end) // 2

        # 🧠 INTELLIGENT STEP: Edge-aware dynamic center (No OpenCV)
        dynamic_center = self._detect_content_center_x(
            video_path=source_video,
            src_w=src_w,
            fallback_center=band_center
        )

        # Anchor crop center to detected dynamic center, clamp to source bounds
        left = dynamic_center - ideal_crop_w // 2
        left = max(0, min(left, src_w - ideal_crop_w))

        return left, top_px, ideal_crop_w, trimmed_h

    # ══════════════════════════════════════════════════════════════════════
    # Filter graph builder & FFmpeg runner
    # ══════════════════════════════════════════════════════════════════════

    def _build_vf(
        self,
        left: int, top: int,
        crop_w: int, crop_h: int,
        tgt_w: int, tgt_h: int,
        blur_pad: bool,
        crop_enabled: bool,
        topic: str = "",
        channel: str = "@PlayOwnAi",
        cta: str = "",
        overlay_enabled: bool = False,
    ) -> str:
        """✅ Issues #1-#6: robust filter_complex with labeled streams."""
        crop_filter = f"crop={crop_w}:{crop_h}:{left}:{top}," if crop_enabled else ""

        # Base video processing → [base]
        if not blur_pad:
            base = (
                f"{crop_filter}"
                f"scale={tgt_w}:{tgt_h}:force_original_aspect_ratio=decrease,"
                f"pad={tgt_w}:{tgt_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"format=yuv420p[base]"
            )
        else:
            base = (
                f"{crop_filter}"
                f"split[bg][fg];"
                f"[bg]scale={tgt_w}:{tgt_h}:force_original_aspect_ratio=increase,"
                f"crop={tgt_w}:{tgt_h},gblur=sigma=30[bgblur];"
                f"[fg]scale={tgt_w}:{tgt_h}:force_original_aspect_ratio=decrease[fg];"
                f"[bgblur][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[base]"
            )

        if not overlay_enabled or not (topic or channel or cta):
            # No overlay, just output [base] as [outv]
            return f"{base};[base]null[outv]"

        # ✅ Issue #6: escape, Issue #2: font, Issue #3: dynamic sizing, Issue #4/5: hierarchy
        safe_channel = self._ffmpeg_escape(channel)
        safe_topic = self._ffmpeg_escape(topic[:60])  # truncate long topics
        safe_cta = self._ffmpeg_escape(cta)

        # Dynamic font sizes (Issue #3)
        ch_fs = max(28, min(36, tgt_w // 30))
        tp_fs = max(38, min(56, tgt_w // 19))
        ct_fs = max(30, min(44, tgt_w // 24))

        font = self.fontfile
        font_opt = f"fontfile='{font}':" if Path(font).exists() else ""

        # ✅ Issue #4: premium navy box, Issue #5: hierarchy
        box = "box=1:boxcolor=0x001122@0.75:boxborderw=12"

        overlays = []
        prev = "base"
        idx = 0

        if safe_channel:
            idx += 1
            overlays.append(
                f"[{prev}]drawtext={font_opt}text='{safe_channel}':x=80:y=80:"
                f"fontsize={ch_fs}:fontcolor=white:{box}[v{idx}]"
            )
            prev = f"v{idx}"

        if safe_topic:
            idx += 1
            y_pos = 80 + ch_fs + 24
            overlays.append(
                f"[{prev}]drawtext={font_opt}text='{safe_topic}':x=80:y={y_pos}:"
                f"fontsize={tp_fs}:fontcolor=#00e5ff:{box}[v{idx}]"
            )
            prev = f"v{idx}"

        if safe_cta:
            idx += 1
            overlays.append(
                f"[{prev}]drawtext={font_opt}text='{safe_cta}':x=(w-text_w)/2:y=h-160:"
                f"fontsize={ct_fs}:fontcolor=white:{box}[v{idx}]"
            )
            prev = f"v{idx}"

        # Final label
        overlays.append(f"[{prev}]null[outv]")

        return f"{base};{';'.join(overlays)}"

    def _run_ffmpeg(self, src: str, dst: str, vf: str) -> bool:
        use_complex = ";" in vf or "[outv]" in vf
        if use_complex:
            # ✅ Issue #1: explicit mapping for labeled filter_complex
            cmd = [
                self.ffmpeg, "-y", "-i", src,
                "-filter_complex", vf,
                "-map", "[outv]", "-map", "0:a?",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", dst
            ]
        else:
            cmd = [
                self.ffmpeg, "-y", "-i", src,
                "-vf", vf,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "copy", "-movflags", "+faststart", dst
            ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                self.logger(f"⚠️ FFmpeg: {r.stderr[-300:]}")
            return r.returncode == 0 and Path(dst).exists()
        except subprocess.TimeoutExpired:
            self.logger("❌ FFmpeg timeout (600s)")
            return False
        except Exception as e:
            self.logger(f"❌ FFmpeg exception: {e}")
            return False

    # ══════════════════════════════════════════════════════════════════════
    # FFprobe Utilities
    # ══════════════════════════════════════════════════════════════════════

    def _probe_duration(self, video_path: str) -> float:
        """Get video duration in seconds."""
        try:
            r = subprocess.run(
                [self.ffprobe, "-v", "quiet", "-print_format", "json",
                 "-show_format", video_path],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                return 10.0  # Safe fallback

            data = json.loads(r.stdout)
            return float(data.get("format", {}).get("duration", 10.0))
        except Exception:
            return 10.0  # Safe fallback if unparseable

    def _probe_dimensions(self, video_path: str) -> tuple[int, int]:
        """Get video width and height."""
        try:
            r = subprocess.run(
                [self.ffprobe, "-v", "quiet", "-print_format", "json",
                 "-show_streams", video_path],
                capture_output=True, text=True, timeout=10,
            )
            # ✅ 4️⃣ Safety check: prevent json.loads crash on ffprobe failure
            if r.returncode != 0:
                return 0, 0

            for s in json.loads(r.stdout).get("streams", []):
                if s.get("codec_type") == "video":
                    return int(s["width"]), int(s["height"])
        except Exception as e:
            self.logger(f"⚠️ probe failed: {e}")
        return 0, 0
