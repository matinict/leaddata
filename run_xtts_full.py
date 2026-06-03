# uv run python run_xtts_full.py
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
import torchaudio
import torch
import time
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
print("Model loaded.")

gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
    audio_path=["assets/voices/matin3.wav"],
    gpt_cond_len=30,
    max_ref_length=60
)
print("Conditioning latents ready.")

# Split text into short sentences/chunks
chunks = [
    "Thank you, Rasheda. I am excited to be here.",
    "Healing, grounding, and safety are essential for both personal and professional growth.",
    "They go hand in hand, and when we work on these aspects, we see a shift in our overall well-being.",
    "Just thinking about my journey, I remember a time when these concepts were merely theoretical for me.",
]

full_wav = []
t0 = time.time()

for i, chunk in enumerate(chunks):
    print(f"Generating chunk {i+1}/{len(chunks)}: {chunk[:50]}...")
    out = model.inference(
        text=chunk,
        language="en",
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=0.75,
        length_penalty=1.0,
        repetition_penalty=5.0,
        top_k=50,
        top_p=0.85,
        speed=1.0,
        enable_text_splitting=False  # we handle splitting ourselves
    )
    full_wav.append(out["wav"])
    # Add a small pause between chunks (0.3 seconds of silence)
    full_wav.append(np.zeros(int(24000 * 0.3)))

elapsed = time.time() - t0

# Concatenate all chunks
final_wav = np.concatenate(full_wav)

output_path = ".runtime/voice/output_matin1.wav"
torchaudio.save(
    output_path,
    torch.tensor(final_wav).unsqueeze(0),
    24000
)
duration = len(final_wav) / 24000
print(f"\nDone in {elapsed:.1f}s — audio {duration:.1f}s — ratio {elapsed/duration:.1f}x realtime")
print(f"Saved {output_path}")
