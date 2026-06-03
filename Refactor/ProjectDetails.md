CF2 (CrewAI Flow Factory v2)
TYPE: Automated AI Video Content Generation & Publishing Pipeline
LICENSE/SCOPE: Internal Tool / Production-Ready Prototype


OVERVIEW

CF2 is an end-to-end, multi-agent AI pipeline designed to automatically research viral topics, generate comparative time-series data, craft structured debate content, render professional visualization videos with synchronized TTS narration, optimize SEO metadata and thumbnails, and publish directly to YouTube, Facebook, and cross-platform social networks.

Built on the CrewAI framework and orchestrated by a custom flow controller, the system operates as a modular, sequential pipeline where each "Unit" specializes in a distinct production phase. The architecture emphasizes determinism, smart skip/resume capabilities, workspace isolation, and credential-secured publishing, making it suitable for automated YouTube channel operations and data-driven content farms.


ARCHITECTURE & EXECUTION FLOW

The system follows a three-tier architecture:
1. CLI & Config Layer: Parses command-line arguments, loads JSON/YAML profiles, flattens nested configuration into flat template variables, and resolves workspace directories.
2. Flow Controller Layer (flow_controller.py): Acts as the central orchestrator. Manages execution order, topic resolution, metadata tracking, and unit-by-unit handoff using CrewAI's Flow API. Handles graceful interruption and resume from last completed step.
3. CrewAI Registry Layer (crew.py + agents.yaml + tasks.yaml): Defines all agents, their roles/goals, assigned tools, task dependencies, context routing, and strict output formatting rules. Tools are registered here; execution flow is managed externally.

Pipeline Execution Order:
Unit-Scout → Unit-Data → Unit-Debate → Unit-Definition → Unit-Animation → Unit-Comparison → Unit-Publisher → Unit-Advertise

Each unit runs independently but passes artifacts through a shared workspace (`output/{slug}/`). Tasks enforce strict input/output contracts, and tools handle file I/O, media rendering, and API interactions.


CORE MODULES (PIPELINE UNITS)

[Unit-Scout]
Discovers and ranks trending topics across configured platforms (YouTube, Reddit, X, LinkedIn). Outputs a prioritized topic queue and memory file for downstream consumption. Supports web search toggle, virality scoring, and force-refresh modes.

[Unit-Data]
Researches multi-entity time-series data (5-10 items tracked over time). Generates deterministic CSV files with strict naming conventions. Produces structured topic definitions (WHAT IS / WHY / KEY TERMS / TIMELINE) ready for video rendering.

[Unit-Debate]
Generates full-length and short-form (Shorts) debate scripts. Produces PROPOSITION, OPPOSITION, and VERDICT markdown files with strict word limits and header formatting. Includes a compression tool to auto-generate mobile-optimized variants (-m.md).

[Unit-Definition]
Converts topic definitions into scrolling text videos. Supports multiple output formats and integrates watermarking, TTS narration, and CC generation. Skips automatically if disabled in config.

[Unit-Animation]
Produces bar chart race animations, general data visualizations, and branded intro clips. Generates synchronized TTS audio, merges audio with video streams using FFmpeg, and concatenates segments into final polished outputs. Handles label mapping for compact naming.

[Unit-Comparison]
(Placeholder/Missing) Listed in pipeline order but currently lacks agents, tasks, or tool registrations. Requires scope definition or removal.

[Unit-Publisher]
Handles secure uploads to YouTube and Facebook. Supports multi-format publishing (Shorts → Reels, HD → Video). Manages OAuth2 authentication, privacy settings, CC subtitle uploads, and metadata localization injections. Includes smart skip via upload logs.

[Unit-Advertise]
Distributes published content across social platforms (LinkedIn, X, Facebook). Attaches HD thumbnails, formats platform-specific posts, supports dry-run mode, and enables post scheduling. Reads upload logs to extract live video URLs.


KEY FEATURES & CAPABILITIES

- Smart Skip & Resume: Per-task SKIP guards, per-unit force flags, and upload/merge log checks prevent redundant processing.
- Multi-Format Output: Native support for Shorts (9:16), HD (16:9), 2K, and 4K resolutions.
- Deterministic File Management: Strict naming conventions, flat directory structures, and automatic workspace isolation per topic/slug.
- TTS & Audio Sync: Edge-TTS integration with chunked generation, FFmpeg concatenation, and precise audio-video synchronization.
- Debate Video Engine: Bottom-to-top streaming text videos, dynamic ad insertion, topic overlays, and full subtitle rendering. Includes an advanced 3D variant (debate_video3d.py) with overlay banners and subtitle pills.
- SEO & Packaging Automation: Auto-generates titles, descriptions, tags, chapters, closed captions, and multi-language translations. Produces PNG/JPG thumbnails optimized per format.
- Credential-Secured Publishing: OAuth2 and Graph API integration for YouTube and Facebook. Auto-templates missing credentials and validates before upload.
- CLI-Driven Control: Full argument parsing, profile switching, unit-level execution, force overrides, and status reporting.


TECHNICAL STACK & DEPENDENCIES

- Core Framework: Python 3.10+, CrewAI (Agents, Tasks, Crew, Flow)
- Media Processing: FFmpeg (concat, audio extraction, muxing), OpenCV (frame rendering), Pillow (image/text overlay, thumbnail generation)
- Audio/TTS: edge-tts, async chunking, FFmpeg audio filters
- Data & Config: Pydantic (input validation), JSON/YAML config loading, CLI argument parsing
- APIs: YouTube Data API v3, Facebook Graph API (Reels/Video), Social Platform APIs (LinkedIn/X)
- Orchestration: Custom Flow Controller with meta tracking, workspace resolution, and config flattening


CONFIGURATION & WORKSPACE MANAGEMENT

- Configuration: Nested YAML/JSON profiles flattened into a single top-level dictionary before pipeline kickoff. Safe defaults injected for all template variables.
- Workspace Structure: `output/{slug}/` contains all artifacts. Debate files in `debate/`, metadata in `YT/[style]/[fmt]/`, uploads logged in `upload_log.json`.
- Meta Tracking: `meta.json` records `created_at`, `updated_at`, `topic`, and `slug`. Enables resume and status queries.
- Template Variables: Over 50 configurable parameters including FPS, audio speed, watermark settings, CC/MD language counts, TTS engine/voices, debate character limits, and publishing flags.


CURRENT STATUS & DEVELOPMENT ROADMAP

[IMPLEMENTED] Core orchestration, 7/8 pipeline units, all packaging/publishing tools, smart skip/resume, workspace tracking, CLI interface, multi-format rendering, TTS sync, debate script generation, metadata/thumbnail automation.
[TOOL READY, NOT WIRED] `debate_video3d.py` is fully functional with dynamic ad support, topic overlay banners, subtitle rendering, and audio sync, but not yet imported or assigned to an agent in `crew.py`.
[PENDING] `Unit-Comparison` module requires scope definition or pipeline removal.
[RECOMMENDED NEXT STEPS]
  1. Wire `DebateVideo3dTool` into crew.py or create a dedicated agent.
  2. Define or remove `Unit-Comparison` from `PIPELINE_ORDER`.
  3. Add CLI credential initialization command.
  4. Implement explicit task-to-task data routing via `flow_controller.py` state.
  5. Add retry/backoff for TTS and FFmpeg subprocess calls.


USE CASES & TARGET AUDIENCE

- Automated YouTube channels focused on data comparisons, tech debates, and trending analysis.
- Content agencies requiring high-volume, SEO-optimized video output with minimal manual intervention.
- Researchers/educators needing rapid generation of time-series visualizations and structured debate content.
- Social media managers requiring cross-platform publishing, scheduling, and thumbnail optimization.


END OF DESCRIPTION
