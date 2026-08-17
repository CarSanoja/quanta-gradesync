from collections.abc import Awaitable, Callable

from pydantic import Field

from autocurricula.core.evolution.calibration_store import (
    CalibrationSet,
    compute_calibration_metrics,
)
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.metrics import CalibrationMetrics

VariantRunner = Callable[[PromptVariant, CalibrationSet], Awaitable[list[GradingResult]]]


class GoldenSummary(StrictBaseModel):
    samples: int = Field(ge=1)
    metrics: CalibrationMetrics


class EvalRunner:
    def __init__(self, calibration: CalibrationSet, variant_runner: VariantRunner) -> None:
        self._calibration = calibration
        self._variant_runner = variant_runner

    async def evaluate(self, variant: PromptVariant) -> GoldenSummary:
        results = await self._variant_runner(variant, self._calibration)
        metrics = compute_calibration_metrics(results, self._calibration.samples)
        return GoldenSummary(samples=len(self._calibration), metrics=metrics)
