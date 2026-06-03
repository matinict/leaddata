from __future__ import annotations
"""
unit_data.py — Content Generation Engine

Architectural Rules
───────────────────
D-1 Provider only. Reads nothing from workspace inputs (only checks
     output existence for the cache guard).
D-5 Unit-Data is the SOLE producer of foundational, *shared* data
     artifacts — i.e. artifacts that multiple consumer units may
     read. Consumer-specific artifacts belong in their own units.
D-6 Consumer units (Unit-Debate, Unit-Definition, Unit-Comparison,
     Unit-Animation, Unit-LeadData, Unit-Classroom) are gated by their
     own Unit-* switches in their own modules.

Ownership Map
─────────────
    Unit-Data owns:
        - data.csv (shared by Animation + LeadData)
        - debate/decide.md (consumed by Unit-Debate renderer)
        - definition/def_En.txt
        - comparison/comparison.md
        - classroom/script.md (consumed by Unit-Classroom renderer)
        - classroom/script-m.md
        - classroom/roles.json
        - classroom/quiz.json

    Unit-Prodcast owns:
        - podcast/script.md (Prodcast-specific; uses Prodcast config)
        - podcast/audio.mp3
        - podcast/video.mp4

Smart Production
────────────────
Unit-Data inspects which downstream consumers are enabled and runs
only the LLM tasks required to satisfy their declared dependencies
(CONSUMER_REQUIREMENTS). Unit-Prodcast is NOT in this map — it
manages its own pipeline.

Cache Guard
───────────
If all artifacts required by the currently-enabled consumers already
exist on disk and are non-empty, Unit-Data short-circuits with
RunStatus.DONE and burns zero tokens. Pass `force=True` to bypass.

Public API
──────────
    run(topic, workspace, inputs, force=False) -> str
"""
import logging

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from crewai import Crew, Process

from cf2.meta import acquire_lock, release_lock
from cf2.crews.crew import CF2Crew
from cf2.core.compress import decide_compressor
from cf2.tools.classroom_script_generator import _compress, _extract_quiz

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════════════════
# Constants
# ════════════════════════════════════════════

class RunStatus(str, Enum):
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"
    LOCKED = "locked"

class Block(str, Enum):
    """Coherent producer bundles. Each block produces one+ artifacts."""
    RESEARCH = "research"
    DEBATE = "debate"
    DEFINITION = "definition"
    COMPARISON = "comparison"
    CLASSROOM = "classroom"

# Map: consumer Unit-* switch → set of producer blocks it depends on.
CONSUMER_REQUIREMENTS: dict[str, set[Block]] = {
    "Unit-Debate": {Block.DEBATE},
    "Unit-Definition": {Block.DEFINITION},
    "Unit-Comparison": {Block.COMPARISON},
    "Unit-Animation": {Block.RESEARCH},
    "Unit-LeadData": {Block.RESEARCH},
    "Unit-Classroom": {Block.CLASSROOM},
}

# Map: block → relative artifact paths it produces
BLOCK_ARTIFACTS: dict[Block, tuple[str,...]] = {
    Block.RESEARCH: ("data.csv",),
    Block.DEBATE: ("debate/decide.md",),
    Block.DEFINITION: ("definition/def_En.txt",),
    Block.COMPARISON: ("comparison/comparison.md",),
    Block.CLASSROOM: (
        "classroom/script.md",
        "classroom/roles.json",
        "classroom/quiz.json",
    ),
}

COMPRESSION_TIERS: tuple[tuple[int, float],...] = (
    (6000, 0.35),
    (3000, 0.42),
    (0, 0.50),
)
COMPRESS_FLOOR = 320
COMPRESS_CEILING = 750
COMPRESS_MIN_CHARS = 260

# ════════════════════════════════════════════════════════════════════════════
# Bundle
# ════════════════════════════════════════════

@dataclass
class CrewBundle:
    agents: list[Any] = field(default_factory=list)
    tasks: list[Any] = field(default_factory=list)
    blocks_included: set[Block] = field(default_factory=set)

    def add(self, block: Block, agents: list[Any], tasks: list[Any]) -> None:
        self.agents.extend(agents)
        self.tasks.extend(tasks)
        self.blocks_included.add(block)

    def is_empty(self) -> bool:
        return not self.tasks

# ════════════════════════════════════════════
# Public Entry Point
# ════════════════════════════════════════════

def run(
    topic: str,
    workspace: Path,
    inputs: dict[str, Any],
    force: bool = False,
) -> str:
    if not topic:
        logger.error("Unit-Data: empty topic")
        return RunStatus.FAILED

    required_blocks = _resolve_required_blocks(inputs)

    if not required_blocks:
        logger.info("Unit-Data: no enabled consumers require shared data — skipping")
        return RunStatus.SKIPPED

    logger.info(
        "Unit-Data: required blocks: %s",
        ", ".join(sorted(b.value for b in required_blocks)),
    )

    # ── 1. CACHE FIRST (always, regardless of flags) ─────────────────────
    if not force:
        missing = _missing_artifacts(workspace, required_blocks)
        if not missing:
            logger.info("Unit-Data: ✅ CACHE HIT — all artifacts exist, skipping")
            return RunStatus.DONE
        logger.info(
            "Unit-Data: cache miss — %d artifact(s) missing: %s",
            len(missing), ", ".join(_relpath(p, workspace) for p in missing),
        )
    else:
        logger.info("Unit-Data: force=True — bypassing cache")

    # ── 2. LLM GATE ─────────────────────────────────────────────────────
    llm_enabled = inputs.get("data_llm_enabled", False)
    if not llm_enabled:
        logger.warning(
            "Unit-Data: LLM DISABLED by default. "
            "Set 'data_llm_enabled': true in request to enable generation."
        )
        return RunStatus.SKIPPED

    # ── 3. Force lowest-cost config ─────────────────────────────────────
    unit_data_flag = inputs.get("Unit-Data", True)

    cheap_config = {
        "default": "ollama/deepseek-r1:1.5b",
        "tiers": {
            "research": {
                "models": [
                    "ollama/deepseek-r1:1.5b",
                    "ollama/llama3.1:8b",
                    "deepseek/deepseek-chat",
                ],
                "temperature": 0.3,
                "max_tokens": 2048
            },
            "scoring": {
                "models": ["ollama/deepseek-r1:1.5b"],
                "temperature": 0.2,
                "max_tokens": 1024
            },
            "local_tiny": {
                "models": ["ollama/deepseek-r1:1.5b"],
                "temperature": 0.5,
                "max_tokens": 1024
            },
            "local_fast": {
                "models": ["ollama/llama3.1:8b"],
                "temperature": 0.5,
                "max_tokens": 2048
            }
        },
        "agents": {
            "data_researcher": {"tier": "research"},
            "csv_generator": {"tier": "local_tiny"},
            "definition_specialist": {"tier": "local_tiny"},
            "scout": {"tier": "local_fast"},
            "score_analyst": {"tier": "scoring"},
            "debater": {"tier": "local_fast"},
            "judge": {"tier": "local_fast"},
        },
        "circuit_breaker": {"failure_threshold": 3, "cooldown_seconds": 300}
    }

    # Block cloud models when Unit-Data is false
    if not unit_data_flag:
        for tier in cheap_config["tiers"].values():
            tier["models"] = [m for m in tier["models"] if m.startswith("ollama/")]
        logger.info("🔒 Unit-Data=false — cloud LLMs blocked, Ollama only")

    inputs = {**inputs, "llm_config": cheap_config}
    logger.info("Unit-Data: LLM enabled with lowest-cost models")

    # ── 4. Execute ──────────────────────────────────────────────────────
    lock = acquire_lock(workspace, "Unit-Data")
    if not lock:
        logger.warning("Unit-Data: could not acquire lock for %s", workspace)
        return RunStatus.LOCKED

    try:
        bundle = _assemble_bundle(required_blocks, inputs)
        if bundle.is_empty():
            logger.error("Unit-Data: empty bundle for blocks=%s", required_blocks)
            return RunStatus.FAILED

        logger.info(
            "Unit-Data: running %d agent(s), %d task(s), blocks=%s, topic='%s'",
            len(bundle.agents), len(bundle.tasks),
            sorted(b.value for b in bundle.blocks_included), topic,
        )

        result = _execute_crew(bundle, topic, workspace, inputs)
        if not result:
            logger.error("Unit-Data: crew returned empty result")
            return RunStatus.FAILED

        if Block.DEBATE in bundle.blocks_included:
            _compress_mobile_verdict(workspace / "debate")

        if Block.CLASSROOM in bundle.blocks_included:
            _post_process_classroom(workspace, inputs)

        still_missing = _missing_artifacts(workspace, required_blocks)
        if still_missing:
            logger.error(
                "Unit-Data: run completed but artifacts missing: %s",
                ", ".join(_relpath(p, workspace) for p in still_missing),
            )
            return RunStatus.FAILED

        logger.info("Unit-Data: complete")
        return RunStatus.DONE

    except Exception as exc:
        logger.exception("Unit-Data: unhandled exception — %s", exc)
        return RunStatus.FAILED
    finally:
        release_lock(lock)

# ── Rest of file unchanged ───────────────────────────────────────────────

def _resolve_required_blocks(inputs: dict[str, Any]) -> set[Block]:
    required: set[Block] = set()
    for unit, blocks in CONSUMER_REQUIREMENTS.items():
        if inputs.get(unit, False):
            required.update(blocks)
            logger.debug("Unit-Data: %s enabled → needs %s", unit, blocks)
    return required

def _missing_artifacts(workspace: Path, blocks: set[Block]) -> list[Path]:
    missing: list[Path] = []
    for block in blocks:
        for rel in BLOCK_ARTIFACTS.get(block, ()):
            path = workspace / rel
            if not path.exists() or path.stat().st_size == 0:
                missing.append(path)
    return missing

def _relpath(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)

def _assemble_bundle(required_blocks: set[Block], inputs: dict[str, Any]) -> CrewBundle:
    factory = CF2Crew(inputs=inputs)
    bundle = CrewBundle()

    if Block.RESEARCH in required_blocks:
        bundle.add(
            Block.RESEARCH,
            agents=[factory.data_researcher(), factory.data_csv_generator()],
            tasks=[factory.data_research(), factory.data_generate_csv()],
        )

    if Block.DEBATE in required_blocks:
        bundle.add(
            Block.DEBATE,
            agents=[factory.debate_debater(), factory.debate_judge()],
            tasks=[
                factory.debate_propose(),
                factory.debate_oppose(),
                factory.debate_decide(),
            ],
        )
        _maybe_add_debate_subfeatures(factory, bundle, inputs)

    if Block.DEFINITION in required_blocks:
        bundle.add(
            Block.DEFINITION,
            agents=[factory.data_definition_specialist()],
            tasks=[factory.data_define_topic()],
        )

    if Block.COMPARISON in required_blocks:
        _add_optional_block(
            factory, bundle, Block.COMPARISON,
            agent_attr="data_comparison_specialist",
            task_attr="data_compare_topic",
        )

    if Block.CLASSROOM in required_blocks:
        _add_optional_block(
            factory, bundle, Block.CLASSROOM,
            agent_attr="classroom_script_writer",
            task_attr="create_classroom_script",
        )

    return bundle

def _add_optional_block(factory: CF2Crew, bundle: CrewBundle, block: Block, agent_attr: str, task_attr: str) -> None:
    agent_fn: Callable | None = getattr(factory, agent_attr, None)
    task_fn: Callable | None = getattr(factory, task_attr, None)
    if callable(agent_fn) and callable(task_fn):
        bundle.add(block, agents=[agent_fn()], tasks=[task_fn()])
    else:
        logger.warning(
            "Unit-Data: %s not wired in CF2Crew (need %s + %s).",
            block.value, agent_attr, task_attr,
        )

def _maybe_add_debate_subfeatures(factory: CF2Crew, bundle: CrewBundle, inputs: dict[str, Any]) -> None:
    bundle.agents.append(factory.debate_debater_m())
    bundle.tasks.extend([factory.debate_propose_m(), factory.debate_oppose_m()])
    score_cfg = inputs.get("debate_config", {}).get("debate_3d_score", {})
    if score_cfg.get("enabled") and score_cfg.get("llm_enabled"):
        bundle.agents.append(factory.debate_score_analyst())
        bundle.tasks.append(factory.debate_generate_scores())

def _execute_crew(bundle: CrewBundle, topic: str, workspace: Path, inputs: dict[str, Any]) -> Any:
    crew = Crew(
        agents=bundle.agents,
        tasks=bundle.tasks,
        process=Process.sequential,
        verbose=inputs.get("verbose", False),
    )
    return crew.kickoff(inputs=_build_kickoff_inputs(topic, workspace, inputs))

def _build_kickoff_inputs(topic: str, workspace: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    ws = str(workspace)
    # Start with ALL inputs from config (includes focus, prodcast_enabled, etc.)
    base = dict(inputs)
    # Override core paths
    base.update({
        "topic": topic,
        "output_dir": ws,
        "workspace": ws,
        "data_dir": ws,
        "debate_dir": str(workspace / "debate"),
        "definition_dir": str(workspace / "definition"),
        "comparison_dir": str(workspace / "comparison"),
        "podcast_dir": str(workspace / "podcast"),
        "classroom_dir": str(workspace / "classroom"),
    })

    # Drop None values (so {focus} becomes "" not "None")
    return {k: ("" if v is None else v) for k, v in base.items()}

def _compress_mobile_verdict(debate_dir: Path) -> None:
    hd_path = debate_dir / "decide.md"
    mobile_path = debate_dir / "decide-m.md"
    if not hd_path.exists():
        return
    try:
        hd_text = hd_path.read_text(encoding="utf-8")
        if not hd_text.strip():
            return
        max_chars = _compute_compression_budget(len(hd_text))
        decide_compressor.compress(hd_path, mobile_path, max_chars=max_chars)
        logger.info("Compress: %s → %s", hd_path.name, mobile_path.name)
    except Exception as exc:
        logger.warning("Compress failed — %s", exc)

def _compute_compression_budget(hd_len: int) -> int:
    ratio = next(r for threshold, r in COMPRESSION_TIERS if hd_len > threshold)
    target = int(hd_len * ratio)
    clamped = max(COMPRESS_FLOOR, min(target, COMPRESS_CEILING))
    return max(COMPRESS_MIN_CHARS, clamped)

def _post_process_classroom(workspace: Path, inputs: dict[str, Any]) -> None:
    classroom_dir = workspace / "classroom"
    classroom_dir.mkdir(parents=True, exist_ok=True)
    script_path = classroom_dir / "script.md"
    if not script_path.exists() or script_path.stat().st_size == 0:
        return
    mini_path = classroom_dir / "script-m.md"
    if not mini_path.exists():
        try:
            raw = script_path.read_text("utf-8")
            mini = _compress(raw)
            mini_path.write_text(mini, encoding="utf-8")
        except Exception:
            pass
    quiz_path = classroom_dir / "quiz.json"
    if not quiz_path.exists():
        try:
            import json
            raw = script_path.read_text("utf-8")
            quiz = _extract_quiz(raw)
            quiz_path.write_text(json.dumps(quiz, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
    roles_path = classroom_dir / "roles.json"
    if not roles_path.exists():
        try:
            from cf2.tools.classroom_roles_generator import run as write_roles
            write_roles(str(workspace), inputs.get("classroom_config", {}))
        except Exception:
            pass
