

v["S1"] = "en-US-AnaNeural"        # young girl
v["S2"] = "en-US-AndrewNeural"     # young male  
v["S3"] = "en-US-EmmaNeural"       # young female
v["S4"] = "en-GB-RyanNeural"       # young UK male
v["S5"] = "en-US-AnaNeural"        # young girl (same as S1)
v["S6"] = "en-US-BrianNeural"      # young male
v["S7"] = "en-US-AvaNeural"        # young female
v["S8"] = "en-US-AndrewNeural"     # young male
















assets/classroom/clips/
├── 01_hook/
│   ├── 360C.png          ← classroom cover image
│   ├── 360C_s.png
│   └── T1.mkv
├── 02_T1/
│   ├── T1.mkv
│   └── T1_s.mkv
├── 03_T2/
│   ├── T2.mkv
│   └── T2_s.mkv
├── 04_S1/
│   ├── S1.mkv
│   └── S1_s.mkv
├── 05_S2/ ... 11_S8/     ← same pattern
├── 14_sum/
│   ├── sum.mkv
│   └── sum_s.mkv
├── 17_end/
│   ├── end.mkv
│   └── end_s.mkv
└── 18_sbs/
    ├── sub.mkv
    └── sub_s.mkv
mkdir -p assets/classroom/clips/{03_T2,04_S1,05_S2,06_S3,07_S4,08_S5,09_S6,10_S7,11_S8,14_sum,17_end}

Current config has `S4: "en-US-AndrewNeural"` — same as Teacher 1. Fix all students to unique voices, no overlap with teachers:

```json
"voice_mapping": {
  "teacher_1": "en-US-AndrewNeural",
  "teacher_2": "en-US-JennyNeural",
  "students": {
    "S1": "en-US-AnaNeural",
    "S2": "en-US-BrianNeural",
    "S3": "en-US-EmmaNeural",
    "S4": "en-US-RyanNeural",
    "S5": "en-US-MichelleNeural",
    "S6": "en-US-GuyNeural",
    "S7": "en-US-AriaNeural",
    "S8": "en-US-DavisNeural"
  }
}
```

**Full map — gender + voice, no teacher overlap:**

| Tag  |Gender| Voice               | Note |
|------|------|-----------------------|---|
| T1-M |Male  |`en-US-AndrewNeural` | Lead teacher |
| T2-F |Female|`en-US-JennyNeural` | Helper teacher |
---------------------------------------------------
| S1-F | F    |`en-US-AnaNeural` | Curious — child female |
| S2-M | M    |`en-US-BrianNeural` | Smart — adult-ish male |
| S3-F | F    |`en-US-EmmaNeural` | Confused — female |
| S4-M | M    |`en-US-RyanNeural` | Creative — male ✅ fixed |
| S5-F | F    |`en-US-MichelleNeural` | Funny — female |
| S6-M | M    |`en-US-GuyNeural` | Doubter — male |
| S7-F | F    |`en-US-AriaNeural` | Quiet — female |
| S8-M | M    |`en-US-DavisNeural` | Beginner — male |

All 8 students unique. Zero overlap with T1/T2.





`assets/classroom/` folder already exists (empty). I'll use **existing clips** from `assets/clips/` — reusing debate clips, zero new files, zero changes to any other module.**Speaker → existing file mapping:**

| Key | Folder resolved | File used | Visual |
|---|---|---|---|
| `T1` | `02_p0` | `p0fl.mkv` | Male proposer = Teacher 1 |
| `T2` | `03_c0` | `c0fl.mkv` | Female opposer = Teacher 2 |
| `S1` | `04_p1` | `arg1.mkv` | Student argues point 1 |
| `S2` | `05_c1` | `carg1.mkv` | Student counter-argues 1 |
| `S3` | `06_p2` | `arg2.mkv` | Student argues point 2 |
| `S4` | `07_c2` | `carg2.mkv` | Student counter-argues 2 |
| `S5` | `08_p3` | `arg3.mkv` | Student argues point 3 |
| `S6` | `09_c3` | `carg3.mkv` | Student counter-argues 3 |
| `S7` | `05_c1` | `adufl3s.mkv` | Audience/quiet student |
| `S8` | `09_c3` | `adufl3s.mkv` | Audience/beginner student |
| `hook` | `02_p0` | `360D.png`+`p0fl` | Opening frame |
| `sum` | `14_sum` | `sum.mkv`+`aly` | Quiz/recap |
| `end` | `17_win` | `cwin.mkv` | Closing |
| `sbs` | `18_sbs` | `sub.mkv` | Subscribe card |

Zero new files. Zero changes to `clips3d.json`, debate, or prodcast configs.
