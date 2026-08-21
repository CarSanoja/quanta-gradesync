from dataclasses import dataclass, field

from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.catalog import JobCatalog
from autocurricula.core.orchestration.context import STAGE_GRADE
from autocurricula.core.orchestration.job_state import CheckpointStore
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.schemas.review import ReviewItem


@dataclass(frozen=True)
class ReviewContext:
    ceilings: dict[str, float] = field(default_factory=dict)
    machine_scores: dict[str, float] = field(default_factory=dict)


async def load_review_context(
    item: ReviewItem, checkpoint_store: CheckpointStore, catalog: JobCatalog
) -> ReviewContext:
    record = await _quiet(checkpoint_store.get(item.job_id))
    manifest = None
    if record is not None:
        manifest = await _quiet(catalog.load_manifest(record.event))
    ceilings = (
        {
            criterion.criterion_id: criterion.max_score
            for criterion in manifest.rubric.criteria
        }
        if manifest is not None
        else {}
    )
    state = await _quiet(checkpoint_store.load_state(item.job_id))
    batch = _resolve_batch(state, manifest)
    return ReviewContext(
        ceilings=ceilings,
        machine_scores=_machine_scores(state, batch, item.student_id),
    )


def _resolve_batch(state: SessionState | None, manifest) -> ExamBatch | None:
    if state is not None and state.batch is not None:
        return state.batch
    return manifest.batch if manifest is not None else None


def _submission_ids(batch: ExamBatch | None, student_id: str) -> set[str]:
    if batch is None:
        return {student_id}
    return {
        submission.submission_id
        for submission in batch.submissions
        if submission.student_id == student_id
    }


def _machine_scores(
    state: SessionState | None, batch: ExamBatch | None, student_id: str
) -> dict[str, float]:
    if state is None:
        return {}
    raw = state.stage_results.get(STAGE_GRADE)
    if raw is None:
        return {}
    try:
        grade_result = GradingBatchResult.model_validate(
            raw if isinstance(raw, dict) else raw.model_dump(mode="json")
        )
    except Exception:
        return {}
    submissions = _submission_ids(batch, student_id)
    for result in grade_result.results:
        if result.submission_id in submissions:
            return {
                score.criterion_id: score.score for score in result.criterion_scores
            }
    return {}


async def _quiet(awaitable):
    try:
        return await awaitable
    except Exception:
        return None
