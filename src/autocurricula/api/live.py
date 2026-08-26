import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.job_views import build_summary
from autocurricula.api.live_sources import (
    read_local_live_events,
    read_remote_live_events,
)
from autocurricula.api.trace import cloud_trace_link
from autocurricula.api.webhooks import require_push_token
from autocurricula.core.telemetry.trace_ids import cloud_trace_id
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.live_events import LiveEvent

live_router = APIRouter(tags=["live"])

DEFAULT_EVENT_LIMIT = 500
MAX_EVENT_LIMIT = 1000
SETTLED_STAGES = frozenset({"completed", "failed"})


class LiveFeedResponse(StrictBaseModel):
    job_id: str
    trace_id: str
    cloud_trace_id: str
    cloud_trace_url: str | None = None
    stage: str
    error: str | None = None
    settled: bool = False
    next_after: int = Field(default=0, ge=0)
    count: int = Field(default=0, ge=0)
    events: list[LiveEvent] = Field(default_factory=list)


def parse_live_events(payloads: list[dict[str, Any]]) -> list[LiveEvent]:
    events: list[LiveEvent] = []
    for payload in payloads:
        try:
            events.append(LiveEvent.model_validate(payload))
        except ValueError:
            continue
    return events


@live_router.get("/jobs/{job_id}/live", response_model=LiveFeedResponse)
async def job_live_feed(
    job_id: str,
    request: Request,
    after: int = Query(default=0, ge=0),
    limit: int = Query(default=DEFAULT_EVENT_LIMIT, ge=1, le=MAX_EVENT_LIMIT),
    container: AppContainer = Depends(get_container),
) -> LiveFeedResponse:
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
        if container.settings.local_mode:
            payloads = await asyncio.to_thread(
                read_local_live_events, container.settings, job_id, after, limit
            )
        else:
            payloads = await asyncio.to_thread(
                read_remote_live_events, container.settings, job_id, after, limit
            )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"live feed unavailable: {error}",
        ) from error
    summary = build_summary(record)
    events = parse_live_events(payloads)
    trace_id = record.event.trace_id
    return LiveFeedResponse(
        job_id=record.job_id,
        trace_id=trace_id,
        cloud_trace_id=cloud_trace_id(trace_id),
        cloud_trace_url=cloud_trace_link(container.settings, trace_id),
        stage=summary.stage,
        error=summary.error,
        settled=summary.stage in SETTLED_STAGES,
        next_after=max((event.seq for event in events), default=after),
        count=len(events),
        events=events,
    )
