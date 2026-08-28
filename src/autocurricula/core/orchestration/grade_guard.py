import logging
from typing import Any

from autocurricula.core.armor import InjectionDetector, screen_submission
from autocurricula.core.fleet import (
    ARMOR_SCREENER_ID,
    FALLBACK_EVALUATOR_ID,
    GRADING_AGENT_ID,
    SCHEMA_REPAIR_ID,
    annotate_span,
    authorize_llm,
)
from autocurricula.core.harness import (
    CapabilityDenied,
    PageTextProvider,
    enforce_result,
    verify_result,
)
from autocurricula.core.orchestration.grade_outcome import GradeOutcome, build_failure
from autocurricula.core.resilience import (
    DeadLetterEntry,
    DeadLetterStore,
    FallbackEvaluator,
    RepairBudgetExhausted,
    SchemaRepairAgent,
)
from autocurricula.core.telemetry import Recorder, usage_scope
from autocurricula.core.telemetry.tracer import SpanHandle
from autocurricula.schemas.armor import ArmorVerdict
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.telemetry import (
    ATTR_EVIDENCE_SPAN_MATCH,
    ATTR_EVIDENCE_SPAN_VERIFICATION,
    ATTR_GEN_AI_CALLS,
    ATTR_GEN_AI_SYSTEM,
    ATTR_GEN_AI_USAGE_INPUT_TOKENS,
    ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
    ATTR_SUBMISSION_OUTCOME,
    OUTCOME_FAILED,
    OUTCOME_GRADED,
    VERIFICATION_FAILED,
    VERIFICATION_UNCHECKED,
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
        armor: InjectionDetector | None = None,
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
        self.armor = armor
        self.armor_verdicts: dict[str, ArmorVerdict] = {}
        self.faithfulness_status: dict[str, str] = {}

    async def grade(self, submission, rubric, retrieved) -> GradeOutcome:
        with self.recorder.span(
            f"Grading_{submission.submission_id}",
            stage="GRADE",
            attributes={
                ATTR_GEN_AI_SYSTEM: "google_gemini",
                "gen_ai.model": self.model_id,
                "student_id": submission.student_id,
            },
        ) as span:
            annotate_span(span, GRADING_AGENT_ID)
            with usage_scope() as ledger:
                result, detail = await self._guarded(submission, rubric, retrieved, span)
            span.set(ATTR_GEN_AI_CALLS, ledger.calls)
            span.set(ATTR_GEN_AI_USAGE_INPUT_TOKENS, ledger.input_tokens)
            span.set(ATTR_GEN_AI_USAGE_OUTPUT_TOKENS, ledger.output_tokens)
            if result is None:
                span.set("harness.isolated", True)
                span.set(ATTR_SUBMISSION_OUTCOME, OUTCOME_FAILED)
                return GradeOutcome(
                    submission_id=submission.submission_id,
                    student_id=submission.student_id,
                    failure=build_failure(submission, detail or "grading returned nothing"),
                )
            span.set(ATTR_SUBMISSION_OUTCOME, OUTCOME_GRADED)
            self._sign_helpers(submission, span)
            if self.armor is not None:
                await self._screen_armor(submission, span)
            if self.provider is not None:
                result = self._enforce_faithfulness(submission, result, span)
            else:
                self.faithfulness_status[submission.submission_id] = VERIFICATION_UNCHECKED
            return GradeOutcome(
                submission_id=submission.submission_id,
                student_id=submission.student_id,
                result=result,
            )

    def _sign_helpers(self, submission, span: SpanHandle) -> None:
        """Record which stand-in agents handled this exam, if any.

        The failover and the repair loop are plain logic with no recorder of
        their own, so their work reached the model without ever carrying an
        identity — the fallback graded two exams on 2026-08-28 with its card
        dark on the live board. They report what they did; this writes it down.
        """
        if getattr(self.evaluator, "last_used_fallback", False):
            with self.recorder.span(
                f"Fallback_{submission.submission_id}", parent=span, stage="GRADE"
            ) as fallback:
                annotate_span(fallback, FALLBACK_EVALUATOR_ID)
                fallback.set("student_id", submission.student_id)
                fallback.set("fallback.reason", "primary timed out or was exhausted")
        attempts = getattr(self.repair_agent, "last_attempts", 0)
        if attempts:
            with self.recorder.span(
                f"SchemaRepair_{submission.submission_id}", parent=span, stage="GRADE"
            ) as repair:
                annotate_span(repair, SCHEMA_REPAIR_ID)
                repair.set("student_id", submission.student_id)
                repair.set("repair.attempts", attempts)

    async def _screen_armor(self, submission, span: SpanHandle) -> None:
        with self.recorder.span(
            "ArmorScreen", parent=span, stage="GRADE"
        ) as armor_span:
            annotate_span(armor_span, ARMOR_SCREENER_ID)
            authorize_llm(
                ARMOR_SCREENER_ID,
                submission.submission_id,
                model_id=getattr(self.armor, "model", ""),
                recorder=self.recorder,
                parent=armor_span,
            )
            verdict = await screen_submission(self.armor, submission)
            armor_span.set("armor.injection_detected", verdict.injection_detected)
            armor_span.set("armor.severity", verdict.severity.value)
            self.armor_verdicts[submission.submission_id] = verdict

    async def _guarded(
        self, submission, rubric, retrieved, span: SpanHandle | None = None
    ) -> tuple[GradingResult | None, str]:
        def operation(attempt):
            return self.evaluator.grade(submission, rubric, retrieved)

        try:
            authorize_llm(
                GRADING_AGENT_ID,
                submission.submission_id,
                model_id=self.model_id,
                recorder=self.recorder,
                parent=span,
            )
        except CapabilityDenied as denial:
            detail = f"{type(denial).__name__}: {denial}"
            await self._dead_letter(submission, detail)
            return None, detail
        try:
            if self.repair_agent is not None:
                return await self.repair_agent.run(operation), ""
            return await operation(0), ""
        except RepairBudgetExhausted as exhaustion:
            detail = f"{type(exhaustion).__name__}: {exhaustion}"
        except Exception as error:
            detail = f"{type(error).__name__}: {error}"
        await self._dead_letter(submission, detail)
        return None, detail

    def _enforce_faithfulness(
        self, submission, result: GradingResult, span: SpanHandle
    ) -> GradingResult:
        with self.recorder.span(
            "FaithfulnessVerification", parent=span, stage="GRADE"
        ) as faith:
            report = verify_result(result, self.provider)
            status = report.status
            self.faithfulness_status[submission.submission_id] = status
            faith.set(ATTR_EVIDENCE_SPAN_VERIFICATION, status)
            faith.set("evidence.spans_verified", report.verified_spans)
            faith.set("evidence.spans_unchecked", report.unchecked_spans)
            if report.checked:
                faith.set(ATTR_EVIDENCE_SPAN_MATCH, status != VERIFICATION_FAILED)
            if status == VERIFICATION_FAILED:
                return enforce_result(result, self.provider)
            return result

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
