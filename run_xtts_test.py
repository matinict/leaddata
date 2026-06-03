from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
import torchaudio, torch, time

config = XttsConfig()
config.load_json("/var/POAi/CrewAiFlow/cf2/models/xtts/config.json")

model = Xtts.init_from_config(config)
model.load_checkpoint(config, checkpoint_dir="/var/POAi/CrewAiFlow/cf2/models/xtts/", eval=True)
model.cpu()
print("Model loaded.")

gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
    audio_path=["assets/voices/matin3.wav"],
    gpt_cond_len=30,
    max_ref_length=60
)
print("Conditioning latents ready.")

# Short test sentence first
t0 = time.time()
out = model.inference(
    text="Thank you, Rasheda. I am excited to be here.",
    language="en",
    gpt_cond_latent=gpt_cond_latent,
    speaker_embedding=speaker_embedding,
    temperature=0.75,
    length_penalty=1.0,
    repetition_penalty=5.0,
    top_k=50,
    top_p=0.85,
    speed=1.0,
    enable_text_splitting=True
)
elapsed = time.time() - t0
wav = out["wav"]
torchaudio.save("output_test.wav", torch.tensor(wav).unsqueeze(0), 24000)
duration = len(wav) / 24000
print(f"Done in {elapsed:.1f}s — audio {duration:.1f}s — ratio {elapsed/duration:.1f}x realtime")
print("Saved output_test.wav")
