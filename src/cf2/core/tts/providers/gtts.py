"""cf2/core/tts/providers/gtts.py"""
from pathlib import Path
from cf2.core.tts.base import TTSProvider


class Provider(TTSProvider):
    def is_available(self) -> bool:
        try:
            import gtts  # noqa: F401
            return True
        except ImportError:
            return False

    def synthesize(self, text: str, output_path: str, voice: str) -> bool:
        from gtts import gTTS
        lang = voice if voice and len(voice) <= 5 else "en"
        gTTS(text=text, lang=lang).save(output_path)
        return Path(output_path).exists()
