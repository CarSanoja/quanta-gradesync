from pydantic import Field

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.job_views import as_model
from autocurricula.api.teacher_feedback import TeacherFeedbackView, build_feedback_view
from autocurricula.api.teacher_reasons import (
    BATCH_HELD,
    BLURRY_SCAN,
    COULD_NOT_GRADE,
    FALLBACK_REASON,
    INJECTION_FOUND,
    LATE_SCAN,
    NO_QUOTE,
    NOT_SURE,
    REASON_TRANSLATIONS,
    reason_key,
    translate_reason,
    translate_reasons,
)
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.context import STAGE_FETCH, STAGE_GRADE, FetchOutputs
from autocurricula.core.review.triage import judgement_reasons, triage_group
from autocurricula.schemas.common import StrictBaseModel, TzAwareDatetime
from autocurricula.schemas.grading import CriterionScore, GradingBatchResult, GradingResult
from autocurricula.schemas.review import ReviewItem


def display_name(student_id: str) -> str:
    normalized = student_id.replace("_", "-").replace(".", "-")
    parts = [part for part in normalized.split("-") if part]
    return " ".join(part[:1].upper() + part[1:] for part in parts) or student_id


def points_text(value: float, ceiling: float | None) -> str:
    return f"{value:g} points" if ceiling is None else f"{value:g} of {ceiling:g} points"


class TeacherEvidenceView(StrictBaseModel):
    page: int = Field(ge=1)
    quote: str
    note: str


class TeacherCriterionView(StrictBaseModel):
    title: str
    score_text: str
    comment: str


class TeacherReviewView(StrictBaseModel):
    review_id: str
    student_id: str
    student_name: str
    subject: str
    job_id: str
    group: str
    reason_key: str
    primary_reason: str
    waiting_since: TzAwareDatetime
    reasons: list[str] = Field(min_length=1)
    evidence: list[TeacherEvidenceView] = Field(default_factory=list)
    score_text: str
    percentage: float
    feedback: str
    student_feedback: TeacherFeedbackView | None = None
    criteria: list[TeacherCriterionView] = Field(default_factory=list)
    has_page: bool


def _criterion_title(criterion_id: str, description: str | None) -> str:
    plain = description or criterion_id.replace("-", " ").replace("_", " ").strip()
    return plain[:1].upper() + plain[1:] if plain else criterion_id


def graded_result(state: SessionState | None, item: ReviewItem) -> GradingResult | None:
    if state is None:
        return None
    fetch = as_model(state.stage_results.get(STAGE_FETCH), FetchOutputs)
    grades = as_model(state.stage_results.get(STAGE_GRADE), GradingBatchResult)
    if grades is None:
        return None
    submissions = fetch.batch.submissions if fetch is not None else []
    target = next(
        (entry.submission_id for entry in submissions if entry.student_id == item.student_id),
        item.student_id,
    )
    return next((entry for entry in grades.results if entry.submission_id == target), None)


def _score_for(state: SessionState | None, item: ReviewItem) -> list[CriterionScore]:
    scored = graded_result(state, item)
    return list(scored.criterion_scores) if scored is not None else []


def _rubric_index(state: SessionState | None) -> dict[str, tuple[str, float]]:
    if state is None:
        return {}
    fetch = as_model(state.stage_results.get(STAGE_FETCH), FetchOutputs)
    if fetch is None:
        return {}
    return {
        criterion.criterion_id: (criterion.description, criterion.max_score)
        for criterion in fetch.rubric.criteria
    }


def plain_criteria(state: SessionState | None, item: ReviewItem) -> list[TeacherCriterionView]:
    rubric = _rubric_index(state)
    views: list[TeacherCriterionView] = []
    for score in _score_for(state, item):
        description, ceiling = rubric.get(score.criterion_id, (None, None))
        views.append(
            TeacherCriterionView(
                title=_criterion_title(score.criterion_id, description),
                score_text=points_text(score.score, ceiling),
                comment=score.comment,
            )
        )
    return views


def _primary_reason(item: ReviewItem) -> str:
    own = judgement_reasons(item)
    return own[0] if own else item.reasons[0]


async def load_state(
    container: AppContainer, job_id: str, cache: dict[str, SessionState | None] | None
) -> SessionState | None:
    if cache is not None and job_id in cache:
        return cache[job_id]
    try:
        state = await container.checkpoint_store.load_state(job_id)
    except Exception:
        state = None
    if cache is not None:
        cache[job_id] = state
    return state


async def build_review_view(
    container: AppContainer,
    item: ReviewItem,
    cache: dict[str, SessionState | None] | None = None,
) -> TeacherReviewView:
    state = await load_state(container, item.job_id, cache)
    record = item.proposed_record
    primary = _primary_reason(item)
    return TeacherReviewView(
        review_id=item.review_id,
        student_id=item.student_id,
        student_name=display_name(item.student_id),
        subject=item.subject,
        job_id=item.job_id,
        group=triage_group(item),
        reason_key=reason_key(primary),
        primary_reason=translate_reason(primary),
        waiting_since=item.created_at,
        reasons=translate_reasons(item.reasons),
        evidence=[
            TeacherEvidenceView(page=span.page, quote=span.quote, note=span.rationale)
            for span in item.evidence
        ],
        score_text=f"{record.score:g} points",
        percentage=record.percentage,
        feedback=record.feedback,
        student_feedback=build_feedback_view(record, graded_result(state, item)),
        criteria=plain_criteria(state, item),
        has_page=bool(item.document_paths),
    )


__all__ = [
    "BATCH_HELD",
    "BLURRY_SCAN",
    "COULD_NOT_GRADE",
    "FALLBACK_REASON",
    "INJECTION_FOUND",
    "LATE_SCAN",
    "NOT_SURE",
    "NO_QUOTE",
    "REASON_TRANSLATIONS",
    "TeacherCriterionView",
    "TeacherEvidenceView",
    "TeacherReviewView",
    "build_review_view",
    "display_name",
    "graded_result",
    "plain_criteria",
    "points_text",
    "reason_key",
    "translate_reason",
    "translate_reasons",
]
