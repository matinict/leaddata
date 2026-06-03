"""subUnitPublish: Optimize metadata for long-form/podcast platforms"""
from pathlib import Path

def run(podcast_dir: Path, topic: str, inputs: dict) -> str:
    """Re-use existing YT/FB tools with podcast-optimized metadata"""
    audio = podcast_dir / "audio.mp3"
    video = podcast_dir / "video.mp4"

    if not audio.exists():
        return "⏭️ Skipped — no audio to publish"

    # Prepare podcast-specific metadata
    podcast_meta = {
        "title": f"🎙️ {topic} | AI Explained Podcast",
        "description": f"Deep dive into {topic}. Full transcript & sources: {inputs.get('website', '')}",
        "tags": ["podcast", "AI", topic, "tech debate", "learning"],
        "is_podcast": True
    }

    # Hand off to existing publisher tools
    # from cf2.tools.packaging_yt_metadata import run as yt_meta_tool
    # yt_meta_tool(topic, inputs, overrides=podcast_meta)

    return "✅ Podcast metadata prepared for publisher pipeline"
