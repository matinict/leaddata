"""cf2/core/tts/providers/piper.py"""
import shutil, subprocess
from pathlib import Path
from cf2.core.tts.base import TTSProvider


class Provider(TTSProvider):
    def is_available(self) -> bool:
        return bool(Path(self.config.get("model_dir", "models/piper")).exists())

    def synthesize(self, text: str, output_path: str, voice: str) -> bool:
        model = Path(self.config.get("model_dir", "models/piper")) / f"{voice}.onnx"
        if not model.exists():
            return False

        wav = output_path.replace(".mp3", ".wav") if output_path.endswith(".mp3") else output_path + ".wav"
        cmd = (["piper"] if shutil.which("piper")
               else ["uvx", "--from", "piper-tts", "piper"]) + ["-m", str(model), "-f", wav]

        r = subprocess.run(
            cmd, input=text, capture_output=True, text=True,
            timeout=self.config.get("timeout_sec", 60),
        )
        if r.returncode != 0 or not Path(wav).exists():
            return False

        if output_path.endswith(".mp3") and wav != output_path:
            return self._wav_to_mp3(wav, output_path)
        return True
