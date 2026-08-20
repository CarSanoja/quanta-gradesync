import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.gcs_notification import PushResolution, resolve_push_event
from autocurricula.api.push_auth import require_push_token
from autocurricula.api.responses import WebhookResult
from autocurricula.core.orchestration.batch_settle import BatchSettler
from autocurricula.core.orchestration.job_state import (
    CheckpointStore,
    JobRecord,
    JobStage,
)
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.events import PubSubJobEvent

logger = logging.getLogger(__name__)

pubsub_router = APIRouter(tags=["webhooks"])

STATUS_COMPLETED = "completed"
STATUS_DUPLICATE = "duplicate"
STATUS_IGNORED = "ignored"


async def run_job_and_checkpoint(
    runner: JobRunner,
    store: CheckpointStore,
    event: PubSubJobEvent,
    settler: BatchSettler | None = None,
) -> JobRecord:
    if settler is not None:
        await settler.wait(event)
    record = await runner.process(event)
    try:
        await store.save(record)
    except Exception as error:
        logger.warning(
            "post-completion checkpoint failed for job %s: %s", event.job_id, error
        )
    return record


async def read_push_body(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pubsub push body is not valid json",
        ) from error
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="pubsub push body must be a json object",
        )
    return body


def resolve_or_reject(body: dict) -> PushResolution:
    try:
        return resolve_push_event(body)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid pubsub push envelope: {error}",
        ) from error


def is_resumable(record: JobRecord, stale_after_seconds: float) -> bool:
    if record.stage == JobStage.FAILED:
        return True
    if record.stage == JobStage.COMPLETED:
        return False
    age = (utc_now() - record.updated_at).total_seconds()
    return age >= stale_after_seconds


async def already_processed(container: AppContainer, job_id: str) -> bool:
    try:
        existing = await container.checkpoint_store.get(job_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="checkpoint store unavailable during idempotency check",
        ) from error
    if existing is None:
        return False
    if is_resumable(existing, container.settings.resume_stale_after_seconds):
        logger.warning(
            "job %s checkpoint at stage %s is stale or failed; accepting redelivery",
            job_id,
            existing.stage.value,
        )
        return False
    return True


def claim_job(container: AppContainer, job_id: str) -> bool:
    if job_id in container.claimed_jobs:
        return False
    container.claimed_jobs.add(job_id)
    return True


async def accept_job(container: AppContainer, job_id: str) -> bool:
    if not claim_job(container, job_id):
        return False
    try:
        seen = await already_processed(container, job_id)
    except Exception:
        container.claimed_jobs.discard(job_id)
        raise
    if seen:
        container.claimed_jobs.discard(job_id)
        return False
    return True


def start_job(
    container: AppContainer, event: PubSubJobEvent, settler: BatchSettler | None
) -> asyncio.Task[JobRecord]:
    try:
        task = asyncio.create_task(
            run_job_and_checkpoint(
                container.job_runner, container.checkpoint_store, event, settler
            )
        )
    except Exception as error:
        container.claimed_jobs.discard(event.job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to start job processing",
        ) from error
    container.in_flight.add(task)
    task.add_done_callback(container.in_flight.discard)
    task.add_done_callback(lambda _: container.claimed_jobs.discard(event.job_id))
    return task


async def await_job_outcome(
    task: asyncio.Task[JobRecord], job_id: str
) -> JobRecord:
    try:
        record = await task
    except Exception as error:
        logger.exception(
            "job %s raised before completion; delivery left unacknowledged", job_id
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"job {job_id} processing raised; delivery will be retried",
        ) from error
    if record.stage == JobStage.FAILED:
        logger.error(
            "job %s failed mid-pipeline (%s); delivery left unacknowledged",
            job_id,
            record.error,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"job {job_id} failed and will resume from its checkpoint on retry",
        )
    return record


@pubsub_router.post(
    "/webhooks/pubsub",
    response_model=WebhookResult,
    response_model_exclude_none=True,
)
async def receive_pubsub_push(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> WebhookResult:
    require_push_token(request, container.settings.pubsub_push_token)
    resolution = resolve_or_reject(await read_push_body(request))
    if resolution.event is None:
        logger.info("pubsub push ignored: %s", resolution.ignored_reason)
        return WebhookResult(
            job_id="", status=STATUS_IGNORED, reason=resolution.ignored_reason
        )
    event = resolution.event
    if not await accept_job(container, event.job_id):
        return WebhookResult(job_id=event.job_id, status=STATUS_DUPLICATE)
    settler = container.batch_settler if resolution.from_notification else None
    record = await await_job_outcome(
        start_job(container, event, settler), event.job_id
    )
    return WebhookResult(
        job_id=event.job_id, status=STATUS_COMPLETED, stage=record.stage.value
    )
