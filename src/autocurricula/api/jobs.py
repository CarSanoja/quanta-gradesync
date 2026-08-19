from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.job_index import list_job_records
from autocurricula.api.job_views import (
    SIS_STATUS_QUARANTINED,
    JobDetail,
    JobSummary,
    apply_review_decisions,
    build_detail,
    build_summary,
)
from autocurricula.api.webhooks import require_push_token
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.review import ReviewStatus

jobs_router = APIRouter(tags=["jobs"])

DEFAULT_JOB_LIMIT = 50


class JobsResponse(StrictBaseModel):
    items: list[JobSummary] = Field(default_factory=list)
    count: int = Field(ge=0)


@jobs_router.get("/jobs", response_model=JobsResponse)
async def list_jobs(
    request: Request,
    limit: int = Query(default=DEFAULT_JOB_LIMIT, ge=1, le=200),
    container: AppContainer = Depends(get_container),
) -> JobsResponse:
    require_push_token(request, container.settings.pubsub_push_token)
    try:
        records = await list_job_records(container.settings)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"job registry unavailable: {error}",
        ) from error
    items = [build_summary(record) for record in records[:limit]]
    return JobsResponse(items=items, count=len(items))


@jobs_router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: str,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> JobDetail:
    require_push_token(request, container.settings.pubsub_push_token)
    try:
        record = await container.checkpoint_store.get(job_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"checkpoint store unavailable: {error}",
        ) from error
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"no job {job_id!r}"
        )
    try:
        state = await container.checkpoint_store.load_state(job_id)
    except Exception:
        state = None
    detail = build_detail(record, state)
    return apply_review_decisions(detail, await review_decisions(container, detail))


async def review_decisions(container: AppContainer, detail: JobDetail) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for student in detail.students:
        if student.sis_status != SIS_STATUS_QUARANTINED:
            continue
        try:
            item = await container.review_service.store.get(student.review_id)
        except Exception:
            continue
        if item is not None and item.status != ReviewStatus.PENDING:
            decisions[student.review_id] = item.status.value
    return decisions
