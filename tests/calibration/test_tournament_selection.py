import pytest

from autocurricula.core.evolution.optimizer_engine import (
    MetaOptimizerEngine,
    call_proposer,
)
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.metrics import CalibrationMetrics, OptimizerReport

pytestmark = pytest.mark.calibration

BASE_INSTRUCTION = "Assess each submission against the rubric and cite page evidence."


class AttemptAwareProposer:
    def __init__(self, candidate: PromptVariant) -> None:
        self.candidate = candidate
        self.attempts: list[int] = []

    async def __call__(self, current, metrics, attempt: int = 0) -> PromptVariant:
        self.attempts.append(attempt)
        return self.candidate


class TwoArgProposer:
    def __init__(self, candidate: PromptVariant) -> None:
        self.candidate = candidate
        self.calls = 0

    async def __call__(self, current, metrics) -> PromptVariant:
        self.calls += 1
        return self.candidate


def _metrics(mae: float, kappa: float) -> CalibrationMetrics:
    return CalibrationMetrics(mae=mae, quadratic_weighted_kappa=kappa, bias=0.0)


async def test_call_proposer_passes_attempt_only_when_supported() -> None:
    weak = PromptVariant(
        variant_id="grading_default",
        version=2,
        system_instruction="weak instruction",
        few_shots=[],
        provenance="test",
    )
    aware = AttemptAwareProposer(weak)
    plain = TwoArgProposer(weak)
    current = PromptVariant(
        variant_id="grading_default",
        version=1,
        system_instruction=BASE_INSTRUCTION,
        few_shots=[],
        provenance="seed",
    )
    zero = _metrics(1.0, 0.0)
    await call_proposer(aware, current, zero, 2)
    await call_proposer(plain, current, zero, 2)
    assert aware.attempts == [2]
    assert plain.calls == 1


def test_select_winner_ignores_rejected_and_tiebreaks_on_kappa() -> None:
    previous = _metrics(1.0, 0.0)
    low = OptimizerReport(
        iteration=1,
        previous_metrics=previous,
        candidate_metrics=_metrics(0.5, 0.2),
        delta_mae=-0.5,
        accepted=True,
    )
    high = OptimizerReport(
        iteration=2,
        previous_metrics=previous,
        candidate_metrics=_metrics(0.5, 0.8),
        delta_mae=-0.5,
        accepted=True,
    )
    rejected = OptimizerReport(
        iteration=3,
        previous_metrics=previous,
        candidate_metrics=_metrics(0.1, 0.9),
        delta_mae=-0.9,
        accepted=False,
        rejected_reasons=["variance_collapse: gamed"],
    )

    winner = MetaOptimizerEngine._select_winner([low, rejected, high])

    assert winner is high


def test_select_winner_returns_none_without_acceptance() -> None:
    previous = _metrics(1.0, 0.0)
    rejected = OptimizerReport(
        iteration=1,
        previous_metrics=previous,
        candidate_metrics=_metrics(1.5, 0.0),
        delta_mae=0.5,
        accepted=False,
        rejected_reasons=["mae improvement 0.0 did not clear threshold 0.0"],
    )
    assert MetaOptimizerEngine._select_winner([rejected]) is None
