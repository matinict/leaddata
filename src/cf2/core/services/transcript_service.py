"""
transcript_service.py
Speech → text extraction using Whisper
"""

from pathlib import Path
import whisper


class TranscriptService:

    def __init__(self, model_size="base"):
        self.model_size = model_size

    def transcribe(
        self,
        video_path: str,
        output_path: Path,
    ) -> str:

        model = whisper.load_model(self.model_size)

        result = model.transcribe(
            video_path,
            fp16=False,
        )

        text = result["text"].strip()

        output_path.write_text(
            text,
            encoding="utf-8"
        )

        return text
