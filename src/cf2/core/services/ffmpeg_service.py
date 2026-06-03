"""
ffmpeg_service.py — CF2 Core FFmpeg Service
Location: cf2/core/services/ffmpeg_service.py
Responsibility: Safe, reusable wrappers around FFmpeg/FFprobe commands.
Compliance: Rule 19 (no hardcoded paths), Rule 28 (configurable limits), Rule 31 (<80 lines/function).
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Callable, List


# ── Configurable limits (Rule 28) ──────────────────────────────────────────
MAX_SILENT_DURATION = 3600.0   # 1 hour ceiling for create_silent_mp3
SHORTS_PRESET = "veryfast"     # CPU-optimised x264 preset


class FFmpegService:
    """Stateless FFmpeg/FFprobe utility service for CF2 pipeline."""

    # ── Binary resolution (Rule 19: no hardcoded paths) ────────────────────

    @staticmethod
    def _find_ffmpeg() -> Optional[str]:
        """Locate ffmpeg binary. Returns None if not found."""
        return shutil.which("ffmpeg")

    @staticmethod
    def _find_ffprobe() -> Optional[str]:
        """Locate ffprobe binary. Returns None if not found."""
        return shutil.which("ffprobe")

    # ── Duration probing ───────────────────────────────────────────────────

    @staticmethod
    def get_duration(
        media_path: str,
        logger: Optional[Callable[[str], None]] = None
    ) -> float:
        """Return media duration in seconds. Returns 0.0 on missing/failure."""
        if not media_path or not Path(media_path).exists():
            return 0.0
        ffprobe = FFmpegService._find_ffprobe()
        if not ffprobe:
            if logger:
                logger("⚠️ Duration probe failed: ffprobe not found")
            return 0.0
        cmd = [
            ffprobe, "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", media_path
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(res.stdout.strip())
        except ValueError:
            return 0.0
        except subprocess.CalledProcessError:
            return 0.0
        except OSError:
            return 0.0
        except Exception as e:
            if logger:
                logger(f"⚠️ Duration probe failed: {e}")
            return 0.0

    # ── Audio integrity validation ─────────────────────────────────────────

    @staticmethod
    def is_valid_audio(
        path: str,
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Validate that a file is a real, non-zero-duration audio file.
        Uses ffprobe to verify container is parseable and duration > 0.
        Returns False for missing, empty, truncated, or broken files.
        """
        if not path or not Path(path).exists():
            if logger:
                logger(f"⚠️ Audio validation failed: file missing — {path}")
            return False

        file_size = os.path.getsize(path)
        if file_size < 1024:
            if logger:
                logger(
                    f"⚠️ Audio validation failed: file too small "
                    f"({file_size} bytes) — {path}"
                )
            return False

        duration = FFmpegService.get_duration(path, logger=logger)
        if duration <= 0:
            if logger:
                logger(
                    f"⚠️ Audio validation failed: zero/negative duration "
                    f"({duration}) — {path}"
                )
            return False

        return True

    # ── Silent MP3 generation ──────────────────────────────────────────────

    @staticmethod
    def create_silent_mp3(
        output_path: str,
        duration: float,
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """Generate a silent MP3 of exact duration (clamped to MAX_SILENT_DURATION)."""
        if duration <= 0:
            duration = 0.1
        duration = min(duration, MAX_SILENT_DURATION)

        ffmpeg = FFmpegService._find_ffmpeg()
        if not ffmpeg:
            if logger:
                logger("⚠️ Silent MP3 failed: FFmpeg not found")
            return False

        cmd = [
            ffmpeg, "-y", "-f", "lavfi",
            "-i", f"aevalsrc=0::d={duration}",
            "-c:a", "libmp3lame", "-b:a", "64k", output_path
        ]
        try:
            subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            if logger:
                logger(f"⚠️ Silent MP3 generation failed: {e}")
            return False
        except OSError as e:
            if logger:
                logger(f"⚠️ Silent MP3 OS error: {e}")
            return False

    # ── BGM mixing ─────────────────────────────────────────────────────────

    @staticmethod
    def mix_bgm(
        narration_path: str,
        bgm_path: str,
        bgm_volume: float = 0.25,
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Mix background music under narration. BGM ducks to bgm_volume (0-1).
        BGM is looped/trimmed to match narration length.
        Overwrites narration_path in-place.
        """
        if not Path(narration_path).exists() or not Path(bgm_path).exists():
            if logger:
                logger("⚠️ BGM mix skipped: missing source files.")
            return False

        ffmpeg = FFmpegService._find_ffmpeg()
        if not ffmpeg:
            if logger:
                logger("⚠️ BGM mix failed: FFmpeg not found")
            return False

        tmp = f"{narration_path}.mixed.mp3"
        cmd = [
            ffmpeg, "-y",
            "-i", narration_path,
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex",
            f"[1:a]volume={bgm_volume}[bgm];"
            f"[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=0[a]",
            "-map", "[a]", "-c:a", "libmp3lame", "-b:a", "128k", tmp
        ]

        replaced = False
        try:
            res = subprocess.run(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            if res.returncode == 0 and Path(tmp).exists():
                os.replace(tmp, narration_path)
                replaced = True
                if logger:
                    logger(f"🎵 BGM mixed (vol={bgm_volume})")
                return True
            err = res.stderr.decode(errors="ignore")[:500] if res.stderr else "Unknown"
            if logger:
                logger(f"⚠️ BGM mix failed: {err}")
            return False
        except Exception as e:
            if logger:
                logger(f"⚠️ BGM mix error: {e}")
            return False
        finally:
            if not replaced and Path(tmp).exists():
                try:
                    os.remove(tmp)
                except OSError:
                    pass

    # ── MP3 concatenation ──────────────────────────────────────────────────

    @staticmethod
    def concat_mp3_safe(
        input_paths: List[str],
        output_path: str,
        bitrate: str = "128k",
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Safely concatenate MP3 files with proper re-encoding to fix DTS
        timestamp issues. Uses FFmpeg concat demuxer + libmp3lame re-encoding
        to ensure monotonically increasing timestamps.
        """
        if not input_paths or not all(Path(p).exists() for p in input_paths):
            if logger:
                logger("⚠️ Concat skipped: missing input files.")
            return False

        ffmpeg = FFmpegService._find_ffmpeg()
        if not ffmpeg:
            if logger:
                logger("⚠️ Concat failed: FFmpeg not found")
            return False

        concat_file = None
        tmp = f"{output_path}.concat_tmp.mp3"
        try:
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.txt', delete=False
            ) as f:
                concat_file = f.name
                for path in input_paths:
                    safe_path = Path(path).resolve()
                    # Escape single quotes for FFmpeg concat list format
                    escaped = str(safe_path).replace("'", r"'\''")
                    f.write(f"file '{escaped}'\n")

            cmd = [
                ffmpeg, "-y",
                "-f", "concat", "-safe", "0",
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

            if concat_file and Path(concat_file).exists():
                os.unlink(concat_file)
                concat_file = None

            if res.returncode == 0 and Path(tmp).exists():
                os.replace(tmp, output_path)
                if logger:
                    logger(
                        f"✅ Concatenated {len(input_paths)} MP3s "
                        f"→ {Path(output_path).name}"
                    )
                return True
            else:
                err = res.stderr[:300] if res.stderr else "Unknown error"
                if logger:
                    logger(f"⚠️ Concat failed: {err}")
                if Path(tmp).exists():
                    os.remove(tmp)
                return False

        except Exception as e:
            if logger:
                logger(f"⚠️ Concat error: {e}")
            if concat_file and Path(concat_file).exists():
                try:
                    os.remove(concat_file)
                except OSError:
                    pass
            if Path(tmp).exists():
                try:
                    os.remove(tmp)
                except OSError:
                    pass
            return False

    # ── Merge audio + video ────────────────────────────────────────────────

    @staticmethod
    def merge_audio_video(
        video_path: str,
        audio_path: str,
        output_path: str,
        logger: Optional[Callable[[str], None]] = None
    ) -> bool:
        """
        Replace the audio track of a video with a new audio file.

        - Copies video stream (no re-encode → fast).
        - Replaces audio stream with provided audio.
        - Stops at shortest stream (-shortest).
        - Validates inputs exist and output is non-trivial.
        - Cleans up partial output on failure.
        """
        # ── Validate inputs ────────────────────────────────────────────────
        if not video_path or not Path(video_path).exists():
            if logger:
                logger(f"⚠️ Merge failed: video not found — {video_path}")
            return False

        if not audio_path or not Path(audio_path).exists():
            if logger:
                logger(f"⚠️ Merge failed: audio not found — {audio_path}")
            return False

        # ── Validate audio integrity ───────────────────────────────────────
        if not FFmpegService.is_valid_audio(audio_path, logger=None):
            if logger:
                logger(
                    f"⚠️ Merge failed: audio file invalid/corrupt "
                    f"— {audio_path}"
                )
            return False

        ffmpeg = FFmpegService._find_ffmpeg()
        if not ffmpeg:
            if logger:
                logger("⚠️ Merge failed: FFmpeg not found on PATH")
            return False

        # ── Build output directory if needed ───────────────────────────────
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # ── Run FFmpeg merge ───────────────────────────────────────────────
        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path
        ]

        if logger:
            logger(
                f"🔄 Merging: {Path(video_path).name} + "
                f"{Path(audio_path).name} → {Path(output_path).name}"
            )

        res = subprocess.run(cmd, capture_output=True, check=False)

        if res.returncode != 0:
            err = res.stderr.decode(errors="ignore")[:1000]
            if logger:
                logger(f"⚠️ Merge failed (rc={res.returncode}): {err}")
            # Clean up partial output so next run doesn't skip
            if Path(output_path).exists():
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            return False

        # ── Validate output ────────────────────────────────────────────────
        if not Path(output_path).exists():
            if logger:
                logger(
                    "⚠️ Merge failed: output file missing after FFmpeg success"
                )
            return False

        output_size = os.path.getsize(output_path)
        if output_size < 1024:
            if logger:
                logger(
                    f"⚠️ Merge failed: output too small ({output_size} bytes)"
                )
            # Clean up tiny/invalid output
            try:
                os.remove(output_path)
            except OSError:
                pass
            return False

        if logger:
            size_mb = output_size / (1024 * 1024)
            logger(f"✅ Merge done: {Path(output_path).name} ({size_mb:.1f} MB)")

        return True

    # ── Shorts duration enforcement ────────────────────────────────────────

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
                 unit="Unit-Debate"     → inputs["debate_shorts_max_seconds"]
                 unit="Unit-Classroom"  → inputs["classroom_shorts_max_seconds"]
                 unit="Unit-Prodcast"   → inputs["prodcast_shorts_max_seconds"]
             These get hoisted from each unit's config file by
             flow_controller._flatten_inputs().
          3. `inputs["shorts_max_seconds"]` (legacy / generic fallback).
          4. None  → enforcement is skipped silently (pass-through).

        Returns dict with path, original_duration, new_duration, speed_factor.
        Modifies file in-place via temp file.
        """
        # ── Resolve max_duration without any code-side default ─────────────
        if max_duration is None and inputs is not None:
            unit_prefix = None
            if unit and unit.startswith("Unit-"):
                unit_prefix = unit.replace("Unit-", "").lower()
            if unit_prefix:
                max_duration = inputs.get(f"{unit_prefix}_shorts_max_seconds")
            if max_duration is None:
                max_duration = inputs.get("shorts_max_seconds")

        orig = FFmpegService.get_duration(input_path, logger=logger)
        if orig <= 0:
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        # No limit configured anywhere → pass through
        if max_duration is None:
            if logger:
                logger("ℹ️  shorts_max_seconds not configured — skipping speed-up")
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        try:
            max_duration = float(max_duration)
        except (TypeError, ValueError):
            if logger:
                logger(
                    f"⚠️ Invalid shorts_max_seconds value: "
                    f"{max_duration!r} — skipping"
                )
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        if orig <= max_duration:
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        tempo = orig / max_duration

        # atempo filter only supports (0.5, 100.0); chain if needed
        if tempo <= 100.0:
            atempo_str = f"atempo={tempo:.4f}"
        else:
            atempo_a = min(tempo, 100.0)
            atempo_b = tempo / atempo_a
            atempo_str = f"atempo={atempo_a:.4f},atempo={atempo_b:.4f}"

        ffmpeg = FFmpegService._find_ffmpeg()
        if not ffmpeg:
            if logger:
                logger("⚠️ Shorts limit enforcement failed: FFmpeg not found")
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}

        tmp = f"{input_path}.shorts_limit.mp4"
        cmd = [
            ffmpeg, "-y", "-i", input_path,
            "-filter_complex",
            f"[0:v]setpts=PTS/{tempo:.4f}[v];[0:a]{atempo_str}[a]",
            "-map", "[v]", "-map", "[a]",
            "-c:v", "libx264", "-preset", SHORTS_PRESET, "-crf", "22",
            "-c:a", "aac", "-b:a", "128k", tmp
        ]
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            if res.returncode != 0:
                err = res.stderr.decode(errors="ignore")[:500]
                if logger:
                    logger(f"⚠️ Speed-up failed: {err}")
                if Path(tmp).exists():
                    os.remove(tmp)
                return {
                    "path": input_path, "orig": orig, "new": orig, "factor": 1.0
                }

            os.replace(tmp, input_path)
            new_dur = FFmpegService.get_duration(input_path, logger=logger)
            factor = orig / new_dur if new_dur > 0 else 1.0
            if logger:
                logger(
                    f"⚡ Shorts sped up: {orig:.1f}s → {new_dur:.1f}s "
                    f"({factor:.2f}x)"
                )
            return {
                "path": input_path, "orig": orig, "new": new_dur, "factor": factor
            }
        except Exception as e:
            if logger:
                logger(f"⚠️ Shorts limit enforcement failed: {e}")
            if Path(tmp).exists():
                os.remove(tmp)
            return {"path": input_path, "orig": orig, "new": orig, "factor": 1.0}
