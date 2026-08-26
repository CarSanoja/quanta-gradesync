from datetime import UTC, datetime

import httpx
import pytest

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.trace import cloud_trace_link
from autocurricula.config.settings import Settings
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.core.telemetry.trace_ids import cloud_trace_id
from autocurricula.schemas.events import PubSubJobEvent

JOB_ID = "job-trace-link"
SHORT_TRACE_ID = "9c41e77b20f5a3d6"
CLOUD_TRACE_ID = "4e2f1b6ad3c04f5b8a9d7e6c5b4a3928"
PROJECT_ID = "quanta-gradesync"


def make_record(job_id: str, trace_id: str) -> JobRecord:
    event = PubSubJobEvent(
        job_id=job_id,
        bucket="exam-uploads",
        exam_batch_prefix="batches/2026_Matematicas_10A_Parcial1",
        class_id="10A",
        subject="matematicas",
        triggered_at=datetime(2026, 8, 19, 22, 30, tzinfo=UTC),
        trace_id=trace_id,
    )
    return JobRecord(job_id=job_id, event=event, stage=JobStage.GRADED)


@pytest.fixture
async def traced_job(container: AppContainer) -> str:
    await container.checkpoint_store.save(make_record(JOB_ID, SHORT_TRACE_ID))
    return JOB_ID


async def test_trace_response_carries_no_cloud_link_in_local_mode(
    client: httpx.AsyncClient, auth_headers, traced_job: str
) -> None:
    response = await client.get(f"/jobs/{traced_job}/trace", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["trace_id"] == SHORT_TRACE_ID
    assert payload["cloud_trace_id"] == cloud_trace_id(SHORT_TRACE_ID)
    assert len(payload["cloud_trace_id"]) == 32
    assert payload["cloud_trace_url"] is None


async def test_trace_response_passes_through_a_native_cloud_trace_id(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.checkpoint_store.save(make_record("job-native", CLOUD_TRACE_ID))
    response = await client.get("/jobs/job-native/trace", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["cloud_trace_id"] == CLOUD_TRACE_ID


def test_cloud_trace_link_is_empty_without_a_project(api_settings: Settings) -> None:
    assert cloud_trace_link(api_settings, SHORT_TRACE_ID) is None


def test_cloud_trace_link_points_at_the_explorer_on_gcp() -> None:
    settings = Settings(
        local_mode=False,
        gcp_project_id=PROJECT_ID,
        pubsub_push_token="deployed-token",
    )
    link = cloud_trace_link(settings, SHORT_TRACE_ID)
    assert link is not None
    assert PROJECT_ID in link
    assert cloud_trace_id(SHORT_TRACE_ID) in link
