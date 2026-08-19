import asyncio
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.gcs_notification import PushResolution, resolve_push_event
from autocurricula.api.responses import WebhookAccepted
from autocurricula.core.orchestration.batch_settle import BatchSettler
from autocurricula.core.orchestration.job_state import CheckpointStore, JobRecord
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.schemas.events import PubSubJobEvent

logger = logging.getLogger(__name__)

pubsub_router = APIRouter(tags=["webhooks"])

BEARER_SCHEME = "bearer"
STATUS_ACCEPTED = "accepted"
STATUS_DUPLICATE = "duplicate"
STATUS_IGNORED = "ignored"


def extract_bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != BEARER_SCHEME:
        return None
    return token.strip()


def require_push_token(request: Request, expected: str) -> None:
    provided = extract_bearer_token(request)
    if provided is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or malformed bearer authorization header",
        )
    if not expected or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="pubsub push verification token rejected",
        )


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


async def already_processed(container: AppContainer, job_id: str) -> bool:
    try:
        existing = await container.checkpoint_store.get(job_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="checkpoint store unavailable during idempotency check",
        ) from error
    return existing is not None


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
) -> None:
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
            detail="failed to enqueue job processing",
        ) from error
    container.in_flight.add(task)
    task.add_done_callback(container.in_flight.discard)
    task.add_done_callback(lambda _: container.claimed_jobs.discard(event.job_id))


@pubsub_router.post(
    "/webhooks/pubsub",
    response_model=WebhookAccepted,
    response_model_exclude_none=True,
)
async def receive_pubsub_push(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> WebhookAccepted:
    require_push_token(request, container.settings.pubsub_push_token)
    resolution = resolve_or_reject(await read_push_body(request))
    if resolution.event is None:
        logger.info("pubsub push ignored: %s", resolution.ignored_reason)
        return WebhookAccepted(
            job_id="", status=STATUS_IGNORED, reason=resolution.ignored_reason
        )
    event = resolution.event
    if not await accept_job(container, event.job_id):
        return WebhookAccepted(job_id=event.job_id, status=STATUS_DUPLICATE)
    settler = container.batch_settler if resolution.from_notification else None
    start_job(container, event, settler)
    return WebhookAccepted(job_id=event.job_id, status=STATUS_ACCEPTED)
