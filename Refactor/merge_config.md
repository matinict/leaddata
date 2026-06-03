



"debate_3d_clips": {
  "Shorts": {
    "intro": { "path": "assets/clips/intro/intro_Shorts01_En.mkv", "text": "Welcome to the Debate!" },
    "ads_primary": { "path": "assets/clips/ads/ad1_Shorts.mp4", "text": "Sponsored by BrandX" },
    "subscribe": { "path": "assets/static/subscribe_Shorts.mp4", "text": "Subscribe for more debates!" }
  }
}

⚡ Execution Logic (must follow)

Order is NOT from JSON order, but enforced like:

intro
→ ads_primary
→ (p0 → c0)
→ (p1 → c1)
→ (p2 → c2)
→ (p3 → c3)
→ (p4 → c4) [HD only]
→ (p5 → c5) [HD only]
→ mod_analysis
→ mod_verdict
→ ads_secondary [HD only]
→ Shorts<179sc if [Optional]- clips not include



{
  "debate_3d_config": {
    "Shorts": {
      "intro": "debate/intro_Shorts_En_with_audio.mp4",
      "ads_primary": "assets/static/ads_primary_Shorts.mp4",

      "p0": "data/clip/short_pro_opening.mkv",
      "c0": "data/clip/short_opp_opening.mkv",

      "p1": "data/clip/short_pro_arg1.mkv",
      "c1": "data/clip/short_opp_carg1.mkv",

      "p2": "data/clip/short_pro_arg2.mkv",
      "c2": "data/clip/short_opp_carg2.mkv",

      "p3": "data/clip/short_pro_arg3.mkv",
      "c3": "data/clip/short_opp_carg3.mkv",
      "mod_analysis": "data/clip/short_judge_analysis.mkv", [Optional]
      "ads_secondary": "assets/static/ads_secondary_Shorts.mp4"
      "mod_verdict": "data/clip/short_judge_verdict_pro.mkv",

      "subscribe": "assets/static/subscribe_Shorts.mp4", [Optional]

    },

    "HD": {
      "intro": "debate/intro_HD_En_with_audio.mp4",
      "ads_primary": "assets/static/ads_primary_HD.mp4",

      "p0": "data/clip/hd_pro_opening.mkv",
      "c0": "data/clip/hd_opp_opening.mkv",

      "p1": "data/clip/hd_pro_arg1.mkv",
      "c1": "data/clip/hd_opp_carg1.mkv",

      "p2": "data/clip/hd_pro_arg2.mkv",
      "c2": "data/clip/hd_opp_carg2.mkv",

      "p3": "data/clip/hd_pro_arg3.mkv",
      "c3": "data/clip/hd_opp_carg3.mkv",

      "p4": "data/clip/hd_pro_arg3.mkv",
      "c4": "data/clip/hd_opp_carg3.mkv",

      "p5": "data/clip/hd_pro_arg3.mkv",
      "c5": "data/clip/hd_opp_carg3.mkv",

      "mod_analysis": "data/clip/hd_judge_analysis.mkv",
      "ads_secondary": "assets/static/ads_secondary_HD.mp4",
      "mod_verdict": "data/clip/hd_judge_verdict_pro.mkv",
      "subscribe": "assets/static/subscribe_HD.mp4"

    }
  }
}





{
  "merge_config": {
    "Shorts": {
      "intro": "debate/intro_Shorts_En_with_audio.mp4",
      "ads_primary": "assets/static/ads_primary_Shorts.mp4",

      "p0": "data/clip/short_pro_opening.mkv",
      "c0": "data/clip/short_opp_opening.mkv",

      "p1": "data/clip/short_pro_arg1.mkv",
      "c1": "data/clip/short_opp_carg1.mkv",

      "p2": "data/clip/short_pro_arg2.mkv",
      "c2": "data/clip/short_opp_carg2.mkv",

      "p3": "data/clip/short_pro_arg3.mkv",
      "c3": "data/clip/short_opp_carg3.mkv",

      "mod_analysis": "data/clip/short_judge_analysis.mkv",
      "mod_verdict": "data/clip/short_judge_verdict_pro.mkv",

      "ads_secondary": "assets/static/ads_secondary_Shorts.mp4" [Optional]
    },

    "HD": {
      "intro": "debate/intro_HD_En_with_audio.mp4",
      "ads_primary": "assets/static/ads_primary_HD.mp4",

      "p0": "data/clip/hd_pro_opening.mkv",
      "c0": "data/clip/hd_opp_opening.mkv",

      "p1": "data/clip/hd_pro_arg1.mkv",
      "c1": "data/clip/hd_opp_carg1.mkv",

      "p2": "data/clip/hd_pro_arg2.mkv",
      "c2": "data/clip/hd_opp_carg2.mkv",

      "p3": "data/clip/hd_pro_arg3.mkv",
      "c3": "data/clip/hd_opp_carg3.mkv",

      "p4": "data/clip/hd_pro_arg3.mkv",
      "c4": "data/clip/hd_opp_carg3.mkv",

      "p5": "data/clip/hd_pro_arg3.mkv",
      "c5": "data/clip/hd_opp_carg3.mkv",

      "mod_analysis": "data/clip/hd_judge_analysis.mkv",
      "mod_verdict": "data/clip/hd_judge_verdict_pro.mkv",

      "ads_secondary": "assets/static/ads_secondary_HD.mp4"
    }
  }
}


# For STATIC
"intro": "assets/intro_HD/Shorts_En_with_audio.mp4",

# For dynamically
"intro": "debate/intro_HD/Shorts_En_with_audio.mp4",
debate/intro_*.mp4




✅ 1. This is FULLY compatible with your current data3d.json
Reuses debate_3d_clips paths
Just extended with intro + ads
✅ 2. Ads are STATIC (global)
assets/static/
✅ 3. Intro is DYNAMIC (per topic)
debate/intro_*.mp4
✅ 4. Optional safe behavior

Your merge engine should:

skip missing p4/p5 automatically
skip ads if file not found
still produce valid output
