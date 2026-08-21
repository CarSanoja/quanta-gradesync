from pydantic import Field

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.job_views import as_model
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.context import STAGE_FETCH, STAGE_GRADE, FetchOutputs
from autocurricula.schemas.common import StrictBaseModel, TzAwareDatetime
from autocurricula.schemas.grading import CriterionScore, GradingBatchResult
from autocurricula.schemas.review import ReviewItem

BATCH_HELD = "This whole batch was held for a human look as a precaution."
INJECTION_FOUND = (
    "This page contains written instructions addressed to the grader — review carefully."
)
BLURRY_SCAN = "This scan is blurry — please confirm the grade yourself."
NO_QUOTE = "The grade doesn't quote anything from the page — please double-check it."
NOT_SURE = "The grading wasn't sure about this one — please confirm it yourself."
FALLBACK_REASON = "This exam is waiting for your decision before the grade goes out."

REASON_TRANSLATIONS: tuple[tuple[str, str], ...] = (
    ("batch anomaly", BATCH_HELD),
    ("prompt injection", INJECTION_FOUND),
    ("legibility", BLURRY_SCAN),
    ("no cited evidence", NO_QUOTE),
    ("below threshold", NOT_SURE),
)


def translate_reason(reason: str) -> str:
    lowered = reason.lower()
    for needle, message in REASON_TRANSLATIONS:
        if needle in lowered:
            return message
    return FALLBACK_REASON


def translate_reasons(reasons: list[str]) -> list[str]:
    return list(dict.fromkeys(translate_reason(reason) for reason in reasons))


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
    waiting_since: TzAwareDatetime
    reasons: list[str] = Field(min_length=1)
    evidence: list[TeacherEvidenceView] = Field(default_factory=list)
    score_text: str
    percentage: float
    feedback: str
    criteria: list[TeacherCriterionView] = Field(default_factory=list)
    has_page: bool


class TeacherBatchProgress(StrictBaseModel):
    assessment: str
    received: int = Field(ge=0)
    in_gradebook: int = Field(ge=0)
    waiting_for_you: int = Field(ge=0)
    still_grading: int = Field(ge=0)
    could_not_grade: int = Field(ge=0)
    headline: str
    settled: bool


class TeacherSummary(StrictBaseModel):
    waiting: list[TeacherReviewView] = Field(default_factory=list)
    waiting_count: int = Field(ge=0)
    batch: TeacherBatchProgress | None = None


def _criterion_title(criterion_id: str, description: str | None) -> str:
    plain = description or criterion_id.replace("-", " ").replace("_", " ").strip()
    return plain[:1].upper() + plain[1:] if plain else criterion_id


def _score_for(state: SessionState | None, item: ReviewItem) -> list[CriterionScore]:
    if state is None:
        return []
    fetch = as_model(state.stage_results.get(STAGE_FETCH), FetchOutputs)
    grades = as_model(state.stage_results.get(STAGE_GRADE), GradingBatchResult)
    if grades is None:
        return []
    submissions = fetch.batch.submissions if fetch is not None else []
    target = next(
        (entry.submission_id for entry in submissions if entry.student_id == item.student_id),
        item.student_id,
    )
    scored = next((entry for entry in grades.results if entry.submission_id == target), None)
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


async def build_review_view(container: AppContainer, item: ReviewItem) -> TeacherReviewView:
    try:
        state = await container.checkpoint_store.load_state(item.job_id)
    except Exception:
        state = None
    record = item.proposed_record
    return TeacherReviewView(
        review_id=item.review_id,
        student_id=item.student_id,
        student_name=display_name(item.student_id),
        subject=item.subject,
        waiting_since=item.created_at,
        reasons=translate_reasons(item.reasons),
        evidence=[
            TeacherEvidenceView(page=span.page, quote=span.quote, note=span.rationale)
            for span in item.evidence
        ],
        score_text=f"{record.score:g} points",
        percentage=record.percentage,
        feedback=record.feedback,
        criteria=plain_criteria(state, item),
        has_page=bool(item.document_paths),
    )
