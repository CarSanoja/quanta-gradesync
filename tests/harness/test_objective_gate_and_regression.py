import json
from pathlib import Path

import pytest

from autocurricula.agents.calibration_evaluator import LocalGradingEvaluator
from autocurricula.agents.prompts import build_grading_prompt_variant
from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.optimizer_engine import MetaOptimizerEngine
from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant
from autocurricula.core.harness.eval_harness import (
    EvalRunner,
    ObjectiveGate,
    ObjectiveThresholds,
)
from autocurricula.schemas.metrics import CalibrationMetrics

pytestmark = pytest.mark.calibration

BASE = (Path(__file__).parent / "golden_baseline.json").read_text(encoding="utf-8")
BASELINE = json.loads(BASE)

FIXTURES_DIR = Path(__file__).parent.parent / "calibration" / "fixtures"

CEILINGS = {"A": 4.0, "B": 4.0}


def metrics(mae: float, qwk: float, bias: float) -> CalibrationMetrics:
    return CalibrationMetrics(mae=mae, quadratic_weighted_kappa=qwk, bias=bias)


def test_grading_gate_passes_healthy_metrics() -> None:
    gate = ObjectiveGate()
    assert gate.evaluate(metrics(0.3, 0.9, 0.05)).passed is True


def test_grading_gate_fails_each_violation() -> None:
    gate = ObjectiveGate()
    assert gate.evaluate(metrics(0.3, 0.80, 0.05)).passed is False
    assert gate.evaluate(metrics(0.5, 0.9, 0.05)).passed is False
    assert gate.evaluate(metrics(0.3, 0.9, 0.1)).passed is False
    reasons = gate.evaluate(metrics(0.5, 0.8, 0.2)).reasons
    assert len(reasons) == 3


def test_auditor_thresholds_skip_qwk() -> None:
    gate = ObjectiveGate(ObjectiveThresholds.auditor())
    assert gate.evaluate(metrics(0.35, -0.5, 0.25)).passed is True
    assert gate.evaluate(metrics(0.5, 1.0, 0.0)).passed is False


def test_threshold_boundaries_are_inclusive_where_specified() -> None:
    gate = ObjectiveGate()
    assert gate.evaluate(metrics(0.4, 0.85, 0.05)).passed is True
    assert gate.evaluate(metrics(0.4, 0.85, 0.099)).passed is True


class FixedProposer:
    def __init__(self, candidate: PromptVariant) -> None:
        self._candidate = candidate

    async def __call__(self, current, metrics, attempt: int = 0) -> PromptVariant:
        return self._candidate


class ByInstructionEvaluator:
    def __init__(self, results_by_instruction: dict) -> None:
        self._results = results_by_instruction

    async def __call__(self, variant, calibration):
        return self._results[variant.system_instruction]


def _variant(version: int, instruction: str) -> PromptVariant:
    return PromptVariant(
        variant_id="grading_default",
        version=version,
        system_instruction=instruction,
        few_shots=["q1"],
        provenance="seed" if version == 1 else "meta",
    )


@pytest.fixture
def calibration(make_calibration_sample) -> CalibrationSet:
    return CalibrationSet(
        [
            make_calibration_sample("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
            make_calibration_sample("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
        ]
    )


async def test_engine_rejects_winner_failing_objective_gate(
    calibration, make_grading_result
) -> None:
    registry = PromptRegistry()
    registry.register(_variant(1, "base instruction"))
    candidate_instruction = "improves mae but not to production floor"
    evaluator = ByInstructionEvaluator(
        {
            "base instruction": [
                make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
                make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
            ],
            candidate_instruction: [
                make_grading_result("sub_001", {"A": 2.5, "B": 1.5}, CEILINGS),
                make_grading_result("sub_002", {"A": 1.5, "B": 2.5}, CEILINGS),
            ],
        }
    )
    engine = MetaOptimizerEngine(
        FixedProposer(_variant(2, candidate_instruction)),
        AntiGamingValidator(calibration),
        registry,
        evaluator=evaluator,
        calibration=calibration,
        objective_gate=ObjectiveGate(),
    )

    tournament = await engine.run_tournament(1)

    assert tournament.winner is None
    reasons = tournament.candidates[0].rejected_reasons
    assert any(reason.startswith("objective gate: mae") for reason in reasons)
    assert registry.get("grading_default").version == 1


async def test_engine_promotes_when_gate_passes(
    calibration, make_grading_result
) -> None:
    registry = PromptRegistry()
    registry.register(_variant(1, "base instruction"))
    candidate_instruction = "production-grade instruction"
    evaluator = ByInstructionEvaluator(
        {
            "base instruction": [
                make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
                make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
            ],
            candidate_instruction: [
                make_grading_result("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
                make_grading_result("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
            ],
        }
    )
    engine = MetaOptimizerEngine(
        FixedProposer(_variant(2, candidate_instruction)),
        AntiGamingValidator(calibration),
        registry,
        evaluator=evaluator,
        calibration=calibration,
        objective_gate=ObjectiveGate(),
    )

    tournament = await engine.run_tournament(1)

    assert tournament.winner is not None
    assert registry.get("grading_default").system_instruction == candidate_instruction


async def test_golden_regression_gate() -> None:
    calibration = CalibrationSet.from_directory(FIXTURES_DIR)
    runner = EvalRunner(
        calibration, LocalGradingEvaluator()
    )
    summary = await runner.evaluate(build_grading_prompt_variant())

    tolerance = BASELINE["tolerance"]
    assert summary.samples == len(calibration)
    assert summary.metrics.mae <= BASELINE["mae"] + tolerance["mae_increase_max"]
    assert (
        summary.metrics.quadratic_weighted_kappa
        >= BASELINE["quadratic_weighted_kappa"] - tolerance["qwk_drop_max"]
    )
    assert abs(summary.metrics.bias) <= abs(BASELINE["bias"]) + tolerance[
        "bias_abs_growth_max"
    ]
