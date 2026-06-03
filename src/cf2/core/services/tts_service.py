"""
TTS Service - Unified TTS Engine
Handles gTTS, Edge TTS, Piper, XTTS with consistent interface.
Smart skip: checks if output already exists before generating.
Defaults provided for config, but fully overridable via inputs.
"""
import os
import re
import asyncio
import shutil
import subprocess
import tempfile
from typing import Optional, List, Union
from pathlib import Path

# -- Optional TTS imports (graceful fallback) -------------------------------
try:
    from gtts import gTTS
except ImportError:
    gTTS = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    import piper
except ImportError:
    piper = None

try:
    from TTS.api import TTS
except ImportError:
    TTS = None

RateLike = Union[int, float, str, None]


def _normalize_edge_rate(rate: RateLike) -> Optional[str]:
    if rate is None or isinstance(rate, bool):
        return None
    if isinstance(rate, int):
        pct = rate
    elif isinstance(rate, float):
        pct = int(round((rate - 1.0) * 100))
    elif isinstance(rate, str):
        s = rate.strip()
        if not s:
            return None
        m = re.fullmatch(r"([+-]?)(\d+)%", s)
        if m:
            sign, num = m.group(1), m.group(2)
            pct = int(num) * (-1 if sign == "-" else 1)
        else:
            try:
                pct = int(round((float(s) - 1.0) * 100))
            except ValueError:
                return None
    else:
        return None
    return f"{max(-50, min(pct, 100)):+d}%"


def _load_xtts_model(model_dir: str, device: str, logger):
    """
    Load XTTS v2 model using explicit local checkpoint loading.
    Avoids TTS() constructor which routes through model manager
    and triggers CPML prompt and unwanted downloads.
    """
    try:
        from TTS.tts.configs.xtts_config import XttsConfig
        from TTS.tts.models.xtts import Xtts
    except ImportError as e:
        logger(f"XTTS internal import failed: {e}")
        return None, None

    config_path     = os.path.join(model_dir, "config.json")
    checkpoint_path = os.path.join(model_dir, "model.pth")
    vocab_path      = os.path.join(model_dir, "vocab.json")

    try:
        config = XttsConfig()
        config.load_json(config_path)

        model = Xtts.init_from_config(config)
        model.load_checkpoint(
            config,
            checkpoint_path=checkpoint_path,
            vocab_path=vocab_path,
            eval=True,
            use_deepspeed=False,
        )
        model.to(device)
        return model, config

    except Exception as e:
        logger(f"XTTS model load failed: {e}")
        return None, None


class TTSService:
    """Unified TTS service supporting multiple engines."""

    def __init__(self, logger=None):
        self.logger = logger or self._default_logger
        self._xtts_cache = {}

    @staticmethod
    def _default_logger(msg: str):
        print(f"[TTS] {msg}")

    def split_sentences(self, text: str, max_chars: int = 150) -> List[str]:
        if not text:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks, current_chunk = [], ""
        for sent in sentences:
            if not sent.strip():
                continue
            if len(sent) > max_chars:
                words = sent.split()
                for word in words:
                    if len(current_chunk) + len(word) + 1 > max_chars:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = word
                    else:
                        current_chunk += " " + word if current_chunk else word
            else:
                test_chunk = current_chunk + " " + sent if current_chunk else sent
                if len(test_chunk) <= max_chars:
                    current_chunk = test_chunk
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sent
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        return chunks

    # -- gTTS ----------------------------------------------------------------
    def generate_gtts(
        self,
        text: str,
        output_path: str,
        lang: str = "en",
        slow: bool = False,
    ) -> bool:
        output_path = str(output_path)
        if os.path.exists(output_path):
            self.logger(f"gTTS skipped (exists): {os.path.basename(output_path)}")
            return True
        if not gTTS:
            self.logger("gTTS not installed")
            return False
        try:
            self.logger(f"gTTS generating: {os.path.basename(output_path)}")
            gTTS(text=text, lang=lang, slow=slow).save(output_path)
            self.logger(f"gTTS done: {os.path.basename(output_path)}")
            return True
        except Exception as e:
            self.logger(f"gTTS failed: {e}")
            return False

    # -- Edge TTS ------------------------------------------------------------
    async def _generate_edge_async_core(
        self,
        text: str,
        voice: str,
        output_path: str,
        rate: RateLike,
        timeout: int,
    ) -> None:
        kwargs = {"text": text, "voice": voice}
        rate_str = _normalize_edge_rate(rate)
        if rate_str and rate_str != "+0%":
            kwargs["rate"] = rate_str
        communicate = edge_tts.Communicate(**kwargs)
        await asyncio.wait_for(communicate.save(output_path), timeout=timeout)

    def generate_edge(
        self,
        text: str,
        output_path: str,
        voice: str = "en-US-AriaNeural",
        rate: RateLike = None,
        timeout: int = 120,
    ) -> bool:
        output_path = str(output_path)
        if os.path.exists(output_path):
            self.logger(f"Edge TTS skipped (exists): {os.path.basename(output_path)}")
            return True
        if not edge_tts:
            self.logger("edge-tts not installed")
            return False
        try:
            self.logger(
                f"Edge TTS generating ({voice}): {os.path.basename(output_path)}"
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    self._generate_edge_async_core(
                        text, voice, output_path, rate, timeout
                    )
                )
            finally:
                asyncio.set_event_loop(None)
                loop.close()
            self.logger(f"Edge TTS done: {os.path.basename(output_path)}")
            return True
        except asyncio.TimeoutError:
            self.logger(f"Edge TTS timeout ({timeout}s)")
            return False
        except Exception as e:
            self.logger(f"Edge TTS failed: {e}")
            return False

    # -- Piper ---------------------------------------------------------------
    def generate_piper(
        self,
        text: str,
        output_path: str,
        model_path: str,
        speed: float = 1.0,
        speaker: int = 0,
    ) -> bool:
        output_path = str(output_path)
        if os.path.exists(output_path):
            self.logger(f"Piper skipped (exists): {os.path.basename(output_path)}")
            return True
        piper_binary = shutil.which("piper")
        if not piper_binary:
            self.logger("Piper binary not found. Install with: sudo apt install piper")
            return False
        if not model_path or not os.path.exists(model_path):
            self.logger(f"Piper model not found: {model_path}")
            return False
        try:
            self.logger(
                f"Piper generating: {os.path.basename(output_path)} "
                f"(model: {os.path.basename(model_path)})"
            )
            temp_wav = str(Path(output_path).with_suffix(".wav"))
            length_scale = 1.0 / max(0.1, speed)
            cmd = [
                piper_binary,
                "--model", model_path,
                "--output_file", temp_wav,
                "--length_scale", str(length_scale),
                "--speaker", str(speaker),
            ]
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                check=False,
            )
            if result.returncode != 0 or not os.path.exists(temp_wav):
                err = result.stderr.decode()[:200] if result.stderr else "Unknown"
                self.logger(f"Piper failed: {err}")
                return False

            ffmpeg_binary = shutil.which("ffmpeg")
            if not ffmpeg_binary:
                self.logger("FFmpeg not found.")
                return False

            ffmpeg_result = subprocess.run(
                [ffmpeg_binary, "-y", "-i", temp_wav, "-q:a", "2", output_path],
                capture_output=True,
                check=False,
            )
            try:
                os.remove(temp_wav)
            except OSError:
                pass
            if ffmpeg_result.returncode != 0 or not os.path.exists(output_path):
                self.logger("FFmpeg conversion failed")
                return False
            size = os.path.getsize(output_path)
            self.logger(
                f"Piper done: {os.path.basename(output_path)} ({size // 1024} KB)"
            )
            return True
        except Exception as e:
            self.logger(f"Piper error: {e}")
            return False

    # -- XTTS (Fixed: explicit checkpoint loading, no TTS() constructor) -----
    def generate_xtts(
        self,
        text: str,
        output_path: str,
        speaker_wav: str,
        language: str = "en",
        model_dir: str = "models/xtts",
        device: str = "cpu",
        chunk_size: int = 120,
    ) -> bool:
        output_path = str(output_path)

        # CPU-only enforcement
        if device != "cpu":
            self.logger(
                f"Non-CPU device '{device}' requested — no GPU available. "
                f"Falling back to cpu."
            )
            device = "cpu"

        if os.path.exists(output_path):
            self.logger(f"XTTS skipped (exists): {os.path.basename(output_path)}")
            return True

        if not speaker_wav or not os.path.exists(speaker_wav):
            self.logger(f"XTTS speaker wav not found: {speaker_wav}")
            return False

        required_files = ["model.pth", "config.json", "vocab.json"]
        for f in required_files:
            fpath = os.path.join(model_dir, f)
            if not os.path.exists(fpath):
                self.logger(f"Missing XTTS file: {fpath}")
                return False

        try:
            import soundfile as sf
        except ImportError:
            self.logger("soundfile not installed (pip install soundfile)")
            return False

        try:
            self.logger(
                f"XTTS generating (voice: {os.path.basename(speaker_wav)}): "
                f"{os.path.basename(output_path)}"
            )

            # 1. Split text into chunks
            chunks = self.split_sentences(text, max_chars=chunk_size)
            if not chunks:
                self.logger("XTTS: empty text")
                return False

            # 2. Load cached model using explicit checkpoint loader
            cache_key = (model_dir, device)
            if cache_key not in self._xtts_cache:
                self.logger(
                    f"Loading XTTS model from: {model_dir} on {device}..."
                )
                model, config = _load_xtts_model(model_dir, device, self.logger)
                if model is None:
                    return False
                self._xtts_cache[cache_key] = (model, config)

            tts_model, tts_config = self._xtts_cache[cache_key]

            # 3. Generate chunks with progress
            with tempfile.TemporaryDirectory() as temp_dir:
                wav_files = []
                total_chars = sum(len(c) for c in chunks)
                done_chars = 0

                for i, chunk in enumerate(chunks, 1):
                    chunk_path = os.path.join(temp_dir, f"chunk_{i:03d}.wav")

                    outputs = tts_model.synthesize(
                        text=chunk,
                        config=tts_config,
                        speaker_wav=speaker_wav,
                        gpt_cond_len=3,
                        language=language,
                    )

                    sf.write(chunk_path, outputs["wav"], 24000)

                    if not os.path.exists(chunk_path):
                        self.logger(
                            f"XTTS chunk {i}/{len(chunks)} missing after write"
                        )
                        return False

                    size = os.path.getsize(chunk_path)
                    done_chars += len(chunk)
                    pct = (done_chars / total_chars) * 100
                    self.logger(
                        f"XTTS chunk {i}/{len(chunks)}: "
                        f"{size} bytes — {pct:.1f}%"
                    )
                    wav_files.append(chunk_path)

                # 4. Merge chunks via ffmpeg
                ffmpeg_binary = shutil.which("ffmpeg")
                if not ffmpeg_binary:
                    self.logger("XTTS merge failed: FFmpeg not found")
                    return False

                concat_file = os.path.join(temp_dir, "concat.txt")
                with open(concat_file, "w", encoding="utf-8") as f:
                    for wav in wav_files:
                        escaped = wav.replace("'", r"'\''")
                        f.write(f"file '{escaped}'\n")

                cmd = [
                    ffmpeg_binary, "-y",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c:a", "libmp3lame",
                    "-b:a", "128k",
                    output_path,
                ]
                result = subprocess.run(cmd, capture_output=True, check=False)

                if result.returncode != 0:
                    err = result.stderr.decode(errors="ignore")[:1000]
                    self.logger(
                        f"XTTS merge failed (rc={result.returncode}): {err}"
                    )
                    if os.path.exists(output_path):
                        try:
                            os.remove(output_path)
                        except OSError:
                            pass
                    return False

                if not os.path.exists(output_path):
                    self.logger("XTTS output missing after merge")
                    return False

                if os.path.getsize(output_path) < 1024:
                    self.logger(
                        f"XTTS output too small: "
                        f"{os.path.getsize(output_path)} bytes"
                    )
                    return False

            self.logger(f"XTTS done: {os.path.basename(output_path)}")
            return True

        except Exception as e:
            self.logger(f"XTTS failed: {e}")
            return False

    # -- Universal entry point -----------------------------------------------
    def generate(
        self,
        text: str,
        output_path: str,
        engine: str = "gtts",
        **engine_config,
    ) -> bool:
        engine = engine.lower()
        if engine == "gtts":
            return self.generate_gtts(
                text, output_path,
                lang=engine_config.get("lang", "en"),
                slow=engine_config.get("slow", False),
            )
        if engine == "edge":
            return self.generate_edge(
                text, output_path,
                voice=engine_config.get("voice", "en-US-AriaNeural"),
                rate=engine_config.get("rate"),
                timeout=engine_config.get("timeout", 120),
            )
        if engine == "piper":
            return self.generate_piper(
                text, output_path,
                model_path=engine_config.get("model_path", ""),
                speed=engine_config.get("speed", 1.0),
                speaker=engine_config.get("speaker", 0),
            )
        if engine == "xtts":
            return self.generate_xtts(
                text, output_path,
                speaker_wav=engine_config.get("speaker_wav", ""),
                language=engine_config.get("language", "en"),
                model_dir=engine_config.get("xtts_model_dir", "models/xtts"),
                device=engine_config.get("device", "cpu"),
                chunk_size=engine_config.get("chunk_max_chars", 120),
            )
        self.logger(f"Unknown TTS engine: {engine}")
        return False