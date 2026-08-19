import time
from collections.abc import Awaitable, Callable

from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric

TRANSIENT_ERROR_TYPES = (TimeoutError,)


class ResourceExhaustedError(RuntimeError):
    pass


class FallbackEvaluator:
    def __init__(
        self,
        primary: Callable,
        fallback: Callable | None,
        *,
        latency_seconds: float,
        confidence_factor: float,
        transient_errors: tuple[type[Exception], ...] = TRANSIENT_ERROR_TYPES,
    ) -> None:
        if latency_seconds <= 0:
            raise ValueError("latency_seconds must be positive")
        if not 0.0 < confidence_factor <= 1.0:
            raise ValueError("confidence_factor must be within (0, 1]")
        self._primary = primary
        self._fallback = fallback
        self._latency_seconds = latency_seconds
        self._confidence_factor = confidence_factor
        self._transient = transient_errors
        self.last_used_fallback = False

    async def grade(
        self, submission, rubric: Rubric, context: RetrievedContext
    ) -> GradingResult:
        self.last_used_fallback = False
        started = time.monotonic()
        try:
            result = await self._primary.grade(submission, rubric, context)
        except self._transient + (ResourceExhaustedError,) as error:
            return await self._on_fallback(submission, rubric, context, error)
        elapsed = time.monotonic() - started
        if elapsed > self._latency_seconds:
            return await self._on_fallback(
                submission, rubric, context, TimeoutError()
            )
        return result

    async def _on_fallback(
        self, submission, rubric: Rubric, context: RetrievedContext, cause: Exception
    ) -> GradingResult:
        if self._fallback is None:
            raise cause
        self.last_used_fallback = True
        result = await self._fallback.grade(submission, rubric, context)
        return _scale_confidence(result, self._confidence_factor)


def _scale_confidence(result: GradingResult, factor: float) -> GradingResult:
    scaled = [
        criterion.model_copy(
            update={"confidence": round(criterion.confidence * factor, 4)}
        )
        for criterion in result.criterion_scores
    ]
    return result.model_copy(update={"criterion_scores": scaled})


FallbackFactory = Callable[[], Awaitable[FallbackEvaluator]]
