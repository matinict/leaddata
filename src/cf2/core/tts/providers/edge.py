"""cf2/core/tts/providers/edge.py"""
from cf2.core.tts.base import TTSProvider


class Provider(TTSProvider):
    def synthesize(self, text: str, output_path: str, voice: str) -> bool:
        from cf2.core.services.tts_service import TTSService
        tts = TTSService(logger=lambda m: None)
        return tts.generate_edge(text, output_path, voice=voice)
