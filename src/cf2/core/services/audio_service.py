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
