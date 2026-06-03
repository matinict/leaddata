"""
yt_shared.py — Shared helpers for the YouTube metadata tool suite.
Imported by: yt_narration_tool.py, yt_metadata_tool.py, yt_thumbnail_tool.py
"""
import json
import time
import urllib.request
import urllib.parse


# ── Language config ───────────────────────────────────────────────────────────

def _load_lang_config():
    """Load language list from data/lang.json, sorted by rank.
    Falls back to a minimal hardcoded list if the file is missing.
    """
    import pathlib
    _here = pathlib.Path(__file__).parent
    _candidates = [
        _here / "data" / "lang.json",
        pathlib.Path("data/lang.json"),
    ]
    for _p in _candidates:
        if _p.exists():
            try:
                with open(_p, encoding="utf-8") as _f:
                    _cfg = json.load(_f)
                _langs = sorted(_cfg["languages"], key=lambda x: x["rank"])
                _codes = [l["code"] for l in _langs]
                _names = {l["code"]: l["name"] for l in _langs}
                _yt_map = {l["code"]: l["yt_code"] for l in _langs}
                for alias, target in _cfg.get("aliases", {}).items():
                    if alias not in _names:
                        _names[alias] = _names.get(target, target)
                    if alias not in _yt_map:
                        _yt_map[alias] = _yt_map.get(target, target)
                print(f"[LangConfig] Loaded {len(_codes)} languages from {_p}")
                return _codes, _names, _yt_map
            except Exception as _e:
                print(f"[LangConfig] Failed to load {_p}: {_e} — using fallback")
                break
    print("[LangConfig] data/lang.json not found — using built-in fallback (top 10)")
    _codes = ['es', 'ar', 'pt', 'id', 'tr', 'vi', 'fr', 'ru', 'hi', 'ko']
    _names = {
        'es': 'Spanish', 'ar': 'Arabic', 'pt': 'Portuguese', 'id': 'Indonesian',
        'tr': 'Turkish', 'vi': 'Vietnamese', 'fr': 'French', 'ru': 'Russian',
        'hi': 'Hindi', 'ko': 'Korean',
    }
    _yt_map = {c: c for c in _codes}
    return _codes, _names, _yt_map


LANGUAGES, LANG_NAMES, _LANG_YT_MAP = _load_lang_config()


# ── Translation helper ────────────────────────────────────────────────────────
def google_translate(text: str, dest: str, retries: int = 3, _depth: int = 0, _max_depth: int = 5) -> str:
    """
    Translate text using Google Translate API with safe recursion handling.
    """
    if not text or not text.strip():
        return text

    # ── Recursion depth guard ──────────────────────────────────────────────
    if _depth >= _max_depth:
        print(f"[Translate] ⚠️  Max recursion depth ({_max_depth}) reached — returning partial")
        return text[:4000] if len(text) > 4000 else text

    # ── Chunk long text safely ─────────────────────────────────────────────
    if len(text) > 4000:
        # Strategy 1: Split by paragraphs
        chunks = text.split("\n\n")
        if len(chunks) > 1 and all(len(c) <= 4000 for c in chunks):
            return "\n\n".join(google_translate(c, dest, retries, _depth + 1, _max_depth) for c in chunks)

        # Strategy 2: Split by sentences
        import re as _re
        sentences = _re.split(r'(?<=[.!?])\s+', text)
        if len(sentences) > 1 and all(len(s) <= 4000 for s in sentences):
            return " ".join(google_translate(s, dest, retries, _depth + 1, _max_depth) for s in sentences)

        # Strategy 3: Fixed-size chunks (fallback)
        chunk_size = 3500  # Leave margin for API overhead
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        return " ".join(google_translate(c, dest, retries, _depth + 1, _max_depth) for c in chunks)

    # ── API call with retry logic ──────────────────────────────────────────
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl={urllib.parse.quote(dest)}"
            f"&dt=t&q={urllib.parse.quote(text)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return " ".join(part[0] for part in data[0] if part[0])
            except Exception as e:
                if attempt < retries - 1:
                    time.sleep(1.5 * (attempt + 1))  # Exponential backoff
                else:
                    print(f"[Translate] Failed ({dest}): {e}")
                    return text
    except Exception as e:
        print(f"[Translate] Error ({dest}): {e}")
        return text

 
# ── YouTube video scraper (yt_id mode) ───────────────────────────────────────

def scrape_youtube_video_data(video_id: str, api_key: str = None) -> dict:
    """Fetch metadata + real CC transcript for a YouTube video ID."""
    import os, tempfile, glob as _glob

    api_key = api_key or os.environ.get('YOUTUBE_API_KEY', '')
    url = f"https://www.youtube.com/watch?v={video_id}"

    # ── Method 1: yt-dlp ─────────────────────────────────────────────────────
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get('title', f"YouTube Video {video_id}")
        description = info.get('description', '')
        tags = info.get('tags', []) or []
        chapters_raw = info.get('chapters', []) or []
        chapters_str = "\n".join(
            f"{int(c.get('start_time', 0) // 60):02d}:{int(c.get('start_time', 0) % 60):02d} {c.get('title', '')}"
            for c in chapters_raw
        ) if chapters_raw else "0:00 Introduction"

        transcript_text = ""
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                sub_opts = {
                    'quiet': True, 'no_warnings': True, 'skip_download': True,
                    'writesubtitles': True, 'writeautomaticsub': True,
                    'subtitleslangs': ['en', 'en-US', 'en-GB'],
                    'subtitlesformat': 'vtt',
                    'outtmpl': os.path.join(tmpdir, '%(id)s.%(ext)s'),
                }
                with yt_dlp.YoutubeDL(sub_opts) as ydl_sub:
                    ydl_sub.download([url])
                vtt_files = _glob.glob(os.path.join(tmpdir, '*.vtt'))
                if vtt_files:
                    import re as _re
                    raw = open(vtt_files[0], encoding='utf-8').read()
                    seen, clean_lines = set(), []
                    for line in raw.splitlines():
                        line = line.strip()
                        if not line or line.startswith(('WEBVTT', 'NOTE', 'STYLE')):
                            continue
                        if _re.match(r'^(Kind|Language|Position|Align|Line|Size)\s*:', line, _re.IGNORECASE):
                            continue
                        if _re.match(r'^\d{2}:\d{2}', line) or _re.match(r'^\d+$', line):
                            continue
                        line = _re.sub(r'<[^>]+>', '', line).strip()
                        if line and line not in seen:
                            seen.add(line)
                            clean_lines.append(line)
                    transcript_text = ' '.join(clean_lines)
                    print(f"[YTScrape] ✅ Real CC: {len(transcript_text)} chars")
        except Exception as e:
            print(f"[YTScrape] ⚠️  CC error: {e}")

        return {
            'title': title, 'description': description, 'tags': tags,
            'chapters': chapters_str, 'transcript': transcript_text,
            'existing_captions': [], 'source': 'yt-dlp',
        }
    except ImportError:
        print("[YTScrape] ℹ️  yt-dlp not installed")
    except Exception as e:
        print(f"[YTScrape] ⚠️  yt-dlp error: {e}")

    # ── Method 2: noembed ────────────────────────────────────────────────────
    try:
        req = urllib.request.Request(
            f"https://noembed.com/embed?url={urllib.parse.quote(url)}",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        title = data.get('title', f"YouTube Video {video_id}")
        author = data.get('author_name', '')
        return {
            'title': title, 'description': f"Video by {author}. Watch: {url}",
            'tags': ['youtube', 'video'], 'chapters': "0:00 Introduction",
            'transcript': '', 'existing_captions': [], 'source': 'noembed',
        }
    except Exception as e:
        print(f"[YTScrape] ⚠️  noembed error: {e}")

    # ── Method 3: oEmbed ─────────────────────────────────────────────────────
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/oembed?url={urllib.parse.quote(url)}&format=json",
            headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        title = data.get('title', f"YouTube Video {video_id}")
        return {
            'title': title, 'description': f"Watch: {url}",
            'tags': ['youtube', 'video'], 'chapters': "0:00 Introduction",
            'transcript': '', 'existing_captions': [], 'source': 'oEmbed',
        }
    except Exception as e:
        print(f"[YTScrape] ⚠️  oEmbed error: {e}")

    # ── Fallback ─────────────────────────────────────────────────────────────
    return {
        'title': f"YouTube Video {video_id}",
        'description': f"Watch: https://youtu.be/{video_id}",
        'tags': ['youtube', 'video'], 'chapters': "0:00 Introduction",
        'transcript': '', 'existing_captions': [], 'source': 'fallback',
    }


# ── Format helpers ────────────────────────────────────────────────────────────

PIPELINE_TOKENS = {"debate", "animation", "yt_id", "ytid"}
REAL_FORMATS = {"HD", "2K", "4K", "8K", "Shorts", "ShortsHD", "Shorts4K"}


def parse_video_formats(video_formats, video_style=None):
    """Normalize video_formats list and inject style pipeline tokens."""
    import re as _re
    if not video_formats:
        video_formats = ["HD"]
    elif isinstance(video_formats, str):
        video_formats = [v.strip() for v in _re.findall(r"[A-Za-z0-9]+", video_formats)
                         if v not in ("true", "false", "null", "list")]
    video_formats = [("yt_id" if f == "ytid" else f)
                     for f in video_formats if f in (PIPELINE_TOKENS | REAL_FORMATS)] or ["HD"]

    if video_style:
        style_list = [video_style] if isinstance(video_style, str) else list(video_style)
        style_tokens = [("yt_id" if s.strip().lower() == "ytid" else s.strip().lower())
                        for s in style_list if s.strip().lower() in PIPELINE_TOKENS]
        for tok in style_tokens:
            if tok not in video_formats:
                video_formats = [tok] + video_formats
        if style_tokens:
            print(f"[YTShared]   video_style={style_tokens} → formats: {video_formats}")

    return video_formats


def get_animation_formats(animation_video_formats, video_formats):
    """Resolve the real (non-pipeline) format names for per-fmt output."""
    if not animation_video_formats:
        return [f for f in video_formats if f in REAL_FORMATS] or ["HD"]
    return [f for f in animation_video_formats if f in REAL_FORMATS] or ["HD"]
