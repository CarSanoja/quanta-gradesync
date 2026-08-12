import asyncio
from typing import Any

import httpx

from autocurricula.api.dependencies import AppContainer
from autocurricula.core.orchestration.job_state import JobRecord, JobStage


class UnavailableCheckpointStore:
    async def save(self, record: JobRecord) -> None:
        raise RuntimeError("checkpoint write failed")

    async def get(self, job_id: str) -> JobRecord | None:
        raise RuntimeError("checkpoint read failed")

    async def save_state(self, job_id: str, state: Any) -> None:
        raise RuntimeError("checkpoint state write failed")

    async def load_state(self, job_id: str) -> Any:
        raise RuntimeError("checkpoint state read failed")


async def test_push_without_authorization_is_unauthorized(
    client: httpx.AsyncClient, make_event, make_push_body
) -> None:
    response = await client.post("/webhooks/pubsub", json=make_push_body(make_event()))
    assert response.status_code == 401


async def test_push_with_non_bearer_scheme_is_unauthorized(
    client: httpx.AsyncClient, make_event, make_push_body
) -> None:
    headers = {"Authorization": "Token some-token"}
    response = await client.post(
        "/webhooks/pubsub", json=make_push_body(make_event()), headers=headers
    )
    assert response.status_code == 401


async def test_push_with_wrong_token_is_forbidden(
    client: httpx.AsyncClient, make_event, make_push_body
) -> None:
    headers = {"Authorization": "Bearer not-the-configured-token"}
    response = await client.post(
        "/webhooks/pubsub", json=make_push_body(make_event()), headers=headers
    )
    assert response.status_code == 403


async def test_push_with_blank_configured_token_is_forbidden(
    client: httpx.AsyncClient, container: AppContainer, make_event, make_push_body
) -> None:
    container.settings = container.settings.model_copy(
        update={"pubsub_push_token": ""}
    )
    headers = {"Authorization": "Bearer anything"}
    response = await client.post(
        "/webhooks/pubsub", json=make_push_body(make_event()), headers=headers
    )
    assert response.status_code == 403


async def test_push_with_invalid_envelope_returns_400(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.post(
        "/webhooks/pubsub", json={"unexpected": True}, headers=auth_headers
    )
    assert response.status_code == 400


async def test_push_with_invalid_base64_returns_400(
    client: httpx.AsyncClient, auth_headers
) -> None:
    body = {
        "message": {"messageId": "message-001", "data": "!!not-base64!!"},
        "subscription": "projects/test-project/subscriptions/exam-push",
    }
    response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert response.status_code == 400


async def test_push_with_non_object_body_returns_400(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.post(
        "/webhooks/pubsub", content="[1, 2]", headers=auth_headers
    )
    assert response.status_code == 400


async def test_push_for_completed_job_is_idempotent(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_event,
    make_push_body,
) -> None:
    event = make_event()
    await container.checkpoint_store.save(
        JobRecord(job_id=event.job_id, event=event, stage=JobStage.COMPLETED)
    )
    response = await client.post(
        "/webhooks/pubsub", json=make_push_body(event), headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {"job_id": event.job_id, "status": "duplicate"}
    assert scripted_runner.events == []


async def test_push_accepts_new_job_and_runs_pipeline(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_event,
    make_push_body,
) -> None:
    event = make_event()
    response = await client.post(
        "/webhooks/pubsub", json=make_push_body(event), headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json() == {"job_id": event.job_id, "status": "accepted"}
    await asyncio.gather(*container.in_flight)
    assert [item.job_id for item in scripted_runner.events] == [event.job_id]
    stored = await container.checkpoint_store.get(event.job_id)
    assert stored is not None
    assert stored.stage == JobStage.COMPLETED


async def test_push_returns_500_when_checkpoint_store_is_unavailable(
    client: httpx.AsyncClient,
    container: AppContainer,
    auth_headers,
    make_event,
    make_push_body,
) -> None:
    container.checkpoint_store = UnavailableCheckpointStore()
    response = await client.post(
        "/webhooks/pubsub", json=make_push_body(make_event()), headers=auth_headers
    )
    assert response.status_code == 500
