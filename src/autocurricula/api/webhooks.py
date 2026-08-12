import asyncio
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.responses import WebhookAccepted
from autocurricula.core.orchestration.job_state import CheckpointStore, JobRecord
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.schemas.events import PubSubJobEvent, parse_push_body

logger = logging.getLogger(__name__)

pubsub_router = APIRouter(tags=["webhooks"])

BEARER_SCHEME = "bearer"
STATUS_ACCEPTED = "accepted"
STATUS_DUPLICATE = "duplicate"


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
    runner: JobRunner, store: CheckpointStore, event: PubSubJobEvent
) -> JobRecord:
    record = await runner.process(event)
    try:
        await store.save(record)
    except Exception as error:
        logger.warning(
            "post-completion checkpoint failed for job %s: %s", event.job_id, error
        )
    return record


@pubsub_router.post("/webhooks/pubsub", response_model=WebhookAccepted)
async def receive_pubsub_push(
    request: Request,
    container: AppContainer = Depends(get_container),
) -> WebhookAccepted:
    require_push_token(request, container.settings.pubsub_push_token)
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
    try:
        event = parse_push_body(body)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid pubsub push envelope: {error}",
        ) from error
    try:
        existing = await container.checkpoint_store.get(event.job_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="checkpoint store unavailable during idempotency check",
        ) from error
    if existing is not None:
        return WebhookAccepted(job_id=event.job_id, status=STATUS_DUPLICATE)
    try:
        task = asyncio.create_task(
            run_job_and_checkpoint(
                container.job_runner, container.checkpoint_store, event
            )
        )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to enqueue job processing",
        ) from error
    container.in_flight.add(task)
    task.add_done_callback(container.in_flight.discard)
    return WebhookAccepted(job_id=event.job_id, status=STATUS_ACCEPTED)
