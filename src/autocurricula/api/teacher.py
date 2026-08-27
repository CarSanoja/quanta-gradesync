from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.ingest_storage import build_ingest_storage
from autocurricula.api.job_index import list_job_records
from autocurricula.api.teacher_batch import (
    TeacherBatchProgress,
    batch_job_id,
    build_batch_progress,
    decided_counts,
)
from autocurricula.api.teacher_triage import TeacherSummary, build_summary
from autocurricula.api.teacher_views import TeacherReviewView, build_review_view
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.job_state import JobRecord
from autocurricula.core.orchestration.manifest_inference import LOT_CODE_PATTERN
from autocurricula.schemas.common import TzAwareDatetime
from autocurricula.schemas.review import ReviewItem

teacher_router = APIRouter(tags=["teacher"])

STATIC_DIR = Path(__file__).parent / "static"
TEACHER_PAGE = "teacher.html"
MAX_RECENT_BATCHES = 10

TEACHER_MODULES = (
    "teacher.js",
    "teacher-actions.js",
    "teacher-dialogs.js",
    "teacher-filenames.js",
    "teacher-format.js",
    "teacher-grades.js",
    "teacher-held.js",
    "teacher-review.js",
    "teacher-screens.js",
    "teacher-state.js",
    "teacher-upload.js",
    "teacher-value.js",
    "teacher-uploading.js",
)

ASSET_MEDIA_TYPES = {
    "teacher.css": "text/css; charset=utf-8",
    **{name: "text/javascript; charset=utf-8" for name in TEACHER_MODULES},
}


class TeacherBatchView(TeacherBatchProgress):
    lot_code: str
    job_id: str
    started_at: TzAwareDatetime | None = None
    decided_by_you: int = Field(default=0, ge=0)
    graded_automatically: int = Field(default=0, ge=0)
    files: list[str] = Field(default_factory=list)


class TeacherSummaryView(TeacherSummary):
    batches: list[TeacherBatchView] = Field(default_factory=list)
    history: list[TeacherReviewView] = Field(default_factory=list)


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@teacher_router.get("/teacher", response_class=FileResponse)
async def teacher_page() -> FileResponse:
    page = STATIC_DIR / TEACHER_PAGE
    if not page.is_file():
        raise _not_found("teacher page is not bundled")
    return FileResponse(
        page,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@teacher_router.get("/teacher/assets/{asset_name}", response_class=FileResponse)
async def teacher_asset(asset_name: str) -> FileResponse:
    media_type = ASSET_MEDIA_TYPES.get(asset_name)
    if media_type is None:
        raise _not_found(f"unknown teacher asset {asset_name!r}")
    path = STATIC_DIR / asset_name
    if not path.is_file():
        raise _not_found(f"teacher asset {asset_name!r} is not bundled")
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )


def lot_code_of(record: JobRecord) -> str | None:
    tail = record.event.exam_batch_prefix.rstrip("/").rsplit("/", 1)[-1]
    return tail if LOT_CODE_PATTERN.fullmatch(tail) else None


async def recent_lot_codes(container: AppContainer, first: str | None) -> list[str]:
    ordered: list[str] = [first] if first else []
    try:
        uploaded = await build_ingest_storage(container.settings).list_lot_codes(
            MAX_RECENT_BATCHES
        )
    except Exception:
        uploaded = []
    for lot_code in uploaded:
        if LOT_CODE_PATTERN.fullmatch(lot_code) and lot_code not in ordered:
            ordered.append(lot_code)
    try:
        records = await list_job_records(container.settings)
    except Exception:
        records = []
    for record in records:
        lot_code = lot_code_of(record)
        if lot_code is not None and lot_code not in ordered:
            ordered.append(lot_code)
        if len(ordered) >= MAX_RECENT_BATCHES:
            break
    return ordered[:MAX_RECENT_BATCHES]


async def batch_view(
    container: AppContainer, lot_code: str, items: list[ReviewItem]
) -> TeacherBatchView | None:
    progress = await build_batch_progress(container, lot_code, items)
    if progress is None:
        return None
    job_id = batch_job_id(lot_code)
    decided, _ = await decided_counts(container, job_id)
    try:
        record = await container.checkpoint_store.get(job_id)
    except Exception:
        record = None
    try:
        files = await build_ingest_storage(container.settings).list_files(lot_code)
    except Exception:
        files = []
    return TeacherBatchView(
        **progress.model_dump(),
        lot_code=lot_code,
        job_id=job_id,
        started_at=record.event.triggered_at if record is not None else None,
        decided_by_you=min(decided, progress.in_gradebook),
        graded_automatically=max(progress.in_gradebook - decided, 0),
        files=files,
    )


def base_progress(view: TeacherBatchView | None) -> TeacherBatchProgress | None:
    if view is None:
        return None
    kept = TeacherBatchProgress.model_fields
    return TeacherBatchProgress(
        **{name: value for name, value in view.model_dump().items() if name in kept}
    )


@teacher_router.get("/teacher/summary", response_model=TeacherSummaryView)
async def teacher_summary(
    request: Request,
    batch: str | None = Query(default=None),
    container: AppContainer = Depends(get_container),
) -> TeacherSummaryView:
    require_push_token(request, container.settings.pubsub_push_token)
    items = await container.review_service.list_pending()
    cache: dict[str, SessionState | None] = {}
    waiting = [await build_review_view(container, item, cache) for item in items]
    views: list[TeacherBatchView] = []
    for lot_code in await recent_lot_codes(container, batch):
        view = await batch_view(container, lot_code, items)
        if view is not None:
            views.append(view)
    named = next((view for view in views if view.lot_code == batch), None)
    history: list[TeacherReviewView] = []
    if batch:
        try:
            recent = await container.review_service.list_recent(limit=500)
        except Exception:
            recent = []
        target_job = batch_job_id(batch)
        history = [
            await build_review_view(container, item, cache)
            for item in recent
            if item.job_id == target_job and item.status.value != "pending"
        ]
    summary = build_summary(waiting, base_progress(named))
    return TeacherSummaryView(
        **summary.model_dump(), batches=views, history=history
    )
