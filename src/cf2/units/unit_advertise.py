"""
Unit-Advertise — dynamic task assignment
subUnitShorts | subUnitSocial | subUnitTvc
Guards: shorts_enabled | social_enabled | tvc_enabled
"""
from cf2.meta import get_topic_dir, _make_slug
from crewai import Crew, Process

def run(topic: str, inputs: dict):
    topic_dir = get_topic_dir(topic)
    inputs["output_dir"]  = str(topic_dir)
    inputs["filename"]    = _make_slug(topic)
    inputs["topic_slug"]  = _make_slug(topic)

    for sub in ["advertise/shorts", "advertise/social", "advertise/tvc"]:
        (topic_dir / sub).mkdir(parents=True, exist_ok=True)

    ran = []

    # subUnitShorts — cut from main video via SmartVideoTool
    if inputs.get("shorts_enabled"):
        print("✂️  subUnitShorts: cutting shorts from main video...")
        # TODO: wire SmartVideoTool
        ran.append("subUnitShorts")

    # subUnitSocial — captions + short clips
    if inputs.get("social_enabled"):
        print("📱  subUnitSocial: generating social clips + captions...")
        # TODO: wire SocialShareTool
        ran.append("subUnitSocial")

    # subUnitTvc — cinematic ad
    if inputs.get("tvc_enabled"):
        print("🎬  subUnitTvc: generating TVC ad...")
        # TODO: wire SmartVideoTool + AudioGenerationTool
        ran.append("subUnitTvc")

    if not ran:
        print("⚠️  Unit-Advertise: no subunits enabled — check inputs flags")
        print("   Set shorts_enabled | social_enabled | tvc_enabled in data.json")
        return

    print(f"✅ Unit-Advertise done: {', '.join(ran)}")
