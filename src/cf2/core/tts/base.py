"""
cf2/core/tts/base.py
Abstract base class for all TTS providers.
Every provider module under providers/ must export a `Provider` class
inheriting from TTSProvider and implementing synthesize().
"""
from abc import ABC, abstractmethod
from pathlib import Path


class TTSProvider(ABC):
    """Stateless TTS adapter. Instantiated per call from provider config."""

    def __init__(self, config: dict):
        self.config = config or {}

    @abstractmethod
    def synthesize(self, text: str, output_path: str, voice: str) -> bool:
        """Generate audio file. Return True on success."""
        ...

    def is_available(self) -> bool:
        """Quick precheck — override if provider needs API key / binary check."""
        return True

    @staticmethod
    def _wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
        import subprocess
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", wav_path,
             "-ar", "24000", "-ac", "1", "-b:a", "48k", mp3_path],
            capture_output=True, timeout=30
        )
        Path(wav_path).unlink(missing_ok=True)
        return r.returncode == 0 and Path(mp3_path).exists()
