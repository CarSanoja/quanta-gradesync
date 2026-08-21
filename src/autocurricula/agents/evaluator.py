from typing import Protocol

from pydantic import ValidationError

from autocurricula.agents.base import AgentResponseError, parse_model_json
from autocurricula.schemas.exam import ExamSubmission
from autocurricula.schemas.feedback import FeedbackBand
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric

STUDENT_FEEDBACK_KEY = "student_feedback"


class GradingValidationError(AgentResponseError):
    pass


class GradingEvaluator(Protocol):
    async def grade(
        self, submission: ExamSubmission, rubric: Rubric, context: RetrievedContext
    ) -> GradingResult: ...


class BandAwareEvaluator(Protocol):
    def for_grade_level(self, grade_level: str | None) -> GradingEvaluator: ...


def bind_feedback_band(
    evaluator: GradingEvaluator | None, grade_level: str | None
) -> GradingEvaluator | None:
    if evaluator is None:
        return None
    binder = getattr(evaluator, "for_grade_level", None)
    if binder is None:
        return evaluator
    return binder(grade_level)


def stamp_feedback_band(
    result: GradingResult, band: FeedbackBand | None
) -> GradingResult:
    feedback = result.student_feedback
    if feedback is None:
        return result
    if band is None:
        return result.model_copy(update={STUDENT_FEEDBACK_KEY: None})
    if feedback.band == band:
        return result
    return result.model_copy(
        update={STUDENT_FEEDBACK_KEY: feedback.model_copy(update={"band": band})}
    )


def salvage_without_student_feedback(
    error: AgentResponseError,
) -> GradingResult | None:
    if not error.raw:
        return None
    try:
        payload = parse_model_json(error.raw)
    except AgentResponseError:
        return None
    if not isinstance(payload, dict) or STUDENT_FEEDBACK_KEY not in payload:
        return None
    candidate = {
        key: value for key, value in payload.items() if key != STUDENT_FEEDBACK_KEY
    }
    try:
        return GradingResult.model_validate(candidate)
    except ValidationError:
        return None
