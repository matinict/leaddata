"""cf2/core/tts/providers/elevenlabs.py"""
import os
from pathlib import Path
from cf2.core.tts.base import TTSProvider


class Provider(TTSProvider):
    def is_available(self) -> bool:
        try:
            import requests  # noqa: F401
        except ImportError:
            return False
        return bool(os.environ.get(self.config.get("api_key_env", "ELEVENLABS_API_KEY")))

    def synthesize(self, text: str, output_path: str, voice: str) -> bool:
        import requests
        api_key = os.environ.get(self.config.get("api_key_env", "ELEVENLABS_API_KEY"))
        endpoint = self.config.get("endpoint", "https://api.elevenlabs.io")
        r = requests.post(
            f"{endpoint}/v1/text-to-speech/{voice}",
            headers={"xi-api-key": api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": "eleven_monolingual_v1"},
            timeout=self.config.get("timeout_sec", 30),
        )
        if r.status_code != 200:
            return False
        Path(output_path).write_bytes(r.content)
        return True
