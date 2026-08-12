import inspect
from collections.abc import Awaitable, Callable, Sequence

from autocurricula.core.evolution.calibration_store import CalibrationSet
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.metrics import CalibrationMetrics

PromptProposer = Callable[..., Awaitable[PromptVariant]]
VariantEvaluator = Callable[[PromptVariant, CalibrationSet], Awaitable[Sequence[GradingResult]]]

CandidateKey = tuple[str, tuple[str, ...]]


async def call_proposer(
    proposer: PromptProposer,
    current: PromptVariant,
    metrics: CalibrationMetrics,
    attempt: int = 0,
) -> PromptVariant:
    try:
        parameters = inspect.signature(proposer).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "attempt" in parameters:
        return await proposer(current, metrics, attempt)
    return await proposer(current, metrics)


def candidate_key(variant: PromptVariant) -> CandidateKey:
    return variant.system_instruction, tuple(variant.few_shots)


def score_distributions(results: Sequence[GradingResult]) -> list[list[float]]:
    return [[score.score for score in result.criterion_scores] for result in results]
