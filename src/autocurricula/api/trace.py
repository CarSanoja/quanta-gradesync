import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.job_views import JobStageView, build_summary
from autocurricula.api.webhooks import require_push_token
from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.telemetry import TypedSpan

trace_router = APIRouter(tags=["trace"])

AUDIT_DIRECTORY = "audit"
AUDIT_EVENTS_SUBCOLLECTION = "events"
FIELD_RECORDED_AT = "recorded_at"


class TraceEventView(StrictBaseModel):
    recorded_at: str
    stage: str | None = None
    error: str | None = None
    span_count: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class TraceResponse(StrictBaseModel):
    job_id: str
    trace_id: str
    stage: str
    error: str | None = None
    stages: list[JobStageView] = Field(default_factory=list)
    recorded_at: str | None = None
    spans: list[TypedSpan] = Field(default_factory=list)
    metrics: dict[str, Any] | None = None
    events: list[TraceEventView] = Field(default_factory=list)


def read_local_audit_events(settings: Settings, job_id: str) -> list[dict[str, Any]]:
    directory = (Path(settings.local_data_dir) / AUDIT_DIRECTORY).resolve()
    path = (directory / f"{job_id}.jsonl").resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def read_remote_audit_events(
    settings: Settings, job_id: str, client: Any | None = None
) -> list[dict[str, Any]]:
    active = client if client is not None else get_firestore_client()
    if active is None:
        raise RuntimeError("audit trail reads require a configured firestore client")
    snapshots = (
        active.collection(settings.firestore_audit_collection)
        .document(job_id)
        .collection(AUDIT_EVENTS_SUBCOLLECTION)
        .stream()
    )
    events = [
        payload
        for snapshot in snapshots
        if isinstance(payload := snapshot.to_dict(), dict)
    ]
    events.sort(key=lambda event: str(event.get(FIELD_RECORDED_AT) or ""))
    return events


def parse_spans(event: dict[str, Any]) -> list[TypedSpan]:
    spans: list[TypedSpan] = []
    for raw in event.get("spans") or []:
        try:
            spans.append(TypedSpan.model_validate(raw))
        except ValueError:
            continue
    return spans


def event_view(event: dict[str, Any]) -> TraceEventView:
    summary = event.get("summary") or {}
    metrics = summary.get("metrics") or {}
    total_tokens = metrics.get("total_tokens")
    return TraceEventView(
        recorded_at=str(event.get(FIELD_RECORDED_AT) or ""),
        stage=str(summary.get("stage")) if summary.get("stage") else None,
        error=str(summary.get("error")) if summary.get("error") else None,
        span_count=len(event.get("spans") or []),
        total_tokens=total_tokens if isinstance(total_tokens, int) else 0,
    )


@trace_router.get("/jobs/{job_id}/trace", response_model=TraceResponse)
async def job_trace(
    job_id: str,
    request: Request,
    container: AppContainer = Depends(get_container),
) -> TraceResponse:
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
            events = await asyncio.to_thread(
                read_local_audit_events, container.settings, job_id
            )
        else:
            events = await asyncio.to_thread(
                read_remote_audit_events, container.settings, job_id
            )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"audit trail unavailable: {error}",
        ) from error
    summary = build_summary(record)
    latest = events[-1] if events else None
    metrics = (latest.get("summary") or {}).get("metrics") if latest else None
    return TraceResponse(
        job_id=record.job_id,
        trace_id=record.event.trace_id,
        stage=summary.stage,
        error=summary.error,
        stages=summary.stages,
        recorded_at=str(latest.get(FIELD_RECORDED_AT)) if latest else None,
        spans=parse_spans(latest) if latest else [],
        metrics=metrics if isinstance(metrics, dict) else None,
        events=[event_view(event) for event in events],
    )
