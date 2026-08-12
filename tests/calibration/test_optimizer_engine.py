import pytest

from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.optimizer_engine import MetaOptimizerEngine
from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.metrics import CalibrationMetrics

pytestmark = pytest.mark.calibration

BASE_INSTRUCTION = "Assess each submission against the rubric and cite page evidence."
CANDIDATE_INSTRUCTION = (
    "Assess each submission against the rubric, cite page evidence, and use mastery language."
)
CEILINGS = {"A": 4.0, "B": 4.0}


class ScriptedProposer:
    def __init__(self, candidate: PromptVariant) -> None:
        self.candidate = candidate
        self.calls: list[tuple[PromptVariant, CalibrationMetrics]] = []

    async def __call__(
        self, current: PromptVariant, metrics: CalibrationMetrics
    ) -> PromptVariant:
        self.calls.append((current, metrics))
        return self.candidate


class ScriptedEvaluator:
    def __init__(self, results_by_version: dict[int, list[GradingResult]]) -> None:
        self._results_by_version = results_by_version
        self.calls: list[int] = []

    async def __call__(
        self, variant: PromptVariant, calibration: CalibrationSet
    ) -> list[GradingResult]:
        self.calls.append(variant.version)
        return self._results_by_version[variant.version]


def _variant(version: int, instruction: str) -> PromptVariant:
    return PromptVariant(
        variant_id="grading_default",
        version=version,
        system_instruction=instruction,
        few_shots=["Q1: full marks with cited page evidence."],
        provenance="seed" if version == 1 else "meta-optimizer",
    )


def _build_engine(
    calibration: CalibrationSet,
    registry: PromptRegistry,
    evaluator: ScriptedEvaluator,
    metrics_threshold: float = 0.0,
) -> tuple[MetaOptimizerEngine, ScriptedProposer]:
    proposer = ScriptedProposer(_variant(2, CANDIDATE_INSTRUCTION))
    engine = MetaOptimizerEngine(
        proposer,
        AntiGamingValidator(calibration),
        registry,
        evaluator=evaluator,
        calibration=calibration,
        metrics_threshold=metrics_threshold,
    )
    return engine, proposer


@pytest.fixture
def calibration(make_calibration_sample) -> CalibrationSet:
    first = make_calibration_sample("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS)
    second = make_calibration_sample("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS)
    return CalibrationSet([first, second])


@pytest.fixture
def registry() -> PromptRegistry:
    registry = PromptRegistry()
    registry.register(_variant(1, BASE_INSTRUCTION))
    return registry


async def test_run_iteration_accepts_improvement_and_promotes(
    calibration, registry, make_grading_result
):
    previous = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    candidate = [
        make_grading_result("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
    ]
    evaluator = ScriptedEvaluator({1: previous, 2: candidate})
    engine, proposer = _build_engine(calibration, registry, evaluator)

    report = await engine.run_iteration()

    assert report.accepted is True
    assert report.rejected_reasons == []
    assert report.iteration == 1
    assert engine.iteration == 1
    assert report.previous_metrics.mae == pytest.approx(1.0)
    assert report.candidate_metrics.mae == pytest.approx(0.0)
    assert report.candidate_metrics.quadratic_weighted_kappa == pytest.approx(1.0)
    assert report.delta_mae == pytest.approx(-1.0)
    promoted = engine.current_variant
    assert promoted.version == 2
    assert promoted.system_instruction == CANDIDATE_INSTRUCTION
    assert [v.version for v in registry.history("grading_default")] == [1, 2]
    assert evaluator.calls == [1, 2]
    assert proposer.calls[0][0].version == 1
    assert proposer.calls[0][1].mae == pytest.approx(1.0)
    assert len(proposer.calls) == 1


async def test_run_iteration_rejects_non_improvement(
    calibration, registry, make_grading_result
):
    results = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    evaluator = ScriptedEvaluator({1: results, 2: results})
    engine, _ = _build_engine(calibration, registry, evaluator)

    report = await engine.run_iteration()

    assert report.accepted is False
    assert report.rejected_reasons[0].startswith("mae improvement")
    assert engine.current_variant.version == 1
    assert len(registry.history("grading_default")) == 1
    assert engine.iteration == 1


async def test_run_iteration_rejects_constant_output_despite_metric_gain(
    calibration, registry, make_grading_result
):
    previous = [
        make_grading_result("sub_001", {"A": 4.0, "B": 0.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 4.0, "B": 0.0}, CEILINGS),
    ]
    candidate = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    evaluator = ScriptedEvaluator({1: previous, 2: candidate})
    engine, _ = _build_engine(calibration, registry, evaluator)

    report = await engine.run_iteration()

    assert report.accepted is False
    assert any(
        reason.startswith("constant_output_detected")
        for reason in report.rejected_reasons
    )
    assert report.candidate_metrics.mae < report.previous_metrics.mae
    assert engine.current_variant.version == 1
    assert len(registry.history("grading_default")) == 1


async def test_run_iteration_enforces_metrics_threshold(
    calibration, registry, make_grading_result
):
    previous = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    candidate = [
        make_grading_result("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
    ]
    evaluator = ScriptedEvaluator({1: previous, 2: candidate})
    engine, _ = _build_engine(calibration, registry, evaluator, metrics_threshold=1.5)

    report = await engine.run_iteration()

    assert report.accepted is False
    assert "did not clear threshold" in report.rejected_reasons[0]
    assert engine.current_variant.version == 1


async def test_run_iteration_requires_registered_variant(calibration):
    evaluator = ScriptedEvaluator({1: [], 2: []})
    engine, _ = _build_engine(calibration, PromptRegistry(), evaluator)

    with pytest.raises(ValueError, match="registry has no prompt variant"):
        await engine.run_iteration()
