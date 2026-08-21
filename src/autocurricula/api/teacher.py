from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.gcs_notification import derive_job_id
from autocurricula.api.ingest_storage import build_ingest_storage, upload_object_name
from autocurricula.api.job_views import JobDetail, build_detail
from autocurricula.api.teacher_views import (
    TeacherBatchProgress,
    TeacherSummary,
    build_review_view,
    display_name,
)
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.core.orchestration.manifest_inference import parse_lot_code
from autocurricula.schemas.review import ReviewItem

teacher_router = APIRouter(tags=["teacher"])

STATIC_DIR = Path(__file__).parent / "static"
TEACHER_PAGE = "teacher.html"

ASSET_MEDIA_TYPES = {
    "teacher.css": "text/css; charset=utf-8",
    "teacher.js": "text/javascript; charset=utf-8",
    "teacher-upload.js": "text/javascript; charset=utf-8",
}

SETTLED_STAGES = frozenset({JobStage.COMPLETED, JobStage.FAILED})
UNKNOWN_ASSESSMENT = "this batch"
NOT_STARTED = "Grading starts on its own — nothing for you to do yet."
NOTHING_YET = "Grading has started — nothing is in the gradebook yet."


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
    in_gradebook = detail.synced_count if detail is not None else 0
    could_not = detail.failed_count if detail is not None else 0
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
    headline = batch_headline(progress, detail is not None)
    return progress.model_copy(update={"headline": headline})


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@teacher_router.get("/teacher", response_class=FileResponse)
async def teacher_page() -> FileResponse:
    page = STATIC_DIR / TEACHER_PAGE
    if not page.is_file():
        raise _not_found("teacher page is not bundled")
    return FileResponse(page, media_type="text/html; charset=utf-8")


@teacher_router.get("/teacher/assets/{asset_name}", response_class=FileResponse)
async def teacher_asset(asset_name: str) -> FileResponse:
    media_type = ASSET_MEDIA_TYPES.get(asset_name)
    if media_type is None:
        raise _not_found(f"unknown teacher asset {asset_name!r}")
    path = STATIC_DIR / asset_name
    if not path.is_file():
        raise _not_found(f"teacher asset {asset_name!r} is not bundled")
    return FileResponse(path, media_type=media_type)


@teacher_router.get("/teacher/summary", response_model=TeacherSummary)
async def teacher_summary(
    request: Request,
    batch: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> TeacherSummary:
    require_push_token(request, container.settings.pubsub_push_token)
    items = await container.review_service.list_pending()
    waiting = [await build_review_view(container, item) for item in items]
    progress = await build_batch_progress(container, batch, items) if batch else None
    return TeacherSummary(waiting=waiting, waiting_count=len(waiting), batch=progress)
