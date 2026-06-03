**Exactly right.** Crop values should be **per-format**, not global.

---

### Revised concept

```json
"video_formats": {
  "HD": {
    "crop": {
      "top": 80,
      "bottom": 80,
      "left": 360,
      "right": 0
    },
    "resolution": "1920x1080"
  },
  "Shorts": {
    "crop": {
      "top": 80,
      "bottom": 80,
      "left": 600,
      "right": 600
    },
    "resolution": "1080x1920",
    "blur_pad": true
  }
}
```

Shorts crops **much more left-right** to get a narrow tall content area → then blur-pads top/bottom to fill 9:16.

---

### Pipeline per format

```
source_video.mp4
    ↓
    ├── HD format
    │     crop(left=360, right=0) → scale 1920x1080 → dubbed_HD.mp4
    │
    └── Shorts format
          crop(left=600, right=600) → scale 1080x? → blur_pad to 1080x1920 → dubbed_Shorts.mp4
```

---

### Service stays clean

```
CropService.process(video, format_cfg)
    → reads crop values from format_cfg
    → applies crop → scale → pad in one FFmpeg call
    → smart skip if output exists
```

**One FFmpeg call per format. No intermediate files.**

---

Smart Auto-Crop for Shorts
When auto_crop: true, converting landscape → vertical automatically centers on the middle 55% of the frame (where speakers typically appear), avoiding empty head/footroom.
