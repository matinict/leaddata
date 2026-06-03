# data_schema.json - Clips Folder Documentation Added

## What Was Added

A new `_clips_folder_structure` section documenting the complete debate video clips folder structure.

## Location in Schema

Added after `debate_background_prompt` in the `debate_config` section.

## Contents

### Folder Structure (00-18)
Complete mapping of numbered folders to config keys:

- **00_intro**: intro.mkv, intro_s.mkv → Channel welcome
- **01_ad1**: Bji000.mkv, Bji000_s.mkv → Pre-debate sponsor
- **02_p0 to 09_c3**: Debate arguments (Shorts max)
- **10_p4 to 13_c5**: Extended arguments (HD only)
- **14_sum**: jMfl.mkv, jMfl_s.mkv → SUMMARY (Male Judge)
- **15_aly**: jFfl.mkv, jFfl_s.mkv → ANALYSIS (Female Judge)
- **16_ad2**: Bji1.mkv, Bji1_s.mkv → Post-debate sponsor
- **17_win**: Multiple variants → DECISION (Chief Judge)
- **18_sbs**: sub.mkv, sub_s.mkv → Subscribe CTA

### Key Information

1. **File Naming Convention**
   - HD: `filename.mkv`
   - Shorts: `filename_s.mkv`
   - Static frames: `filename.png`

2. **Folder Lookup**
   - With `_folder_prefix: true`, scans for folders ending with `_{key}`
   - Example: key "sum" finds folder "14_sum"
   - Falls back to `assets/clips/{key}/` if not found

3. **Voice Mapping**
   - sum → judge_m (Male/Liam)
   - aly → judge_f (Female/Clara)
   - win → decide (Chief/Christopher)

4. **Pipeline Usage**
   - Shorts: p0-p3, c0-c3 (4 arguments max per side)
   - HD: p0-p5, c0-c5 (6 arguments max per side)

## Usage

Reference this section when:
- Setting up new clips folders
- Understanding folder naming requirements
- Configuring debate_3d_clips paths
- Debugging missing clip errors
