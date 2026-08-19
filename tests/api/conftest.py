import base64
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from autocurricula.api.dependencies import AppContainer, build_container, set_container
from autocurricula.api.main import create_app
from autocurricula.config.settings import Settings
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.events import PubSubJobEvent

PUSH_TOKEN = "unit-test-push-token"


class ScriptedRunner:
    def __init__(self) -> None:
        self.events: list[PubSubJobEvent] = []

    async def process(self, event: PubSubJobEvent) -> JobRecord:
        self.events.append(event)
        return JobRecord(job_id=event.job_id, event=event, stage=JobStage.COMPLETED)


@pytest.fixture
def push_token() -> str:
    return PUSH_TOKEN


@pytest.fixture
def auth_headers(push_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {push_token}"}


@pytest.fixture
def make_event():
    def _make(job_id: str = "job-001") -> PubSubJobEvent:
        return PubSubJobEvent(
            job_id=job_id,
            bucket="exam-uploads",
            exam_batch_prefix="batches/2026-08",
            class_id="class-7b",
            subject="mathematics",
            triggered_at=utc_now(),
        )

    return _make


@pytest.fixture
def make_push_body():
    def _make(event: PubSubJobEvent) -> dict[str, Any]:
        payload = json.dumps(event.model_dump(mode="json"))
        encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
        return {
            "message": {"messageId": "message-001", "data": encoded, "attributes": {}},
            "subscription": "projects/test-project/subscriptions/exam-push",
        }

    return _make


@pytest.fixture
def make_notification_body():
    def _make(
        object_name: str,
        bucket: str = "quanta-gradesync-exams",
        event_type: str = "OBJECT_FINALIZE",
        message_id: str = "gcs-message-001",
        with_data: bool = True,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "messageId": message_id,
            "publishTime": "2026-08-19T22:29:58.000Z",
            "attributes": {
                "bucketId": bucket,
                "eventType": event_type,
                "objectId": object_name,
                "payloadFormat": "JSON_API_V1",
                "notificationConfig": "projects/_/buckets/exams/notificationConfigs/1",
            },
        }
        if with_data:
            resource = {
                "kind": "storage#object",
                "bucket": bucket,
                "name": object_name,
                "contentType": "image/jpeg",
                "size": "54242",
            }
            message["data"] = base64.b64encode(
                json.dumps(resource).encode("utf-8")
            ).decode("ascii")
        return {
            "message": message,
            "subscription": (
                "projects/quanta-gradesync/subscriptions/exam-batch-ingest-push"
            ),
        }

    return _make


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    return Settings(
        local_mode=True,
        gcp_project_id="",
        pubsub_push_token=PUSH_TOKEN,
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
        batch_settle_interval_seconds=0.0,
    )


@pytest.fixture
def scripted_runner() -> ScriptedRunner:
    return ScriptedRunner()


@pytest.fixture
def container(api_settings: Settings, scripted_runner: ScriptedRunner) -> AppContainer:
    built = build_container(api_settings)
    built.job_runner = scripted_runner
    return built


@pytest.fixture
def app(container: AppContainer) -> FastAPI:
    application = create_app()
    set_container(application, container)
    return application


@pytest.fixture
async def client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gradesync.test"
    ) as active:
        yield active
