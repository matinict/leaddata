"""
Smoke test for score_extractor — heuristic path only.
Validates ScoreData shape from a synthetic propose/oppose/decide set.
"""
import json
import sys
import tempfile
from pathlib import Path

# Stub the PROJECT_ROOT dependency by not importing anything that needs it
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import the extractor module directly (no external deps)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "score_extractor",
    Path(__file__).parent
    / "src/cf2/core/render/scoreboard/score_extractor.py",
)
score_extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score_extractor)


PROPOSE = """PROPOSITION: China's Belt and Road trap

OPENING STATEMENT

China's BRI leaves poor countries saddled with debt they cannot repay,
forcing concessions on ports, minerals, and strategic assets.

Argument 1: AI Chip Sovereignty
Beijing's aggressive funding of domestic chip fabs has locked developing
nations into Chinese tech stacks. Research from 2024 shows 62 percent of
new data centers in sub-Saharan Africa run on Chinese silicon.

Argument 2: Alliance Expansion
Through port concessions and rail corridors, China has built a physical
alliance spanning four continents. Reports cite 147 BRI agreements now
include military access clauses.

Argument 3: Dollar Dominance
The yuan-settlement push is quietly eroding dollar clearing in commodity
trade, according to IMF data covering 2022 to 2026.
"""

OPPOSE = """OPPOSITION: China's Belt and Road trap — Disagree

OPENING STATEMENT

The "debt trap" narrative is a Western talking point unsupported by
credible evidence. Most BRI restructurings were initiated by the
borrowers themselves.

Counter-Argument 1: Strategic Overreach
China's chip push has stumbled — US export controls cut SMIC yields by
40 percent. The sovereignty claim ignores real manufacturing setbacks.

Counter-Argument 2: Debt-Fueled Fragility
BRI itself is fragile. Evergrande's collapse exposed 2 trillion in hidden
liabilities. Expansion is outpacing Beijing's ability to fund it.

Counter-Argument 3: Rule-Making Is Moving On
Standards bodies — ISO, ITU, IEEE — increasingly sideline Chinese
proposals. The rule-making center of gravity is shifting to Europe.
"""

DECIDE = """VERDICT: China's Belt and Road trap

SUMMARY

PROPOSITION: BRI creates structural dependence through chips, ports, and
currency channels.
OPPOSITION: The dependence thesis is weak; China faces more fragility
than it projects.

ANALYSIS

The proposition supplied concrete numbers on chip penetration and port
access. The opposition pushed back effectively on yields but left the
currency argument largely unchallenged.

DECISION

PROPOSITION WINS.
The evidence on BRI's physical and monetary reach was better sourced
than the opposition's counter-claims.
"""


def main():
    tmp = Path(tempfile.mkdtemp(prefix="scoreboard_test_"))
    (tmp / "propose.md").write_text(PROPOSE, encoding="utf-8")
    (tmp / "oppose.md").write_text(OPPOSE, encoding="utf-8")
    (tmp / "decide.md").write_text(DECIDE, encoding="utf-8")

    cfg = {"debate_scoreboard_max_args": 3}
    data = score_extractor.resolve(tmp, md_suffix="", cfg=cfg)

    assert data is not None, "resolver returned None"
    assert data["source"] == "heuristic"
    assert data["winner"] == "propose"
    assert data["totals"]["pro"] > data["totals"]["con"], \
        f"Winner total not higher: {data['totals']}"
    assert len(data["args"]) == 3
    for arg in data["args"]:
        assert 8 <= arg["pro"] <= 20
        assert 8 <= arg["con"] <= 20
        assert len(arg["pro_title"]) <= 43
        assert len(arg["con_title"]) <= 43

    print("✅ Heuristic scoring OK")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
