"""
unit_publisher.py — Distribution Layer (Rule 7)

Responsibility: Upload finished content to YouTube, Facebook, and social
platforms. That is ALL this unit does.

Packaging (metadata, thumbnails, narration) is Unit-Packaging's job.
If those files don't exist, this unit warns the operator and exits cleanly
rather than generating them itself — that would violate Rule 18 (unit
independence) and Rule 6 (consumer units never regenerate content).

Why uploads call tools directly instead of going through LLM agents:
  Upload operations are fully deterministic — fixed parameters in, API
  call out, result string back. There is zero reasoning for an LLM to
  contribute. Routing uploads through an agent introduces hallucination
  risk: the agent may mutate output_dir, return the raw tool-call JSON
  instead of the result, or fabricate a skip. Calling tool._run(...)
  directly is faster, cheaper, and guaranteed correct (Rule 16).
"""
from pathlib import Path
from cf2.meta import mark_subtask

import json as _json
# ── Dependency check ──────────────────────────────────────────────────────

def _check_packaging_deps(workspace: Path, inputs: dict) -> bool:
    """
    Verify that Unit-Packaging produced the files this unit needs.
    Returns True if all required files exist, False otherwise.
    Prints a clear operator message listing what is missing.
    """
    video_formats = inputs.get("video_formats", ["Shorts", "HD"])
    video_style   = inputs.get("video_style", ["debate"])
    style         = video_style[0] if isinstance(video_style, list) else video_style
    missing       = []

    for fmt in video_formats:
        # Metadata file — required for YouTube title/description
        md_path = workspace / "debate" / "YT" / fmt / "MD" / "en.json"
        if not md_path.exists():
            missing.append(str(md_path))

    if missing:
        print("\n⚠️  Unit-Publisher: required packaging files not found.")
        print("   Run Unit-Packaging first, or enable it in your config:")
        print('   "Unit-Packaging": true')
        print("   Missing:")
        for m in missing:
            print(f"     • {m}")
        return False
    return True


# ── Upload helpers (direct tool calls — no LLM) ───────────────────────────

def _run_yt_upload(inputs: dict) -> str:
    """
    Call YTUploadTool directly with parameters from inputs.
    No LLM agent involved — output_dir is guaranteed to be the workspace
    root, not a hallucinated subdirectory path.
    """
    from cf2.tools.publisher_yt_upload import YTUploadTool
    yt_cfg = inputs.get("publisher_config", {}).get("yt_upload_config", {})
    result = YTUploadTool()._run(
        topic                = inputs["topic"],
        output_dir           = inputs["output_dir"],
        video_formats        = inputs.get("video_formats", ["Shorts", "HD"]),
        upload_youtube_video = yt_cfg.get("upload_youtube_video", False),
        channel              = inputs.get("channel", "PlayOwnAi"),
        privacy_status       = yt_cfg.get("upload_privacy", "private"),
        category_id          = yt_cfg.get("upload_category_id", "27"),
        upload_cc            = yt_cfg.get("upload_cc", True),
        upload_cc_lang       = str(yt_cfg.get("upload_cc_lang", "0")),
        upload_md_lang       = str(yt_cfg.get("upload_md_lang", "0")),
        notify_subscribers   = yt_cfg.get("upload_notify_subscribers", False),
        client_secrets_file  = yt_cfg.get("upload_client_secrets_file", ""),
        token_file           = yt_cfg.get("upload_token_file", ""),
        dry_run              = yt_cfg.get("upload_dry_run", False),
    )
    print(result)
    return result


def _run_fb_upload(inputs: dict) -> str:
    """Call FBUploadTool directly. No LLM agent."""
    from cf2.tools.publisher_fb_upload import FBUploadTool
    fb_cfg = inputs.get("publisher_config", {}).get("fb_upload_config", {})
    result = FBUploadTool()._run(
        topic                 = inputs["topic"],
        output_dir            = inputs["output_dir"],
        video_formats         = inputs.get("video_formats", ["Shorts", "HD"]),
        upload_facebook_video = fb_cfg.get("upload_facebook_video", False),
        channel               = inputs.get("channel", "PlayOwnAi"),
        privacy_status        = fb_cfg.get("privacy_status", "SELF"),
        credentials_file      = fb_cfg.get("credentials_file", ""),
    )
    print(result)
    return result


def _run_social_share(inputs: dict) -> str:
    """Call SocialShareTool directly. No LLM agent."""
    from cf2.tools.advertise_social_share import SocialShareTool
    result = SocialShareTool()._run(
        topic                = inputs["topic"],
        filename             = inputs.get("filename", ""),
        output_dir           = inputs["output_dir"],
        social_share_enabled = inputs.get("social_share_enabled", False),
        social_platforms     = inputs.get("social_platforms", []),
        video_formats        = inputs.get("video_formats", ["Shorts", "HD"]),
        channel              = inputs.get("channel", "PlayOwnAi"),
        website              = inputs.get("website", ""),
        image_path           = "",        # tool auto-detects from output_dir
        start_year           = inputs.get("start", 2000),
        end_year             = inputs.get("end", 2024),
        video_url            = "",
        dry_run              = inputs.get("social_share_dry_run", False),
        schedule_post        = inputs.get("schedule_post", False),
        schedule_datetime    = inputs.get("schedule_datetime", ""),
        schedule_timezone    = inputs.get("schedule_timezone", "UTC"),
    )
    print(result)
    return result


# ── Main entry point ──────────────────────────────────────────────────────

def run(topic: str, workspace: Path, inputs: dict, force: bool = False) -> str:
    """
    Unit-Publisher entry point. Called only by executor.py (Rule 21).

    This unit does exactly three things, and only if enabled:
      1. Upload to YouTube   (if yt_upload=true)
      2. Upload to Facebook  (if fb_upload=true)
      3. Post to social      (if social_share=true)

    It does NOT run packaging. If metadata/thumbnail files are missing,
    it warns the operator to enable Unit-Packaging and exits cleanly.
    """
    # ── Resolve workspace paths once — never modified after this point ────
    topic_dir            = workspace if isinstance(workspace, Path) else Path(workspace)
    inputs["output_dir"] = str(topic_dir)
    inputs["filename"]   = inputs.get("_slug", topic_dir.name)
    inputs["topic"]      = topic

    print(f"\n📦  Unit-Publisher | {topic}")
    print(f"   📁 Workspace: {topic_dir}")

    # ── Determine which upload tasks are enabled ───────────────────────────
    pub_cfg      = inputs.get("publisher_config", {})
    # Safety: check if debate completed successfully
    meta_file = topic_dir / "meta.json"
    if meta_file.exists():
        meta = _json.loads(meta_file.read_text())
        debate_status = meta.get("status", {}).get("Unit-Debate", "pending")
        if debate_status not in ("done", "skipped"):
            msg = f"❌ Unit-Publisher: Unit-Debate is '{debate_status}'. Aborting."
            print(msg)
            raise RuntimeError(msg)

    pub_cfg      = inputs.get("publisher_config", {})
    do_yt_upload = inputs.get("publisher_config", {}).get("yt_upload", False)
    do_fb_upload = pub_cfg.get("fb_upload", False)

    do_social    = inputs.get("social_share", False)

    enabled = []
    if do_yt_upload: enabled.append("YT upload")
    if do_fb_upload: enabled.append("FB upload")
    if do_social:    enabled.append("social share")

    if not enabled:
        msg = (
            "⏭️  Unit-Publisher: no upload tasks enabled.\n"
            "   To activate: set yt_upload=true / fb_upload=true / social_share=true"
        )
        print(msg)
        return msg

    print(f"   🚀 Starting: {', '.join(enabled)}")

    # ── Guard: packaging files must exist before uploading ─────────────────
    if do_yt_upload and not _check_packaging_deps(topic_dir, inputs):
        return (
            "❌ Unit-Publisher: upload aborted — packaging files missing.\n"
            '   Enable Unit-Packaging: set "Unit-Packaging": true and re-run.'
        )

    # ── Execute uploads directly — no LLM agents ──────────────────────────
    results = []

    if do_yt_upload:
        print("\n📤  YouTube Upload")
        results.append(_run_yt_upload(inputs))

    if do_fb_upload:
        print("\n📤  Facebook Upload")
        results.append(_run_fb_upload(inputs))

    if do_social:
        print("\n📣  Social Share")
        results.append(_run_social_share(inputs))

    # Update meta.json with per-platform status
    if do_yt_upload:
        mark_subtask(topic_dir, "Unit-Publisher", "yt_upload", "done")
    if do_fb_upload:
        mark_subtask(topic_dir, "Unit-Publisher", "fb_upload", "done")
    if do_social:
        mark_subtask(topic_dir, "Unit-Publisher", "social_share", "done")

    return "\n".join(results)
