import logging
from typing import Any

from autocurricula.core.harness import (
    PageTextProvider,
    SidecarTextProvider,
    enforce_result,
    sidecar_texts_from_batch,
    verify_result,
)
from autocurricula.core.resilience import (
    DeadLetterEntry,
    DeadLetterStore,
    FallbackEvaluator,
    RepairBudgetExhausted,
    SchemaRepairAgent,
)
from autocurricula.core.telemetry import Recorder
from autocurricula.core.telemetry.tracer import SpanHandle
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.telemetry import (
    ATTR_EVIDENCE_SPAN_MATCH,
    ATTR_GEN_AI_SYSTEM,
)

logger = logging.getLogger(__name__)

DLQ_KIND_GRADING = "grading"


class GradeGuard:
    def __init__(
        self,
        *,
        job_id: str,
        evaluator: Any,
        fallback: Any | None,
        latency_seconds: float,
        confidence_factor: float,
        repair_agent: SchemaRepairAgent | None,
        dead_letter: DeadLetterStore | None,
        dead_letter_max_attempts: int,
        model_id: str,
        recorder: Recorder,
        provider: PageTextProvider | None,
    ) -> None:
        self.job_id = job_id
        self.evaluator = FallbackEvaluator(
            evaluator,
            fallback,
            latency_seconds=latency_seconds,
            confidence_factor=confidence_factor,
        )
        self.repair_agent = repair_agent
        self.dead_letter = dead_letter
        self.dead_letter_max_attempts = dead_letter_max_attempts
        self.model_id = model_id
        self.recorder = recorder
        self.provider = provider

    async def grade(self, submission, rubric, retrieved) -> GradingResult | None:
        with self.recorder.span(
            f"Grading_{submission.submission_id}",
            stage="GRADE",
            attributes={
                ATTR_GEN_AI_SYSTEM: "google_gemini",
                "gen_ai.model": self.model_id,
                "student_id": submission.student_id,
            },
        ) as span:
            result = await self._guarded(submission, rubric, retrieved, span)
            if result is None:
                span.set("harness.isolated", True)
                return None
            if self.provider is not None:
                result = self._enforce_faithfulness(submission, result, span)
            return result

    async def _guarded(self, submission, rubric, retrieved, span: SpanHandle):
        operation = lambda attempt: self.evaluator.grade(
            submission, rubric, retrieved
        )
        try:
            if self.repair_agent is not None:
                return await self.repair_agent.run(operation)
            return await operation(0)
        except RepairBudgetExhausted as exhaustion:
            await self._dead_letter(
                submission, f"{type(exhaustion).__name__}: {exhaustion}"
            )
            return None
        except Exception as error:
            await self._dead_letter(
                submission, f"{type(error).__name__}: {error}"
            )
            return None

    def _enforce_faithfulness(
        self, submission, result: GradingResult, span: SpanHandle
    ) -> GradingResult:
        with self.recorder.span(
            "FaithfulnessVerification", parent=span, stage="GRADE"
        ) as faith:
            report = verify_result(result, self.provider)
            matched = not report.hallucinated
            faith.set(ATTR_EVIDENCE_SPAN_MATCH, matched)
            if matched:
                return result
            return enforce_result(result, self.provider)

    async def _dead_letter(self, submission, reason: str) -> None:
        logger.warning(
            "isolating submission %s: %s", submission.submission_id, reason
        )
        if self.dead_letter is None:
            return
        attempts = self.repair_agent.last_attempts if self.repair_agent else 0
        await self.dead_letter.record(
            DeadLetterEntry(
                kind=DLQ_KIND_GRADING,
                job_id=self.job_id,
                target=submission.submission_id,
                reason=reason,
                attempts=max(1, attempts),
                max_attempts=self.dead_letter_max_attempts,
            )
        )


def build_grade_guard(
    *,
    job_id: str,
    evaluator: Any,
    fallback: Any | None,
    latency_seconds: float,
    confidence_factor: float,
    repair_agent: SchemaRepairAgent | None,
    dead_letter: DeadLetterStore | None,
    dead_letter_max_attempts: int,
    model_id: str,
    recorder: Recorder | None,
    faithfulness_enabled: bool,
    batch: Any,
) -> GradeGuard:
    provider = (
        SidecarTextProvider(sidecar_texts_from_batch(batch))
        if faithfulness_enabled
        else None
    )
    return GradeGuard(
        job_id=job_id,
        evaluator=evaluator,
        fallback=fallback,
        latency_seconds=latency_seconds,
        confidence_factor=confidence_factor,
        repair_agent=repair_agent,
        dead_letter=dead_letter,
        dead_letter_max_attempts=dead_letter_max_attempts,
        model_id=model_id,
        recorder=recorder,
        provider=provider,
    )
