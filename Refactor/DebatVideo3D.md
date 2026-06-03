


# Write ONLY the raw key (no quotes, no prefix, no newline)
echo -n "sk-239e9cf2fd5d416eac0ce39492d7619d" > .runtime/secrets/dashscope_key.txt

# Verify
cat .runtime/secrets/dashscope_key.txt
# Should output EXACTLY: sk-239e9cf2fd5d416eac0ce39492d7619d




# HD2 Shorts
ffmpeg -i jCfl.mkv -filter_complex \
"[0:v]setpts=0.6667*PTS,split=2[v0][v1]; \
 [v0]scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2,boxblur=40:12,crop=1080:1920[bg]; \
 [v1]scale=1080:-2:flags=lanczos[fg]; \
 [bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1[outv]; \
 [0:a]atempo=1.5[outa]" \
-map "[outv]" -map "[outa]" \
-c:v libx264 -crf 18 -preset medium \
-c:a aac -b:a 128k \
jCfl_s.mkv

# Center Crop HD(1920x1080) into a Short/Reel format
ffmpeg -i nwin.mkv -vf "yadif,scale=w=-1:h=1920,crop=1080:1920" -c:a copy nwin_sh.mkv  
#ffmpeg -i jf1_fl.mkv -vf "yadif,scale=w=-2:h=1920,crop=1080:1920:iw-1080:0" -c:a copy -t 5 preview_right.mkv
#ffmpeg -i jf1_fl.mkv -vf "yadif,scale=w=-2:h=1920,crop=1080:1920:(iw-1080)/1.2:0" -c:a copy jf1_fl_right_focus.mkv

# Blurred Background HD (1920x1080) into a Short/Reel format
ffmpeg -i sum.mkv -lavfi "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,boxblur=20:10[bg];[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2" -c:a copy sum_sh.mkv


# Letterbox HD (1920x1080) into a Short/Reel format
#ffmpeg -i jf1_fl.mkv -vf "yadif,scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" jf1_fl_letterbox.mp4


# Pro Reverse
ffmpeg -i outputHD1.mp4 -vf "yadif,reverse" -af "areverse" -pix_fmt yuv420p outputHD1Rev.mp4

ffmpeg -i outputHD1.mkv -vf "yadif,reverse" -af "areverse" -pix_fmt yuv420p outputHD1Rev.mkv
ffmpeg -i outputHD2.mkv -vf "yadif,reverse" -af "areverse" -pix_fmt yuv420p outputHD2Rev.mkv


# Speed Up (Fit 3:45 into 2:59)
ffmpeg -i 360Debate_ChinaTrappingDeveloping_Shorts_En.mp4 -filter_complex "[0:v]setpts=0.8*PTS[v];[0:a]atempo=1.30[a]" -map "[v]" -map "[a]" output_fast.mp4

ffmpeg -i 360Debate_RussiaEconomyDestroyed_Shorts_En.mp4 -filter_complex "[0:v]setpts=0.7955*PTS[v];[0:a]atempo=1.257[a]" -map "[v]" -map "[a]" 360Debate_RussiaEconomyDestroyed_Shorts.mp4


## MakeHD:

ffmpeg -i a_3D_animation_style,_.mp4 -vf "scale=1920:-1,crop=1920:1080" -c:a copy outputHD1.mp4
ffmpeg -i a_3D_animation_style2.mp4 -vf "scale=1920:-1,crop=1920:1080" -c:a copy outputHD2.mp4

ffmpeg -i grok-imagine-video-720p_a_Create_a_12-second,_.mp4 -vf "scale=1920:-1,crop=1920:1080:(in_w-1920)/2:(in_h-1080)/2" -c:a copy BjiHD01.mp4


# Shorts Convert to faster/Speed up Duration reduce:
ffmpeg -i 360Debate_ChinaTrappingDeveloping_Shorts_En.mp4 -filter_complex "[0:v]setpts=0.72*PTS[v];[0:a]atempo=1.38[a]" -map "[v]" -map "[a]" 360Debate_ChinaTrappingDeveloping_Shorts.mp4

# HD2Short:
ffmpeg -i pro1_fl.mkv -filter_complex \
"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,boxblur=40:12,crop=1080:1920[bg]; \
 [0:v]scale=1080:-1:flags=lanczos[fg]; \
 [bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1" \
-c:v libx264 -crf 18 -preset medium -c:a aac -b:a 128k \
pro1_fl_short.mkv

# HD2Short with reduce time:

ffmpeg -i tr1ly.mkv -filter_complex \
"[0:v]setpts=PTS/1.5,split=2[v0][v1]; \
 [v0]scale=1080:1920:force_original_aspect_ratio=increase,boxblur=40:12,crop=1080:1920[bg]; \
 [v1]scale=1080:-1:flags=lanczos[fg]; \
 [bg][fg]overlay=(W-w)/2:(H-h)/2:shortest=1" \
-c:v libx264 -crf 18 -preset medium \
-filter:a "atempo=1.2" -c:a aac -b:a 128k \
tr1ly_s.mkv


matin@mhpz:/var/POAi/CrewAiFlow/cf2$ tree data/img/
data/img/
├── hd_Stage1920x1080.jpg
├── short_Stage1080x1920.jpg


3. Speaking Text like subtitles will be top only 2/3 line at time of speak










cd /var/POAi/CrewAiFlow/cf2
uv run python -m cf2.main --topic "Mastercard’s AI payment demo points to agent-led commerce" --unit Unit-Debate --force









uv run python -m cf2.main --topic "Mastercard’s AI payment demo points to agent-led commerce" --unit Unit-Debate --force











## 📊 video3d ARCHITECTURE AT A GLANCE

```
                       FLOW CONTROLLER
                              │
                              ▼
                         UNIT-DEBATE
                       (checks config)
                              │
                ┌─────────────┴─────────────┐
                │                           │
          ┌─────▼─────────┐            ┌───────▼──────┐
          │ debate_       │            │ debate_      │
          │ video.py      │            │ video3d.py   │
          │ (2D)~2k line  │            │(3d)~200Line  │
          └───────────────┘            └─────┬────────┘
                                             │
                               ┬─────────────┘
                         ┌─────▼────────────┐
                         │ SHARED SERVICES  │
                         ├──────────────────┤
                         │ tts_service      │
                         │ audio_service    │
                         │ md_parser        │
                         │ debate_parser    │
                         │ frame_renderer   │
                         └──────────────────┘
## 📂 FILE PLACEMENT

```
src/cf2/
├── core/
│   ├── services/
│   │   ├── tts_service.py        ← Place here
│   │   └── audio_service.py      ← Place here
│   ├── parser/
│   │   ├── md_parser.py          ← Place here
│   │   └── debate_parser.py      ← Place here
│   └── render/
│       └── frame_renderer.py     ← Place here
│
├── tools/
│   ├── debate_video.py           ← Place here (2D)
│   ├── debate_video_3d.py        ← Place here (3D)
│   ├── definition_video.py
│   └── ...
│
├── units/
│   └── unit_debate.py            ← Calls both tools based on config
│
└── flow_controller.py
```                         

HD version
You should now see individual block clips being generated:
_blk_p0 (PROPOSITION & OPENING STATEMENT) → AndrewNeural voice
_blk_c0 (OPPOSITION OPENING STATEMENT ) → AnaNeural voice  
_blk_p1 (Argument 1)       → AndrewNeural voice
_blk_c1 (Counter-Argument 1)   → AnaNeural voice
_blk_p2 (Argument 2)       → AndrewNeural voice
_blk_c2 (Counter-Argument 2)   → AnaNeural voice
_blk_p3 (Argument 3)       → AndrewNeural voice
_blk_c3 (Counter-Argument 3)   → AnaNeural voice
mod                    → ChristopherNeural voice


Short/Mini version
You should now see individual block clips being generated:
_blk_p0 (PRO opening) → AndrewNeural voice
_blk_c0 (CON opening) → AnaNeural voice  
_blk_p1 (Arg 1)       → AndrewNeural voice
_blk_c1 (C-Arg 1)   → AnaNeural voice
_blk_p2 (Arg 2)       → AndrewNeural voice
_blk_c2 (C-Arg 2)   → AnaNeural voice
_blk_p3 (Arg 3)       → AndrewNeural voice
_blk_c3 (C-Arg 3)   → AnaNeural voice
mod                    → ChristopherNeural voice


Opp:  

C-Arg 1:  
C-Arg 2:  
C-Arg 3:


bad Voice tone
"edge_tts_voices": {
  "propose": { "edge_voice": "en-US-AndrewNeural" },
  "oppose": { "edge_voice": "en-US-AnaNeural" },
  "decide": { "edge_voice": "en-US-ChristopherNeural" }
},

Good Voice tone  we used another channel need alternative like that
"propose": { "edge_voice": "en-US-GuyNeural" },
"oppose": { "edge_voice": "en-US-AriaNeural" },
"decide": { "edge_voice": "en-GB-RyanNeural" }


uv run edge-tts --voice "en-US-RogerNeural" --text "That argument has no factual basis whatsoever." --write-media test_propose.mp3
uv run edge-tts --voice "en-US-MichelleNeural" --text "That argument has no factual basis whatsoever." --write-media test_oppose.mp3
uv run edge-tts --voice "en-US-ChristopherNeural" --text "That argument has no factual basis whatsoever." --write-media test_decide.mp3




Blender/Manim/Pillow-based animation based on your stack.

debate_video3d.py (orchestrator)
    ↓
1. parser/debate_parser.py
   - Read propose.md, oppose.md, decide.md
   - Split into lines
   - Return: [{"role": "propose", "text": "...", "duration": 3.5}, ...]

2. services/tts_service.py
   - Generate audio for each line (edge-tts, gtts, piper)
   - Return: audio segments + durations

3. services/audio_service.py
   - Concatenate audio segments
   - Add timing metadata
   - Return: final audio file + timings

4. render/frame_builder.py
   - For each line + timing:
     - Draw neon text frame
     - Apply layout (left/right/center)
   - Return: frame sequence

5. render/renderer.py
   - Encode frame sequence + audio → MP4
   - Return: debate_video3d_*.mp4








   debate_video3d.py (orchestrator)
       ↓
   1. parser/debate_parser.py
      - Read propose.md, oppose.md, decide.md
      - Split into lines
      - Return: [{"role": "propose", "text": "...", "duration": 3.5}, ...]

   2. services/tts_service.py
      - Generate audio for each line (edge-tts, gtts, piper)
      - Return: audio segments + durations

   3. services/audio_service.py
      - Concatenate audio segments
      - Add timing metadata
      - Return: final audio file + timings

   4. render/frame_builder.py
      - For each line + timing:
        - Draw neon text frame
        - Apply layout (left/right/center)
      - Return: frame sequence

   5. render/renderer.py
      - Encode frame sequence + audio → MP4
      - Return: debate_video3d_*.mp4
