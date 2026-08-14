import pytest

from autocurricula.core.evolution.anti_gaming_validator import AntiGamingValidator
from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.optimizer_engine import MetaOptimizerEngine
from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant
from autocurricula.schemas.grading import GradingResult

pytestmark = pytest.mark.calibration

BASE_INSTRUCTION = "Assess each submission against the rubric and cite page evidence."
CEILINGS = {"A": 4.0, "B": 4.0}


def _variant(version: int, instruction: str) -> PromptVariant:
    return PromptVariant(
        variant_id="grading_default",
        version=version,
        system_instruction=instruction,
        few_shots=["Q1: full marks with cited page evidence."],
        provenance="seed" if version == 1 else "meta-optimizer",
    )


class AttemptAwareProposer:
    def __init__(self, candidates: list[PromptVariant]) -> None:
        self._candidates = candidates
        self.attempts: list[int] = []

    async def __call__(self, current, metrics, attempt: int = 0) -> PromptVariant:
        self.attempts.append(attempt)
        return self._candidates[min(attempt, len(self._candidates) - 1)]


class ByInstructionEvaluator:
    def __init__(self, results_by_instruction: dict[str, list[GradingResult]]) -> None:
        self._results = results_by_instruction
        self.calls: list[str] = []

    async def __call__(self, variant, calibration) -> list[GradingResult]:
        self.calls.append(variant.system_instruction)
        return self._results[variant.system_instruction]


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


async def test_tournament_promotes_best_accepted_candidate(
    calibration, registry, make_grading_result
) -> None:
    mediocre_instruction = "mediocre mutation with partial mastery language"
    perfect_instruction = "perfect mutation with full mastery language"
    previous = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    mediocre = [
        make_grading_result("sub_001", {"A": 2.5, "B": 1.5}, CEILINGS),
        make_grading_result("sub_002", {"A": 1.5, "B": 2.5}, CEILINGS),
    ]
    perfect = [
        make_grading_result("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
    ]
    evaluator = ByInstructionEvaluator(
        {
            BASE_INSTRUCTION: previous,
            mediocre_instruction: mediocre,
            perfect_instruction: perfect,
        }
    )
    engine = MetaOptimizerEngine(
        AttemptAwareProposer(
            [_variant(2, mediocre_instruction), _variant(2, perfect_instruction)]
        ),
        AntiGamingValidator(calibration),
        registry,
        evaluator=evaluator,
        calibration=calibration,
    )

    tournament = await engine.run_tournament(2)

    assert tournament.winner is not None
    assert tournament.winner.candidate_metrics.mae == pytest.approx(0.0)
    assert tournament.winner.accepted is True
    assert len(tournament.candidates) == 2
    assert engine.current_variant.system_instruction == perfect_instruction
    assert [v.version for v in registry.history("grading_default")] == [1, 2]


async def test_tournament_without_acceptance_promotes_nothing(
    calibration, registry, make_grading_result
) -> None:
    worse_instruction = "worse mutation that loses agreement"
    previous = [
        make_grading_result("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
    ]
    worse = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    evaluator = ByInstructionEvaluator(
        {BASE_INSTRUCTION: previous, worse_instruction: worse}
    )
    engine = MetaOptimizerEngine(
        AttemptAwareProposer([_variant(2, worse_instruction)]),
        AntiGamingValidator(calibration),
        registry,
        evaluator=evaluator,
        calibration=calibration,
    )

    tournament = await engine.run_tournament(3)

    assert tournament.winner is None
    assert all(not report.accepted for report in tournament.candidates)
    assert engine.current_variant.version == 1
    assert len(registry.history("grading_default")) == 1


async def test_tournament_dedupes_identical_candidates(
    calibration, registry, make_grading_result
) -> None:
    candidate_instruction = "single repeated mutation"
    previous = [
        make_grading_result("sub_001", {"A": 2.0, "B": 2.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 2.0, "B": 2.0}, CEILINGS),
    ]
    perfect = [
        make_grading_result("sub_001", {"A": 3.0, "B": 1.0}, CEILINGS),
        make_grading_result("sub_002", {"A": 1.0, "B": 3.0}, CEILINGS),
    ]
    evaluator = ByInstructionEvaluator(
        {BASE_INSTRUCTION: previous, candidate_instruction: perfect}
    )
    proposer = AttemptAwareProposer([_variant(2, candidate_instruction)])
    engine = MetaOptimizerEngine(
        proposer,
        AntiGamingValidator(calibration),
        registry,
        evaluator=evaluator,
        calibration=calibration,
    )

    tournament = await engine.run_tournament(3)

    assert proposer.attempts == [0, 1, 2]
    assert len(tournament.candidates) == 1
    assert evaluator.calls.count(candidate_instruction) == 1
    assert tournament.winner is not None


async def test_tournament_rejects_invalid_candidate_count(calibration, registry) -> None:
    engine = MetaOptimizerEngine(
        AttemptAwareProposer([_variant(2, "x")]),
        AntiGamingValidator(calibration),
        registry,
        evaluator=ByInstructionEvaluator({}),
        calibration=calibration,
    )
    with pytest.raises(ValueError):
        await engine.run_tournament(0)
