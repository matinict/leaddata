Based on your actual project setup:

---

### ⚡ Makefile shortcuts

```bash
make profiles                   # list profiles
make 3d                         # Unit-Debate, 3d profile
make 3d-force                   # force re-run Unit-Debate
make 3d-data                    # Unit-Data, 3d profile
make 3d-topic t="AI vs Humans"  # custom topic
make bn                         # Unit-Debate, Bn profile
make bn-data                    # Unit-Data, Bn profile
make data    p=3d               # Unit-Data, any profile
make debate  p=3d               # Unit-Debate, any profile
make force-debate p=3d          # force Unit-Debate
make status  p=3d               # pipeline status
make dry u=Unit-Debate p=3d     # dry run
make help                       # show all targets
```

---

### 🔧 Base command
```bash
uv run python -m cf2.main [flags]
```

---

### 📋 All flags

```bash
--unit          Unit to run (see list below)
--topic         Override topic string
--profile       Profile: short name OR full path
--force         Re-run even if already done
--dry-run       Show what would run — no execution
--list-profiles List available profiles and exit
--status        Show pipeline status for topic
--yt-upload     Enable YouTube upload
--fb-upload     Enable Facebook upload
```

---

### 🧱 Valid `--unit` values

```bash
Unit-Scout
Unit-Data
Unit-Debate
Unit-Definition
Unit-Animation
Unit-Comparison
Unit-Publisher
Unit-Advertise
```

---

### 💡 All commands

```bash
# ── Profiles ────────────────────────────────────────────────
uv run python -m cf2.main --list-profiles

# ── Run with short profile name ──────────────────────────────
uv run python -m cf2.main --unit Unit-Data     --profile 3d
uv run python -m cf2.main --unit Unit-Debate   --profile 3d
uv run python -m cf2.main --unit Unit-Debate   --profile Bn
uv run python -m cf2.main --unit Unit-Publisher --profile 3d

# ── Run with full path (old way — still works) ───────────────
uv run python -m cf2.main --unit Unit-Debate \
  --profile /var/POAi/CrewAiFlow/cf2/input/data3d.json

# ── Force re-run ─────────────────────────────────────────────
uv run python -m cf2.main --unit Unit-Debate --profile 3d --force

# ── Custom topic ─────────────────────────────────────────────
uv run python -m cf2.main --unit Unit-Data \
  --profile 3d --topic "AI vs Humans"

# ── Dry run ──────────────────────────────────────────────────
uv run python -m cf2.main --unit Unit-Debate --profile 3d --dry-run

# ── Status ───────────────────────────────────────────────────
uv run python -m cf2.main --status --profile 3d

# ── Publish ──────────────────────────────────────────────────
uv run python -m cf2.main --unit Unit-Publisher --profile 3d --yt-upload
uv run python -m cf2.main --unit Unit-Publisher --profile 3d --fb-upload
uv run python -m cf2.main --unit Unit-Publisher --profile 3d \
  --yt-upload --fb-upload
```



## list profiles

make profiles
uv run python -m cf2.main --list-profiles

📂  Profiles & usage:

  default
    uv run python -m cf2.main --unit Unit-Debate
    make debate

  default (data.json)
    uv run python -m cf2.main --unit Unit-Debate --profile default (data.json)
    make debate p=default (data.json)

  3d
    uv run python -m cf2.main --unit Unit-Debate --profile 3d
    make 3d

  Bn
    uv run python -m cf2.main --unit Unit-Debate --profile Bn
    make debate p=Bn
