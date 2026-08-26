from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from autocurricula.api.dependencies import AppContainer, set_container
from autocurricula.api.live import live_router
from autocurricula.api.live_sources import LIVE_DIRECTORY, read_local_live_events
from autocurricula.api.main import create_app
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.live_events import (
    LiveEvent,
    LiveEventKind,
    LiveEventStatus,
    LlmExchange,
)

JOB_ID = "job-live-1"
TRACE_ID = "9c41e77b20f5a3d6"
SUBJECT = "matematicas"
BUCKET = "exam-uploads"
PREFIX = "batches/2026_Matematicas_10A_Parcial1"
TRIGGERED_AT = datetime(2026, 8, 19, 22, 30, tzinfo=UTC)
LIVE_PATH = "/jobs/{job_id}/live"


@pytest.fixture
def app(container: AppContainer) -> FastAPI:
    application = create_app()
    if not any(getattr(route, "path", "") == LIVE_PATH for route in application.routes):
        application.include_router(live_router)
    set_container(application, container)
    return application


def make_record(job_id: str, stage: JobStage = JobStage.GRADED) -> JobRecord:
    event = PubSubJobEvent(
        job_id=job_id,
        bucket=BUCKET,
        exam_batch_prefix=PREFIX,
        class_id="10A",
        subject=SUBJECT,
        triggered_at=TRIGGERED_AT,
        trace_id=TRACE_ID,
    )
    return JobRecord(
        job_id=job_id,
        event=event,
        stage=stage,
        stage_statuses={"fetch": "succeeded", "grade": "running"},
    )


def make_live_event(job_id: str, seq: int) -> LiveEvent:
    return LiveEvent(
        seq=seq,
        recorded_at=f"2026-08-19T22:30:{40 + seq:02d}+00:00",
        job_id=job_id,
        trace_id=TRACE_ID,
        kind=LiveEventKind.LLM_CALL,
        name=f"Grading_ana-torres-{seq}",
        status=LiveEventStatus.OK,
        stage="grade",
        agent_id="grading-agent",
        principal="grader@gradesync.test",
        student_id="ana-torres",
        span_id=f"s{seq}",
        parent_span_id="s0",
        duration_ms=float(120 + seq),
        attributes={"gen_ai.model": "gemini-3.5-flash", "armor.injection_detected": False},
        llm=LlmExchange(
            model="gemini-3.5-flash",
            request_excerpt="Score criterion crit-a against the rubric.",
            response_excerpt="crit-a scored 2.0 of 4.0 with page-1 evidence.",
            finish_reason="STOP",
            input_tokens=400,
            output_tokens=112,
            total_tokens=512,
        ),
    )


def seed_live_events(container: AppContainer, job_id: str, count: int = 5) -> Path:
    directory = Path(container.settings.local_data_dir) / LIVE_DIRECTORY
    directory.mkdir(parents=True, exist_ok=True)
    lines = [make_live_event(job_id, seq).model_dump_json() for seq in range(1, count + 1)]
    lines.insert(2, '{"seq": 3, "kind": "span_start"')
    path = directory / f"{job_id}.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
async def live_job(container: AppContainer) -> str:
    await container.checkpoint_store.save(make_record(JOB_ID))
    seed_live_events(container, JOB_ID)
    return JOB_ID


async def test_live_feed_requires_the_push_token(
    client: httpx.AsyncClient, live_job: str
) -> None:
    missing = await client.get(f"/jobs/{live_job}/live")
    assert missing.status_code == 401
    wrong = await client.get(
        f"/jobs/{live_job}/live", headers={"Authorization": "Bearer nope"}
    )
    assert wrong.status_code == 403


async def test_live_feed_returns_404_for_unknown_jobs(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get("/jobs/job-ghost/live", headers=auth_headers)
    assert response.status_code == 404


async def test_live_feed_streams_every_parsable_event(
    client: httpx.AsyncClient, auth_headers, live_job: str
) -> None:
    response = await client.get(f"/jobs/{live_job}/live", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == live_job
    assert payload["trace_id"] == TRACE_ID
    assert payload["count"] == 5
    assert [event["seq"] for event in payload["events"]] == [1, 2, 3, 4, 5]
    assert payload["next_after"] == 5
    assert len(payload["cloud_trace_id"]) == 32
    assert payload["cloud_trace_url"] is None
    first = payload["events"][0]
    assert first["kind"] == "llm_call"
    assert first["agent_id"] == "grading-agent"
    assert first["attributes"]["armor.injection_detected"] is False
    assert first["llm"]["total_tokens"] == 512


async def test_live_feed_paginates_from_the_after_cursor(
    client: httpx.AsyncClient, auth_headers, live_job: str
) -> None:
    response = await client.get(
        f"/jobs/{live_job}/live", params={"after": 2}, headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert [event["seq"] for event in payload["events"]] == [3, 4, 5]
    assert payload["count"] == 3
    assert payload["next_after"] == 5
    rejected = await client.get(
        f"/jobs/{live_job}/live", params={"after": -1}, headers=auth_headers
    )
    assert rejected.status_code == 422


async def test_live_feed_caps_the_page_at_the_limit(
    client: httpx.AsyncClient, auth_headers, live_job: str
) -> None:
    response = await client.get(
        f"/jobs/{live_job}/live", params={"limit": 2}, headers=auth_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert [event["seq"] for event in payload["events"]] == [1, 2]
    assert payload["next_after"] == 2
    drained = await client.get(
        f"/jobs/{live_job}/live", params={"after": 5}, headers=auth_headers
    )
    exhausted = drained.json()
    assert exhausted["events"] == []
    assert exhausted["count"] == 0
    assert exhausted["next_after"] == 5


async def test_live_feed_reports_the_settled_stage(
    client: httpx.AsyncClient, container: AppContainer, auth_headers, live_job: str
) -> None:
    running = await client.get(f"/jobs/{live_job}/live", headers=auth_headers)
    assert running.json()["settled"] is False
    await container.checkpoint_store.save(make_record(live_job, JobStage.COMPLETED))
    settled = await client.get(f"/jobs/{live_job}/live", headers=auth_headers)
    payload = settled.json()
    assert payload["stage"] == "completed"
    assert payload["settled"] is True


async def test_live_feed_serves_an_empty_page_before_any_event(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.checkpoint_store.save(make_record("job-live-quiet"))
    response = await client.get("/jobs/job-live-quiet/live", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["events"] == []
    assert payload["count"] == 0
    assert payload["next_after"] == 0


def test_local_reader_refuses_paths_outside_the_live_directory(
    container: AppContainer,
) -> None:
    seed_live_events(container, JOB_ID)
    escaped = read_local_live_events(
        container.settings, "../audit/" + JOB_ID, 0, 500
    )
    assert escaped == []
