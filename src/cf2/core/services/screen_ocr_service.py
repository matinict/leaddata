from __future__ import annotations

"""
screen_ocr_service.py — Educational Screen OCR Service

Uses a subprocess-isolated worker (ocr_worker.py) to run PaddleOCR.
This is required because PaddlePaddle's oneDNN backend initializes at
C++ .so load time — env var flags set in the parent process are already
too late. The worker subprocess sets them before any paddle code loads.
"""

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ── Logging Setup ────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

try:
    from config import PATHS
    LOG_DIR = PATHS["logs"] / "ocr"
except ImportError:
    LOG_DIR = Path(".runtime/logs/ocr")


def _log_ocr(action: str, video: str = "", details: dict = None):
    """Write OCR event to .runtime/logs/ocr/ as timestamped JSON."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        safe_video = Path(video).stem if video else "unknown"
        safe_video = re.sub(r'[^\w\-.]', '_', safe_video)
        log_file = LOG_DIR / f"{ts}_ocr_{action}_{safe_video}.json"
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "video": video,
            "details": details or {},
        }
        log_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[OCR_LOG_ERROR] Failed to write log: {e}", file=sys.stderr)


def _normalize_text(text: str) -> str:
    """Normalize for stable dedup hashing."""
    return " ".join(text.split()).lower()


# ── Worker path resolution ───────────────────────────────────────────────────

def _worker_cmd() -> List[str]:
    """
    Build the command to invoke ocr_worker.py in the same venv Python.
    Uses sys.executable so the venv interpreter is always used,
    never a system Python that might lack paddleocr.
    """
    return [sys.executable, "-m", "cf2.core.services.ocr_worker"]


# ── Service ──────────────────────────────────────────────────────────────────

class ScreenOCRService:
    def __init__(
        self,
        ffmpeg_bin: str = "ffmpeg",
        base_fps: float = 0.5,
        max_frames: int = 30,
        confidence_threshold: float = 0.70,
        crop_region: Optional[Tuple[int, int, int, int]] = None,
        lang: str = "en",
        worker_timeout: int = 60,
    ):
        """
        Args:
            ffmpeg_bin:           ffmpeg binary path/name
            base_fps:             Target FPS for frame extraction
            max_frames:           Hard frame limit (enables adaptive FPS)
            confidence_threshold: Min confidence for UI/Terminal blocks
            crop_region:          (x, y, w, h) crop before OCR
            lang:                 PaddleOCR language code
            worker_timeout:       Seconds before killing a stuck worker process
        """
        self.ffmpeg_bin           = ffmpeg_bin
        self.ffprobe_bin          = ffmpeg_bin.replace("ffmpeg", "ffprobe")
        self.base_fps             = base_fps
        self.max_frames           = max_frames
        self.confidence_threshold = confidence_threshold
        self.code_confidence_threshold = 0.55
        self.crop_region          = crop_region
        self.lang                 = lang
        self.worker_timeout       = worker_timeout

        _log_ocr("init", details={
            "lang":                      self.lang,
            "base_fps":                  self.base_fps,
            "max_frames":                self.max_frames,
            "confidence_threshold":      self.confidence_threshold,
            "code_confidence_threshold": self.code_confidence_threshold,
            "crop_region":               list(self.crop_region) if self.crop_region else None,
            "worker_timeout":            self.worker_timeout,
            "worker_cmd":                _worker_cmd()[1],
        })

    # ──────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────

    def extract(
        self,
        video_path: str,
        output_dir: Path,
        cleanup_frames: bool = True,
    ) -> str:
        """
        Extract screen text from sampled video frames.

        Returns:
            Merged plain text (CODE + TERMINAL only, UI excluded).
        Saves:
            ocr_blocks.json in output_dir with all blocks including UI.
        """
        output_dir = Path(output_dir)
        frames_dir = output_dir / "screen_frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        try:
            # 1. Adaptive frame sampling
            duration     = self._get_video_duration(video_path)
            adaptive_fps = min(self.base_fps, self.max_frames / max(duration, 1))

            self._extract_frames(video_path, frames_dir, fps=adaptive_fps)

            frame_files = sorted(frames_dir.glob("*.jpg"))[: self.max_frames]

            seen_hashes:     set       = set()
            collected_blocks: List[dict] = []
            text_blocks:      List[str]  = []

            # 2. OCR each frame in isolated subprocess
            for frame_path in frame_files:
                frame_blocks = self._ocr_frame_subprocess(frame_path)

                for block in frame_blocks:
                    text_hash = hashlib.md5(
                        _normalize_text(block["text"]).encode("utf-8")
                    ).hexdigest()

                    if text_hash in seen_hashes:
                        continue

                    seen_hashes.add(text_hash)
                    block["frame"] = frame_path.name
                    collected_blocks.append(block)

                    if block["type"] in {"code", "terminal"}:
                        text_blocks.append(block["text"])

            # 3. Save structured JSON (all types, for future use)
            ocr_json = output_dir / "ocr_blocks.json"
            ocr_json.write_text(
                json.dumps(collected_blocks, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            merged = "\n\n".join(text_blocks).strip()

            _log_ocr("ocr_complete", video_path, {
                "duration_seconds":        round(duration, 2),
                "adaptive_fps":            round(adaptive_fps, 3),
                "frames_processed":        len(frame_files),
                "unique_blocks_total":     len(collected_blocks),
                "unique_code_term_blocks": len(text_blocks),
                "char_count":              len(merged),
            })

            return merged

        except Exception as e:
            _log_ocr("error", video_path, {"error": str(e)})
            raise
        finally:
            if cleanup_frames and frames_dir.exists():
                shutil.rmtree(frames_dir, ignore_errors=True)

    # ──────────────────────────────────────────
    # Subprocess OCR
    # ──────────────────────────────────────────

    def _ocr_frame_subprocess(self, frame_path: Path) -> List[dict]:
        """
        Run ocr_worker.py in a fresh subprocess for this frame.

        The subprocess sets paddle env flags before any import,
        which is the ONLY reliable way to disable oneDNN on affected builds.

        Communication:
          - Args passed via temp JSON file (avoids shell escaping issues)
          - Results returned as JSON on stdout
          - Errors written to stderr (logged as WARNING, never crash parent)
        """
        args = {
            "image_path":               str(frame_path),
            "lang":                     self.lang,
            "crop_region":              list(self.crop_region) if self.crop_region else [],
            "confidence_threshold":     self.confidence_threshold,
            "code_confidence_threshold": self.code_confidence_threshold,
        }

        # Write args to a temp file — safer than passing large JSON on CLI
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            json.dump(args, tmp)
            tmp_path = Path(tmp.name)

        try:
            cmd = _worker_cmd() + [str(tmp_path)]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.worker_timeout,
                # Pass through the parent env but override the critical flags
                # This is a belt-and-suspenders measure; the worker also sets them
                env={
                    **__import__("os").environ,
                    "FLAGS_enable_pir_api":         "0",
                    "FLAGS_enable_pir_in_executor": "0",
                    "FLAGS_use_mkldnn":             "0",
                    "FLAGS_enable_mkldnn_bfloat16": "0",
                    "MKL_THREADING_LAYER":          "GNU",
                    "OMP_NUM_THREADS":              "1",
                },
            )

            # Log stderr from worker (paddle noise + real errors)
            if result.stderr.strip():
                # Filter out known harmless paddle startup messages
                real_errors = [
                    line for line in result.stderr.splitlines()
                    if line.strip()
                    and not any(noise in line for noise in [
                        "UserWarning",
                        "Creating model:",
                        "Model files already exist",
                        "warnings.warn",
                        "paddlex",
                        "ccache",
                    ])
                ]
                if real_errors:
                    logger.warning(
                        f"OCR worker stderr for {frame_path.name}:\n"
                        + "\n".join(real_errors)
                    )

            if not result.stdout.strip():
                logger.warning(
                    f"OCR worker returned no output for {frame_path.name} "
                    f"(exit={result.returncode})"
                )
                return []

            blocks: List[dict] = json.loads(result.stdout)
            return blocks

        except subprocess.TimeoutExpired:
            logger.warning(
                f"OCR worker timed out after {self.worker_timeout}s "
                f"on {frame_path.name} — skipping frame"
            )
            return []

        except json.JSONDecodeError as e:
            logger.warning(
                f"OCR worker returned invalid JSON for {frame_path.name}: {e}"
            )
            return []

        except Exception as e:
            logger.warning(f"OCR worker failed on {frame_path.name}: {e}")
            return []

        finally:
            # Always clean up temp args file
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

    # ──────────────────────────────────────────
    # ffmpeg helpers
    # ──────────────────────────────────────────

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds via ffprobe."""
        cmd = [
            self.ffprobe_bin,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return float(result.stdout.strip())
        except Exception:
            return 60.0

    def _extract_frames(self, video_path: str, frames_dir: Path, fps: float) -> None:
        """Extract frames via ffmpeg at adaptive fps."""
        # Clear existing frames
        if frames_dir.exists():
            for p in frames_dir.glob("*"):
                try:
                    p.unlink()
                except Exception:
                    pass

        out_pattern = frames_dir / "frame_%04d.jpg"
        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-i", str(video_path),
            "-vf", f"fps={fps}",
            str(out_pattern),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            error_msg = result.stderr[-400:]
            _log_ocr("error", video_path, {"stage": "ffmpeg", "error": error_msg})
            raise RuntimeError(f"ffmpeg frame extraction failed: {error_msg}")

        extracted = len(list(frames_dir.glob("*.jpg")))
        _log_ocr("frames_extracted", video_path, {
            "frame_count": extracted,
            "fps_used":    fps,
        })


__all__ = ["ScreenOCRService"]
