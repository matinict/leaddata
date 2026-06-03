






















unit_debate.py (Orchestrator)
├─▶ subUnitDebateParser          → propose/oppose/decide.md → block_map.json
├─▶ subUnitDebateScoreboard      → block_map + scores.json → pipeline.json + scoreboard_clips.json
├─▶ subUnitDebateAudioBuilder    → pipeline.json + TTS config → audio_segments.json + .mp3 blocks
├─▶ subUnitDebateClipResolver    → pipeline + clip_config → clip_map.json + resolved_paths
├─▶ subUnitDebateVideoRenderer   → clip_map + audio + subtitles → silent_video.mp4
└─▶ subUnitDebateMerger          → concat + AV sync + post-process → final MP4





Unit-- How missing _s clips are handled
Classroom Code-level fallback in classroom_video_renderer.py — tries T1_s.mkv, falls back to T1.mkv automatically. No symlinks needed.
Debate Symlinks created manually in assets/debate/ — c0fl_s.mkv → c0fl.mkv etc.
Prodcast Symlinks created manually in assets/podcast/clips/ — same approach.

So Prodcast is not using Classroom's code-level fallback. It's relying on the symlinks you created last session.



matin@mhpz:/var/POAi/CrewAiFlow/cf2$ tree assets/
assets/
├── bubble
├── classroom
│   ├── clips
│   │   ├── 00_intro
│   │   │   └── Intro.mkv
│   │   ├── 01_ad1
│   │   │   ├── Bji3s.mkv
│   │   │   └── Bji3s_s.mkv
│   │   ├── 02_T1
│   │   │   └── T1.mkv
│   │   ├── 03_T2
│   │   │   └── T2F.mkv
│   │   ├── 04_S1
│   │   │   └── S1.mkv
│   │   ├── 05_S2
│   │   │   └── S2M.mkv
│   │   ├── 06_S3
│   │   │   └── S3F.mkv
│   │   ├── 07_S4
│   │   │   ├── S11R.mkv
│   │   │   └── S4F.mkv
│   │   ├── 08_S5
│   │   │   └── S5F.mkv
│   │   ├── 09_S6
│   │   │   └── S6.mkv
│   │   ├── 10_S7
│   │   │   └── S7.mkv
│   │   ├── 11_S8
│   │   │   └── S8.mkv
│   │   ├── 14_sum
│   │   │   └── T2F.mkv
│   │   ├── 16_ad2
│   │   │   ├── Bji1.mkv
│   │   │   ├── Bji1_s.mkv
│   │   │   ├── Bji4s.mkv
│   │   │   ├── try.mkv
│   │   │   └── try_s.mkv
│   │   ├── 17_end
│   │   └── 18_sbs
│   │       ├── sub.mkv
│   │       └── sub_s.mkv
│   └── cover.png

└── podcast
   ├── clips
   │   ├── 00_intro
   │   │   ├── int5s.mkv
   │   │   └── int7s.mkv
   │   ├── 01_ad1
   │   │   ├── Bji3s.mkv
   │   │   └── Bji3s_s.mkv
   │   ├── 02_p0
   │   │   ├── 360P.png
   │   │   ├── h01.mkv
   │   │   ├── Std15s.mkv
   │   │   └── std4s.mkv
   │   ├── 03_c0
   │   │   ├── g01.mkv
   │   │   ├── std4s.mkv
   │   │   └── Std7s.mkv
   │   ├── 04_p1
   │   │   └── h01.mkv
   │   ├── 05_c1
   │   │   ├── g01.mkv
   │   │   └── std4s.mkv
   │   ├── 06_p2
   │   │   └── h01.mkv
   │   ├── 07_c2
   │   │   ├── g01.mkv
   │   │   └── std4s.mkv
   │   ├── 08_p3
   │   │   └── h01.mkv
   │   ├── 09_c3
   │   │   ├── g01.mkv
   │   │   └── std4s.mkv
   │   ├── 10_p4
   │   │   ├── h01.mkv
   │   │   └── std4s.mkv
   │   ├── 11_c4
   │   │   ├── g01.mkv
   │   │   └── std4s.mkv
   │   ├── 12_p5
   │   │   ├── h01.mkv
   │   │   └── std4s.mkv
   │   ├── 13_c5
   │   │   ├── g01.mkv
   │   │   └── std4s.mkv
   │   ├── 16_ad2
   │   │   ├── Bji1.mkv
   │   │   ├── Bji1_s.mkv
   │   │   ├── Bji4s.mkv
   │   │   ├── try.mkv
   │   │   └── try_s.mkv
   │   └── 18_sbs
   │       ├── sub.mkv
   │       └── sub_s.mkv
   ├── cover.png
   └── cover_s.png
