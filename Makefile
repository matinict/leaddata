# ══════════════════════════════════════════════════════════════════════════════
# CF2 — CrewAI Flow Factory Makefile
# Usage: make <target> [p=profile] [t=topic] [u=unit]
# Run `make` alone to launch interactive numbered menu.
# ══════════════════════════════════════════════════════════════════════════════

.DEFAULT_GOAL := launch

RUN = uv run python -m cf2.main
p ?= 3d

# ── Interactive Launcher ──────────────────────────────────────────────────────
launch:
	@uv run python -m cf2.cli.launcher

.PHONY: launch

# ══════════════════════════════════════════════════════════════════════════════
# PROFILES & STATUS
# ══════════════════════════════════════════════════════════════════════════════

profiles:
	$(RUN) --list-profiles

status:
	$(RUN) --status --profile $(p)

# ══════════════════════════════════════════════════════════════════════════════
# SINGLE UNITS
# ══════════════════════════════════════════════════════════════════════════════

scout:
	$(RUN) --unit Unit-Scout --profile $(p)

data:
	$(RUN) --unit Unit-Data --profile $(p)

debate:
	$(RUN) --unit Unit-Debate --profile $(p)

definition:
	$(RUN) --unit Unit-Definition --profile $(p)

animation:
	$(RUN) --unit Unit-Animation --profile $(p)

comparison:
	$(RUN) --unit Unit-Comparison --profile $(p)

pack:
	$(RUN) --unit Unit-Packaging --profile $(p)

publish:
	$(RUN) --unit Unit-Publisher --profile $(p)

advertise:
	$(RUN) --unit Unit-Advertise --profile $(p)

# ══════════════════════════════════════════════════════════════════════════════
# LEAD GENERATION PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

leads:
	$(RUN) --profile leads

leads-force:
	$(RUN) --profile leads --force

# ══════════════════════════════════════════════════════════════════════════════
# LEAD INTENT — Review-based Intent Mining
# ══════════════════════════════════════════════

leadint:
	$(RUN) --profile leadint

leadint-force:
	$(RUN) --profile leadint --force

leadint-unit:
	$(RUN) --unit Unit-LeadData --profile leadint

leadint-unit-force:
	$(RUN) --unit Unit-LeadData --profile leadint --force

# ══════════════════════════════════════════════════════════════════════════════
# FULL PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

run-full:
	$(RUN) --profile $(p)

# ══════════════════════════════════════════════════════════════════════════════
# FORCE RE-RUNS
# ══════════════════════════════════════════════════════════════════════════════

force-scout:
	$(RUN) --unit Unit-Scout --profile $(p) --force

force-data:
	$(RUN) --unit Unit-Data --profile $(p) --force

force-debate:
	$(RUN) --unit Unit-Debate --profile $(p) --force

force-pack:
	$(RUN) --unit Unit-Packaging --profile $(p) --force

force-publish:
	$(RUN) --unit Unit-Publisher --profile $(p) --force

force-advertise:
	$(RUN) --unit Unit-Advertise --profile $(p) --force

# ══════════════════════════════════════════════════════════════════════════════
# 3D PIPELINE
# ══════════════════════════════════════════════

3d:
	$(RUN) --profile 3d

3d-force:
	$(RUN) --profile 3d --force

3d-data:
	$(RUN) --unit Unit-Data --profile 3d

3d-pack:
	$(RUN) --unit Unit-Packaging --profile 3d

3d-scout:
	$(RUN) --unit Unit-Scout --profile 3d

3d-topic:
	$(RUN) --unit Unit-Debate --profile 3d --topic "$(t)"

# ══════════════════════════════════════════════
# BENGALI
# ══════════════════════════════════════════════

bn:
	$(RUN) --unit Unit-Debate --profile Bn

bn-data:
	$(RUN) --unit Unit-Data --profile Bn

bn-pack:
	$(RUN) --unit Unit-Packaging --profile Bn

# ══════════════════════════════════════════════
# PODCAST
# ══════════════════════════════════════════════════════════════════════════════

pcm:
	$(RUN) --profile pcm

pcf:
	$(RUN) --profile pcf

pcm-force:
	$(RUN) --profile pcm --force

pcf-force:
	$(RUN) --profile pcf --force

pcm-topic:
	$(RUN) --unit Unit-Prodcast --profile pcm --topic "$(t)"

pcf-topic:
	$(RUN) --unit Unit-Prodcast --profile pcf --topic "$(t)"

# ══════════════════════════════════════════════
# CLASSROOM
# ══════════════════════════════════════════════════════════════════════════════

croom:
	$(RUN) --profile croom

croom-force:
	$(RUN) --profile croom --force

croom-unit:
	$(RUN) --unit Unit-Classroom --profile croom

croom-topic:
	$(RUN) --unit Unit-Classroom --profile croom --topic "$(t)"

# ══════════════════════════════════════════════
# CTUTOR
# ══════════════════════════════════════════════

ctutor:
	$(RUN) --profile ctutor

ctutor-force:
	$(RUN) --profile ctutor --force

ctutor-unit:
	$(RUN) --unit Unit-Classroom --profile ctutor

ctutor-topic:
	$(RUN) --unit Unit-Classroom --profile ctutor --topic "$(t)"

# ══════════════════════════════════════════════════════════════════════════════
# DUBBING PIPELINE
# ══════════════════════════════════════════════

dub:
	$(RUN) --unit Unit-Dubbing --profile dub

dub-force:
	$(RUN) --unit Unit-Dubbing --profile dub --force

dub-ed:
	TTS=edge $(MAKE) dub

dub-ed-force:
	TTS=edge $(MAKE) dub-force

dub-xt:
	TTS=xtts $(MAKE) dub

dub-xt-force:
	TTS=xtts $(MAKE) dub-force

dub-pi:
	TTS=piper $(MAKE) dub

dub-pi-force:
	TTS=piper $(MAKE) dub-force

dub-gt:
	TTS=gtts $(MAKE) dub

dub-gt-force:
	TTS=gtts $(MAKE) dub-force

# ── Dubbing Subtasks ──────────────────────────────────────────────────────────

dub-transcribe:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask transcribe

dub-ocr:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask screen_ocr

dub-merge:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask merge_context

dub-synth:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask synthesize

dub-synth-ed:
	TTS=edge $(MAKE) dub-synth

dub-synth-xt:
	TTS=xtts $(MAKE) dub-synth

dub-sync:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask sync

dub-av:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask merge

dub-holo:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask hologram

dub-crop:
	$(RUN) --unit Unit-Dubbing --profile dub --subtask crop

# ══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ══════════════════════════════════════════════

dry:
	$(RUN) --unit $(u) --profile $(p) --dry-run

llm:
	@uv run python -c "import json, pathlib; f=pathlib.Path('.runtime/cache/llm_status.json'); d=json.loads(f.read_text()) if f.exists() else {}; print('LLM STATUS -', len(d), 'models'); [print(k, v.get('status','?'), v.get('last_call','')[:19]) for k,v in sorted(d.items())] if d else print('No LLM calls yet')"

lls:
	@watch -n 3 "make llm"

llm-json:
	@cat .runtime/cache/llm_status.json 2>/dev/null | python -m json.tool || echo "No status file yet"

# Rule 25 — Lock maintenance
clean-locks:
	@find .runtime/output -name ".lock" -type f -delete -print

clean-output:
	@rm -rf .runtime/output/*

clean-cache:
	@rm -rf src/cf2/__pycache__ src/cf2/core/__pycache__
