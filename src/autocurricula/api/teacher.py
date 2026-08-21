from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.teacher_batch import build_batch_progress
from autocurricula.api.teacher_triage import TeacherSummary, build_summary
from autocurricula.api.teacher_views import build_review_view
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.memory.session_memory import SessionState

teacher_router = APIRouter(tags=["teacher"])

STATIC_DIR = Path(__file__).parent / "static"
TEACHER_PAGE = "teacher.html"

ASSET_MEDIA_TYPES = {
    "teacher.css": "text/css; charset=utf-8",
    "teacher.js": "text/javascript; charset=utf-8",
    "teacher-upload.js": "text/javascript; charset=utf-8",
    "teacher-triage.js": "text/javascript; charset=utf-8",
    "teacher-detail.js": "text/javascript; charset=utf-8",
}


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
    cache: dict[str, SessionState | None] = {}
    waiting = [await build_review_view(container, item, cache) for item in items]
    progress = await build_batch_progress(container, batch, items) if batch else None
    return build_summary(waiting, progress)
