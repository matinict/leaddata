



English :
========================================================



COQUI_HOME=/var/POAi/CrewAiFlow/cf2/models/xtts \
uv run --no-sync python - <<'EOF'
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
import torchaudio
import torch
import numpy as np

config = XttsConfig()
config.load_json("/var/POAi/CrewAiFlow/cf2/models/xtts/config.json")

model = Xtts.init_from_config(config)
model.load_checkpoint(
   config,
   checkpoint_dir="/var/POAi/CrewAiFlow/cf2/models/xtts/",
   eval=True
)
model.cpu()
gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
    audio_path=["assets/voices/matin3.wav"],
    gpt_cond_len=30,        # use up to 30 sec of reference (default=6)
    max_ref_length=60       # allow longer reference
)
out = model.inference(
    text=" Thank you, Rasheda!... I'm excited to be here. Healing, grounding, and safety are essential for both personal and professional growth. They go hand in hand... and when we work on these aspects, we see a shift in our overall well-being. Just thinking about my journey... I remember a time when these concepts were merely theoretical for me.",
    language="en",
    gpt_cond_latent=gpt_cond_latent,
    speaker_embedding=speaker_embedding,
    temperature=0.65,       # lower = more stable/similar (default 0.85)
    repetition_penalty=2.0,
    top_k=50,
    top_p=0.85,
)

wav = torch.tensor(out["wav"]).unsqueeze(0)
torchaudio.save(".runtime/output/matin31.wav", wav, 24000)
print("Done — .runtime/output/matin31.wav")
EOF





Bangla :
========================================================
uv run --no-sync python - <<'EOF'
import asyncio
import edge_tts

async def main():
    tts = edge_tts.Communicate(
        text="স্বাগতম প্লেওনএআই চ্যানেলে। আজকে আমরা কৃত্রিম বুদ্ধিমত্তার বড় প্রবণতা নিয়ে আলোচনা করব।",
        voice="bn-BD-PradeepNeural"   # male BD Bengali
        # voice="bn-BD-NabanitaNeural" # female BD Bengali
        # voice="bn-IN-BashkarNeural"  # male IN Bengali
        # voice="bn-IN-TanishaaNeural" # female IN Bengali
    )
    await tts.save(".runtime/output/raad_bn_test.mp3")
    print("Done — .runtime/output/raad_bn_test.mp3")

asyncio.run(main())
EOF










 ==============
