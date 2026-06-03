"""
packaging_yt_thumbnail.py — Config-Driven High-CTR AI Thumbnail Generator
Backends: dashscope (PAI) → openai → local_diffusers → placeholder
Rule: 19 (Paths), 23 (Config), 24 (Smart Skip), 17 (Function Size)
Fallback: Tries methods in order. STOPS on first success. Logs failures. Never crashes.
"""
import os
import re
import time
import json
import requests
from pathlib import Path
from crewai.tools import BaseTool
from typing import Type, ClassVar
from pydantic import BaseModel, Field

# Rule 19: Path routing via config.py
try:
    from config import PROJECT_ROOT
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]

from .publisher_yt_shared import parse_video_formats, get_animation_formats

class YTThumbnailToolInput(BaseModel):
    topic: str = Field(..., description="Video topic")
    filename: str = Field(..., description="Base filename slug")
    output_dir: str = Field(..., description="Output directory")
    channel: str = Field(default=" ", description="Channel name")
    video_formats: list = Field(default=[], description="Video formats")
    thumbnail_config: dict = Field(default={}, description="Thumbnail backend config")

class YTThumbnailTool(BaseTool):
    name: str = "PackagingYtThumbnail"
    description: str = "Generates high-CTR YouTube thumbnails via config-routed AI backend"
    args_schema: Type[BaseModel] = YTThumbnailToolInput

    # 🔥 FIX: Annotate as ClassVar so Pydantic ignores it
    THUMBNAIL_PROMPT: ClassVar[str] = """Create a high-CTR YouTube thumbnail (1280x720, 16:9) for a geopolitical debate video.
Scene: Split-screen comparison between {country_a} and {country_b}
Visuals: Left side: {country_a} flag + symbolic image. Right side: {country_b} flag + contrasting image.
Text (MAX 2–3 WORDS ONLY): "{hook}" - Bold, heavy sans-serif, white/yellow with dark outline. Center/Top.
Style: High contrast, cinematic lighting, clean composition, mobile readable.
DO NOT: Use full sentences, add clutter, repeat title."""

    DEFAULT_METHODS: ClassVar[list] = ["dashscope", "openai", "local_diffusers", "placeholder"]

    def _run(self, topic: str, filename: str, output_dir: str,
             channel: str = " ", video_formats: list = None,
             thumbnail_config: dict = None) -> str:
        t0 = time.time()
        cfg = thumbnail_config or {}
        methods = [m.lower().strip() for m in cfg.get("thumbnail_methods", self.DEFAULT_METHODS)]
        w, h = cfg.get("width", 1280), cfg.get("height", 720)

        country_a, country_b = self._extract_countries(topic)
        hook = self._generate_hook(topic)
        prompt = self.THUMBNAIL_PROMPT.format(country_a=country_a, country_b=country_b, hook=hook)

        video_formats = parse_video_formats(video_formats, ["Shorts", "HD"])
        animation_video_formats = get_animation_formats([], video_formats)
        saved = []

        for fmt in animation_video_formats:
            th_dir = Path(output_dir) / "YT" / fmt / "Th"
            jpg_path = th_dir / f"{filename}.jpg"
            png_path = th_dir / f"{filename}.png"
            prompt_path = th_dir / "high-CTR-YT-Th.txt"

            # 🔥 Rule 24: Smart Skip
            if jpg_path.exists() and png_path.exists():
                print(f"[YTThumb] ⏭️ Skip {fmt} — thumbnail already exists")
                saved.append(str(jpg_path))
                continue

            try:
                print(f"[YTThumb] 🎨 Generating {fmt} (Fallback: {' → '.join(methods)})")
                th_dir.mkdir(parents=True, exist_ok=True)

                if not prompt_path.exists():
                    prompt_path.write_text(prompt, encoding="utf-8")
                    print(f"[YTThumb] 📝 Prompt saved → high-CTR-YT-Th.txt")

                # 🛑 SHORT-CIRCUIT: Stops on first success
                image_source = self._generate_with_fallback(prompt, methods, w, h, cfg)
                self._save_image(image_source, jpg_path, png_path)
                saved.append(str(jpg_path))

            except Exception as e:
                print(f"[YTThumb] ❌ {fmt} failed after all fallbacks: {e}")

        return f"✅ Thumbnails COMPLETED in {time.time()-t0:.1f}s\nSaved: {', '.join(saved)}"

    def _generate_with_fallback(self, prompt: str, methods: list, w: int, h: int, cfg: dict) -> str:
        """Try backends in order. STOPS immediately on first success."""
        for method in methods:
            try:
                print(f"[YTThumb] 🔌 Trying backend: {method}")
                src = self._route_method(method, prompt, w, h, cfg)
                if src:
                    print(f"[YTThumb] ✅ {method} succeeded. Stopping chain.")
                    return src
            except Exception as e:
                print(f"[YTThumb] ⚠️ {method} failed: {e}")
        raise RuntimeError("All thumbnail generation backends failed.")

    def _route_method(self, method: str, prompt: str, w: int, h: int, cfg: dict) -> str:
        routers = {
            "dashscope": self._call_dashscope,
            "openai": self._call_openai,
            "local_diffusers": self._call_local_diffusers,
            "placeholder": lambda p, w, h, c: f"https://placehold.co/{w}x{h}/1a1a2e/FFF?text=Thumbnail+Mock"
        }
        router = routers.get(method)
        if not router:
            raise ValueError(f"Unknown method: {method}")
        return router(prompt, w, h, cfg)

    def _call_dashscope(self, prompt: str, w: int, h: int, cfg: dict) -> str:
        """DashScope Image Generation via direct HTTP to PAI workspace."""
        import requests

        # Load API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            secret = PROJECT_ROOT / ".runtime" / "secrets" / "dashscope_key.txt"
            if secret.exists():
                raw = secret.read_text().strip()
                if "=" in raw:
                    raw = raw.split("=", 1)[-1].strip()
                api_key = raw.strip().strip('"').strip("'").strip()
        if not api_key or not api_key.startswith("sk-"):
            raise ValueError(f"Invalid DASHSCOPE_API_KEY. Got: '{api_key[:10] if api_key else None}...'")

        # Workspace endpoint (your custom URL)
        base_endpoint = cfg.get("dashscope_native_endpoint",
            "https://ws-ml5w5d25c5b4vqpd.ap-southeast-1.maas.aliyuncs.com/api/v1")
        # Correct path for image generation on PAI workspaces
        url = f"{base_endpoint}/services/aigc/multimodal-generation/generation"

        # Size format: use "*" not "x"
        size_str = f"{w}*{h}"

        # Use the working model
        model = cfg.get("dashscope_model", "wan2.6-t2i")  # default to the tested model

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": prompt}
                        ]
                    }
                ]
            },
            "parameters": {
                "n": 1,
                "size": size_str,
                "prompt_extend": True   # optional, improves quality
            }
        }

        print(f"[YTThumb] 🌏 Calling PAI endpoint: {url}")
        print(f"[YTThumb] 🤖 Model: {model}, size: {size_str}")

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()

            result = response.json()
            # Extract image URL from the response structure you observed
            image_url = result["output"]["choices"][0]["message"]["content"][0]["image"]
            print(f"[YTThumb] ✅ Image generated successfully")
            return image_url

        except requests.exceptions.RequestException as e:
            error_detail = ""
            if e.response is not None:
                error_detail = f" - {e.response.text}"
            raise RuntimeError(f"HTTP request failed: {e}{error_detail}")
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to parse response: {e}\nResponse: {response.text if 'response' in locals() else 'unknown'}")

    def _call_openai(self, prompt, w, h, cfg):
        """OpenAI DALL-E 3 — most reliable for production."""
        from openai import OpenAI
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            secret = PROJECT_ROOT / ".runtime" / "secrets" / "openai_key.txt"
            if secret.exists(): api_key = secret.read_text().strip()
        if not api_key: raise ValueError("Missing OPENAI_API_KEY")

        client = OpenAI(api_key=api_key)
        # DALL-E 3 size mapping
        size_map = {(1280, 720): "1792x1024", (720, 1280): "1024x1792", (1024, 1024): "1024x1024"}
        dalle_size = size_map.get((w, h), "1024x1024")

        resp = client.images.generate(model="dall-e-3", prompt=prompt, size=dalle_size, quality="standard", n=1)
        return resp.data[0].url

    def _call_local_diffusers(self, prompt: str, w: int, h: int, cfg: dict) -> str:
        """CPU-optimized Stable Diffusion fallback using project models/ directory."""
        import torch
        from diffusers import StableDiffusionPipeline
        from huggingface_hub import snapshot_download

        model_id = cfg.get("hf_model", "Lykon/dreamshaper-8")
        steps = min(cfg.get("steps", 20), 25)
        safe_name = model_id.replace("/", "_")
        local_model_dir = str(PROJECT_ROOT / "models" / "stable-diffusion" / safe_name)

        # Auto-download if missing
        if not os.path.exists(os.path.join(local_model_dir, "model_index.json")):
            print(f"[YTThumb] 📥 Downloading {model_id} to models/ ...")
            os.makedirs(local_model_dir, exist_ok=True)
            snapshot_download(repo_id=model_id, local_dir=local_model_dir, resume_download=True)

        print(f"[YTThumb] 🤖 Loading {model_id} on CPU (float32, steps={steps})...")
        try:
            pipe = StableDiffusionPipeline.from_pretrained(
                local_model_dir, torch_dtype=torch.float32, local_files_only=True,
                safety_checker=None, requires_safety_checker=False
            )
        except Exception as e:
            print(f"[YTThumb] ⚠️ Safetensors load failed ({e}), falling back to bin...")
            pipe = StableDiffusionPipeline.from_pretrained(
                local_model_dir, torch_dtype=torch.float32, local_files_only=True,
                safety_checker=None, requires_safety_checker=False, use_safetensors=False
            )

        pipe.to("cpu")
        pipe.enable_attention_slicing()
        pipe.enable_sequential_cpu_offload()

        img = pipe(prompt, negative_prompt="ugly, blurry, text, watermark, lowres, deformed",
                   num_inference_steps=steps, guidance_scale=cfg.get("cfg_scale", 7.5)).images[0]

        tmp_path = Path("/tmp") / f"cf2_thumb_{int(time.time())}.jpg"
        img.save(tmp_path, "JPEG", quality=95)
        del pipe, img
        return str(tmp_path)

    def _extract_countries(self, topic: str) -> tuple:
        match = re.search(r'(.+?)\s+vs\.?\s+(.+?)(?:\s*[:?]|$)', topic, re.IGNORECASE)
        return (match.group(1).strip(), match.group(2).strip()) if match else ("Country A", "Country B")

    def _generate_hook(self, topic: str) -> str:
        stop = {"vs","and","the","is","are","which","system","better","for","in"}
        strong = [w for w in re.findall(r'\b[A-Za-z]{4,}\b', topic) if w.lower() not in stop]
        return f"{strong[0].upper()} VS {strong[1].upper()}" if len(strong)>=2 else "THE TRUTH"

    def _save_image(self, source: str, jpg_path: Path, png_path: Path):
        jpg_path.parent.mkdir(parents=True, exist_ok=True)
        if source.startswith("http"):
            resp = requests.get(source, timeout=20)
            resp.raise_for_status()
            jpg_path.write_bytes(resp.content)
        else:
            from shutil import copy2; copy2(source, jpg_path)
        try:
            from PIL import Image; Image.open(jpg_path).save(png_path, format="PNG")
        except Exception as e:
            print(f"[YTThumb] ⚠️ PNG backup skipped: {e}")
