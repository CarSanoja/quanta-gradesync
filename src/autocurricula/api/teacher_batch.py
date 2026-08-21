from pydantic import Field

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.gcs_notification import derive_job_id
from autocurricula.api.ingest_storage import build_ingest_storage, upload_object_name
from autocurricula.api.job_views import JobDetail, build_detail
from autocurricula.api.teacher_views import display_name
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.core.orchestration.manifest_inference import parse_lot_code
from autocurricula.schemas.common import StrictBaseModel, utc_now
from autocurricula.schemas.labels import LabelDecision
from autocurricula.schemas.review import ReviewItem

SETTLED_STAGES = frozenset({JobStage.COMPLETED, JobStage.FAILED})
LABEL_SCAN_LIMIT = 1000
WRITTEN_DECISIONS = frozenset({LabelDecision.APPROVE, LabelDecision.OVERRIDE})
UNKNOWN_ASSESSMENT = "this batch"
NOT_STARTED = "Grading starts on its own — nothing for you to do yet."
NOTHING_YET = "Grading has started — nothing is in the gradebook yet."


class TeacherBatchProgress(StrictBaseModel):
    assessment: str
    received: int = Field(ge=0)
    in_gradebook: int = Field(ge=0)
    waiting_for_you: int = Field(ge=0)
    still_grading: int = Field(ge=0)
    could_not_grade: int = Field(ge=0)
    minutes_left: int | None = Field(default=None, ge=0)
    headline: str
    settled: bool


def batch_prefix(lot_code: str) -> str:
    return upload_object_name(lot_code, "")


def batch_job_id(lot_code: str) -> str:
    return derive_job_id(batch_prefix(lot_code).rstrip("/"))


def assessment_title(lot_code: str) -> str:
    try:
        return display_name(parse_lot_code(lot_code).assessment)
    except Exception:
        return UNKNOWN_ASSESSMENT


def exam_count(count: int) -> str:
    return "1 exam" if count == 1 else f"{count} exams"


def join_clauses(clauses: list[str]) -> str:
    if len(clauses) == 1:
        return clauses[0]
    return f"{', '.join(clauses[:-1])} and {clauses[-1]}"


def _clause(count: int, tail: str) -> str:
    return f"{count} {'is' if count == 1 else 'are'} {tail}"


def progress_line(progress: TeacherBatchProgress, started: bool) -> str:
    if not started:
        return NOT_STARTED
    clauses: list[str] = []
    if progress.in_gradebook:
        clauses.append(_clause(progress.in_gradebook, "already in the gradebook"))
    if progress.waiting_for_you:
        clauses.append(_clause(progress.waiting_for_you, "waiting for your review"))
    if progress.could_not_grade:
        clauses.append(f"{progress.could_not_grade} could not be graded")
    if not clauses:
        return NOTHING_YET
    return f"Grading has started — {join_clauses(clauses)}."


def batch_headline(progress: TeacherBatchProgress, started: bool) -> str:
    total = exam_count(progress.received)
    if progress.settled and progress.in_gradebook >= progress.received:
        return f"All {total} for {progress.assessment} are in the gradebook."
    opening = f"We received {total} for {progress.assessment}."
    return f"{opening} {progress_line(progress, started)}"


def minutes_left(detail: JobDetail | None, progress: TeacherBatchProgress) -> int | None:
    if progress.still_grading <= 0:
        return 0
    if detail is None:
        return None
    settled = progress.in_gradebook + progress.waiting_for_you + progress.could_not_grade
    if settled <= 0:
        return None
    elapsed = (utc_now() - detail.job.triggered_at).total_seconds()
    if elapsed <= 0:
        return None
    remaining = (elapsed / settled) * progress.still_grading
    return max(1, round(remaining / 60))


async def count_received(container: AppContainer, lot_code: str) -> int:
    try:
        storage = build_ingest_storage(container.settings)
        return await storage.count_objects(batch_prefix(lot_code))
    except Exception:
        return 0


async def load_batch_detail(container: AppContainer, job_id: str) -> JobDetail | None:
    try:
        record = await container.checkpoint_store.get(job_id)
    except Exception:
        return None
    if record is None:
        return None
    try:
        state = await container.checkpoint_store.load_state(job_id)
    except Exception:
        state = None
    return build_detail(record, state)


async def decided_counts(container: AppContainer, job_id: str) -> tuple[int, int]:
    try:
        labels = await container.review_service.label_store.list_labels(
            job_id=job_id, limit=LABEL_SCAN_LIMIT
        )
    except Exception:
        return 0, 0
    written = sum(1 for label in labels if label.decision in WRITTEN_DECISIONS)
    returned = sum(1 for label in labels if label.decision is LabelDecision.DISMISS)
    return written, returned


async def build_batch_progress(
    container: AppContainer, lot_code: str, pending: list[ReviewItem]
) -> TeacherBatchProgress | None:
    job_id = batch_job_id(lot_code)
    detail = await load_batch_detail(container, job_id)
    received = await count_received(container, lot_code)
    if detail is not None:
        received = max(received, detail.submission_count)
    if received == 0:
        return None
    waiting = sum(1 for item in pending if item.job_id == job_id)
    written, returned = await decided_counts(container, job_id)
    in_gradebook = (detail.synced_count if detail is not None else 0) + written
    could_not = (detail.failed_count if detail is not None else 0) + returned
    accounted = in_gradebook + waiting + could_not
    finished = detail is not None and detail.job.stage in SETTLED_STAGES
    progress = TeacherBatchProgress(
        assessment=assessment_title(lot_code),
        received=received,
        in_gradebook=in_gradebook,
        waiting_for_you=waiting,
        still_grading=max(received - accounted, 0),
        could_not_grade=could_not,
        headline="",
        settled=finished and accounted >= received,
    )
    return progress.model_copy(
        update={
            "headline": batch_headline(progress, detail is not None),
            "minutes_left": minutes_left(detail, progress),
        }
    )
