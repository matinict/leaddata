Based on your `pcf.json`, just replace `prodcast_voice_guest` with a special xtts clone marker and handle it in the TTS routing layer.


cd /var/POAi/CrewAiFlow/cf2
export OMP_NUM_THREADS=5
export MKL_NUM_THREADS=5
make pcf









**Step 1 — Update `pcf.json`:**
```json
{
  "tts_engine": "edge-tts",
  "prodcast_voice_host": "en-US-JennyNeural",
  "prodcast_voice_guest": "xtts:assets/voices/RaadEn_clean.wav"
}
```

The `xtts:` prefix is the signal — host stays edge-tts, guest uses XTTS clone.

---

**Step 2 — In your TTS service, resolve by prefix:**
```python
# src/cf2/core/services/tts_service.py

def synthesize_for_role(text: str, output_path: str, voice: str, inputs: dict) -> str:
    """
    voice examples:
      "en-US-JennyNeural"          → edge-tts
      "xtts:assets/voices/Raad.wav" → XTTS clone
    """
    if voice.startswith("xtts:"):
        speaker_wav = voice.split("xtts:", 1)[1]
        return _synthesize_xtts(text, output_path, speaker_wav, inputs)
    else:
        return _synthesize_edge_tts(text, output_path, voice)


def _synthesize_xtts(text: str, output_path: str, speaker_wav: str, inputs: dict) -> str:
    import torch, torchaudio
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    if os.path.exists(output_path):
        return f"⏭️ Skipped: {output_path}"

    model_dir = "/var/POAi/CrewAiFlow/cf2/models/xtts"
    config = XttsConfig()
    config.load_json(f"{model_dir}/config.json")

    model = Xtts.init_from_config(config)
    model.load_checkpoint(config, checkpoint_dir=model_dir, eval=True)
    model.cpu()

    gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
        audio_path=[speaker_wav],
        gpt_cond_len=30,
        max_ref_length=60
    )
    out = model.inference(
        text=text,
        language="en",
        gpt_cond_latent=gpt_cond_latent,
        speaker_embedding=speaker_embedding,
        temperature=0.65,
        repetition_penalty=2.0,
        top_k=50,
        top_p=0.85,
    )
    wav = torch.tensor(out["wav"]).unsqueeze(0)
    torchaudio.save(output_path, wav, 24000)
    return f"✅ XTTS: {output_path}"
```

---

**Step 3 — In your podcast unit, resolve guest voice:**
```python
# wherever podcast audio is generated per role

host_voice  = inputs.get("prodcast_voice_host")   # "en-US-JennyNeural"
guest_voice = inputs.get("prodcast_voice_guest")  # "xtts:assets/voices/RaadEn_clean.wav"

synthesize_for_role(host_line,  host_output_path,  host_voice,  inputs)
synthesize_for_role(guest_line, guest_output_path, guest_voice, inputs)
```

---

This way:
- `pcf.json` is the only file you change per project
- Host always uses edge-tts
- Guest uses XTTS clone from whatever WAV you point to
- Swap guest voice by changing one line in `pcf.json`
