import asyncio
from pathlib import Path

import httpx
import pytest

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.gcs_notification import derive_job_id, resolve_push_event
from autocurricula.core.orchestration.manifest_inference import LocalManifestInferer
from autocurricula.schemas.events import PubSubJobEvent
from tests.orchestration.inference_fixtures import (
    BUCKET,
    PREFIX,
    write_batch_files,
    write_defaults,
)

E2E_PREFIX = "e2e/2026-08-19/batches/2026_Matematicas_10A_Parcial1"
E2E_OBJECT = f"{E2E_PREFIX}/ana-torres.jpg"
E2E_JOB_ID = "e2e-2026-08-19-2026-matematicas-10a-parcial1"


class RecordingSettler:
    def __init__(self) -> None:
        self.events: list[PubSubJobEvent] = []

    async def wait(self, event: PubSubJobEvent) -> int:
        self.events.append(event)
        return 0


def test_derive_job_id_is_deterministic_and_slugged() -> None:
    assert derive_job_id(E2E_PREFIX) == E2E_JOB_ID
    assert derive_job_id(PREFIX) == "2026-matematicas-10a-parcial1"
    assert derive_job_id(E2E_PREFIX) == derive_job_id(f"{E2E_PREFIX}/")


async def test_raw_notification_is_translated_into_a_job(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    response = await client.post(
        "/webhooks/pubsub",
        json=make_notification_body(E2E_OBJECT),
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json() == {"job_id": E2E_JOB_ID, "status": "accepted"}
    await asyncio.gather(*container.in_flight)
    assert len(scripted_runner.events) == 1
    event = scripted_runner.events[0]
    assert event.job_id == E2E_JOB_ID
    assert event.bucket == "quanta-gradesync-exams"
    assert event.exam_batch_prefix == E2E_PREFIX
    assert event.subject == "Matematicas"
    assert event.class_id == "10A"


async def test_notification_without_data_uses_attributes(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    body = make_notification_body(E2E_OBJECT, with_data=False)
    response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    await asyncio.gather(*container.in_flight)
    assert scripted_runner.events[0].exam_batch_prefix == E2E_PREFIX


async def test_envelope_with_unknown_fields_is_accepted(
    client: httpx.AsyncClient,
    container: AppContainer,
    auth_headers,
    make_notification_body,
) -> None:
    body = make_notification_body(E2E_OBJECT)
    body["deliveryAttempt"] = 2
    body["message"]["orderingKey"] = "exam-batch"
    response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    await asyncio.gather(*container.in_flight)


@pytest.mark.parametrize(
    "object_name",
    [
        "catalog-defaults.json",
        "e2e/2026-08-19/notes.txt",
        f"{E2E_PREFIX}/notes.txt",
        f"{E2E_PREFIX}/",
        "e2e/batches/2026_Matematicas_10A/ana-torres.jpg",
        f"{E2E_PREFIX}/pages/ana-torres.jpg",
        E2E_PREFIX,
    ],
)
async def test_irrelevant_objects_are_ignored_without_a_job(
    object_name: str,
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    response = await client.post(
        "/webhooks/pubsub",
        json=make_notification_body(object_name),
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ignored"
    assert body["job_id"] == ""
    assert body["reason"]
    assert scripted_runner.events == []
    assert container.in_flight == set()


async def test_non_finalize_event_type_is_ignored(
    client: httpx.AsyncClient,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    body = make_notification_body(E2E_OBJECT, event_type="OBJECT_DELETE")
    response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert scripted_runner.events == []


async def test_batch_manifest_object_creates_a_job(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    body = make_notification_body(f"{E2E_PREFIX}/batch.json")
    response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    await asyncio.gather(*container.in_flight)
    assert [event.job_id for event in scripted_runner.events] == [E2E_JOB_ID]


async def test_per_object_fan_in_runs_the_batch_once(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    students = [
        "ana-torres",
        "camila-rios",
        "diego-castro",
        "julian-pardo",
        "luis-gomez",
        "mariana-ruiz",
        "sofia-morales",
        "tomas-vega",
    ]
    statuses = []
    for index, student in enumerate(students):
        body = make_notification_body(
            f"{E2E_PREFIX}/{student}.jpg", message_id=f"gcs-message-{index}"
        )
        response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
        assert response.status_code == 200
        statuses.append(response.json()["status"])
        await asyncio.gather(*container.in_flight)
    assert statuses[0] == "accepted"
    assert set(statuses[1:]) == {"duplicate"}
    assert [event.job_id for event in scripted_runner.events] == [E2E_JOB_ID]


async def test_concurrent_notifications_start_the_job_once(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    container.batch_settler = RecordingSettler()
    bodies = [
        make_notification_body(
            f"{E2E_PREFIX}/student-{index}.jpg", message_id=f"gcs-message-{index}"
        )
        for index in range(8)
    ]
    responses = await asyncio.gather(
        *(
            client.post("/webhooks/pubsub", json=body, headers=auth_headers)
            for body in bodies
        )
    )
    statuses = [response.json()["status"] for response in responses]
    assert statuses.count("accepted") == 1
    assert statuses.count("duplicate") == 7
    await asyncio.gather(*container.in_flight)
    assert [event.job_id for event in scripted_runner.events] == [E2E_JOB_ID]


async def test_notification_job_waits_for_upload_quiescence(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_notification_body,
) -> None:
    settler = RecordingSettler()
    container.batch_settler = settler
    response = await client.post(
        "/webhooks/pubsub",
        json=make_notification_body(E2E_OBJECT),
        headers=auth_headers,
    )
    assert response.status_code == 200
    await asyncio.gather(*container.in_flight)
    assert [event.job_id for event in settler.events] == [E2E_JOB_ID]
    assert [event.job_id for event in scripted_runner.events] == [E2E_JOB_ID]


async def test_legacy_job_event_bypasses_translation_and_settling(
    client: httpx.AsyncClient,
    container: AppContainer,
    scripted_runner,
    auth_headers,
    make_event,
    make_push_body,
) -> None:
    settler = RecordingSettler()
    container.batch_settler = settler
    event = make_event(job_id="sample-2026-matematicas-10a-parcial1")
    body = make_push_body(event)
    body["message"]["attributes"] = {
        "bucketId": event.bucket,
        "eventType": "OBJECT_FINALIZE",
        "objectId": f"{event.exam_batch_prefix}/2026-08.manifest",
    }
    response = await client.post("/webhooks/pubsub", json=body, headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"job_id": event.job_id, "status": "accepted"}
    await asyncio.gather(*container.in_flight)
    assert [item.job_id for item in scripted_runner.events] == [event.job_id]
    assert settler.events == []


async def test_translated_event_satisfies_manifest_inference(
    tmp_path: Path, make_notification_body
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    write_defaults(staging, ["matematicas"])
    write_batch_files(staging, ("ana-torres.jpg", "luis-gomez.pdf", "notes.txt"))
    body = make_notification_body(f"{PREFIX}/ana-torres.jpg", bucket=BUCKET)
    resolution = resolve_push_event(body)
    assert resolution.from_notification is True
    assert resolution.event is not None
    manifest = await LocalManifestInferer(staging).infer_manifest(resolution.event)
    assert [item.student_id for item in manifest.batch.submissions] == [
        "ana-torres",
        "luis-gomez",
    ]
    assert manifest.batch.job_id == "2026-matematicas-10a-parcial1"
