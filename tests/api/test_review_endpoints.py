import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from autocurricula.api.dependencies import AppContainer
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.review import ReviewItem
from autocurricula.schemas.sis_sync import SISGradeRecord

SUBJECT = "matematicas"
GRADED_AT = datetime(2026, 8, 17, 11, 0, tzinfo=UTC)


def make_item(review_id: str, student_id: str, job_id: str) -> ReviewItem:
    return ReviewItem(
        review_id=review_id,
        job_id=job_id,
        student_id=student_id,
        subject=SUBJECT,
        reasons=["crit-a confidence 0.620 below threshold 0.85"],
        document_paths=[f"gs://exams/batches/x/{student_id}.jpg"],
        proposed_record=SISGradeRecord(
            student_id=student_id,
            subject=SUBJECT,
            score=2.0,
            percentage=50.0,
            feedback="quarantined feedback",
            competency_codes=["MAT.8.1"],
            graded_at=GRADED_AT,
        ),
        created_at=utc_now(),
    )


def sis_students(container: AppContainer) -> set[str]:
    path = Path(container.settings.local_data_dir) / "sis_writes.jsonl"
    if not path.is_file():
        return set()
    students: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        for record in event["request"]["records"]:
            students.add(record["student_id"])
    return students


async def test_pending_requires_authorization(client: httpx.AsyncClient) -> None:
    response = await client.get("/review/pending")
    assert response.status_code == 401


async def test_pending_rejects_wrong_token(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/review/pending", headers={"Authorization": "Bearer nope"}
    )
    assert response.status_code == 403


async def test_pending_starts_empty(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get("/review/pending", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


async def test_pending_lists_quarantined_items(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-1:stu-9", "stu-9", "job-1")
    )
    response = await client.get("/review/pending", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["items"][0]["review_id"] == "job-1:stu-9"
    assert payload["items"][0]["status"] == "pending"


async def test_approve_unknown_review_returns_404(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.post("/review/job-1:ghost/approve", headers=auth_headers)
    assert response.status_code == 404


async def test_approve_writes_to_sis_with_one_click(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-2:stu-1", "stu-1", "job-2")
    )
    response = await client.post("/review/job-2:stu-1/approve", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert "stu-1" in sis_students(container)
    pending = await client.get("/review/pending", headers=auth_headers)
    assert pending.json()["count"] == 0


async def test_double_approve_returns_409(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-3:stu-1", "stu-1", "job-3")
    )
    first = await client.post("/review/job-3:stu-1/approve", headers=auth_headers)
    assert first.status_code == 200
    second = await client.post("/review/job-3:stu-1/approve", headers=auth_headers)
    assert second.status_code == 409


async def test_dismiss_closes_without_sis_write(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-4:stu-2", "stu-2", "job-4")
    )
    response = await client.post("/review/job-4:stu-2/dismiss", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "dismissed"
    assert "stu-2" not in sis_students(container)


class FakeBlob:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def download_as_bytes(self) -> bytes:
        return self._payload


class FakeBucket:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.requested: list[str] = []

    def blob(self, blob_name: str) -> FakeBlob:
        self.requested.append(blob_name)
        return FakeBlob(self._payload)


class FakeStorageClient:
    def __init__(self, payload: bytes) -> None:
        self.buckets: dict[str, FakeBucket] = {}
        self._payload = payload

    def bucket(self, name: str) -> FakeBucket:
        return self.buckets.setdefault(name, FakeBucket(self._payload))


async def test_page_image_streams_gcs_object_in_gcp_mode(
    client: httpx.AsyncClient,
    container: AppContainer,
    auth_headers: dict[str, str],
    monkeypatch,
) -> None:
    from autocurricula.api import media

    item = make_item("job-900:stu-900", "stu-900", "job-900")
    await container.review_service.store.put(item)
    container.settings = container.settings.model_copy(
        update={"local_mode": False, "gcp_project_id": "p", "gcs_bucket": "exams"}
    )
    storage = FakeStorageClient(b"page-bytes")
    monkeypatch.setattr(media, "get_storage_client", lambda: storage)

    response = await client.get(
        "/review/job-900:stu-900/page-image", headers=auth_headers
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == b"page-bytes"
    assert storage.buckets["exams"].requested == ["batches/x/stu-900.jpg"]


async def test_page_image_rejects_document_outside_configured_bucket(
    client: httpx.AsyncClient,
    container: AppContainer,
    auth_headers: dict[str, str],
) -> None:
    item = make_item("job-901:stu-901", "stu-901", "job-901")
    await container.review_service.store.put(item)
    container.settings = container.settings.model_copy(
        update={"local_mode": False, "gcp_project_id": "p", "gcs_bucket": "other"}
    )

    response = await client.get(
        "/review/job-901:stu-901/page-image", headers=auth_headers
    )

    assert response.status_code == 403
    assert "outside the configured exam bucket" in response.json()["detail"]


async def test_override_requires_authorization(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/review/job-5:stu-3/override", json={"scores": [{"criterion_id": "c", "score": 1.0}]}
    )
    assert response.status_code == 401


async def test_override_unknown_review_returns_404(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.post(
        "/review/job-5:ghost/override",
        headers=auth_headers,
        json={"scores": [{"criterion_id": "crit-a", "score": 1.0}]},
    )
    assert response.status_code == 404


async def test_override_writes_corrected_record_to_sis(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-5:stu-3", "stu-3", "job-5")
    )
    response = await client.post(
        "/review/job-5:stu-3/override",
        headers=auth_headers,
        json={
            "scores": [{"criterion_id": "crit-a", "score": 3.0}],
            "note": "handwriting was legible",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "overridden"
    assert payload["corrected_record"]["score"] == 3.0
    assert payload["corrected_record"]["percentage"] == 75.0
    assert payload["reviewer_note"] == "handwriting was legible"
    assert "stu-3" in sis_students(container)
    pending = await client.get("/review/pending", headers=auth_headers)
    assert pending.json()["count"] == 0


async def test_override_rejects_scores_beyond_the_rubric_maximum(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-6:stu-4", "stu-4", "job-6")
    )
    response = await client.post(
        "/review/job-6:stu-4/override",
        headers=auth_headers,
        json={"scores": [{"criterion_id": "crit-a", "score": 9.0}]},
    )
    assert response.status_code == 422
    assert "stu-4" not in sis_students(container)
    item = await container.review_service.store.get("job-6:stu-4")
    assert item is not None
    assert item.status.value == "pending"


async def test_override_rejects_negative_scores_at_the_schema_boundary(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-7:stu-5", "stu-5", "job-7")
    )
    response = await client.post(
        "/review/job-7:stu-5/override",
        headers=auth_headers,
        json={"scores": [{"criterion_id": "crit-a", "score": -1.0}]},
    )
    assert response.status_code == 422


async def test_override_of_a_decided_item_returns_409(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_item("job-8:stu-6", "stu-6", "job-8")
    )
    first = await client.post("/review/job-8:stu-6/dismiss", headers=auth_headers)
    assert first.status_code == 200
    second = await client.post(
        "/review/job-8:stu-6/override",
        headers=auth_headers,
        json={"scores": [{"criterion_id": "crit-a", "score": 3.0}]},
    )
    assert second.status_code == 409


async def test_labels_endpoint_requires_authorization(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/labels")).status_code == 401
    wrong = await client.get("/labels", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 403


async def test_labels_endpoint_starts_empty(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get("/labels", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


async def test_every_decision_is_readable_as_a_label(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    for review_id, student_id, job_id in (
        ("job-10:stu-a", "stu-a", "job-10"),
        ("job-11:stu-b", "stu-b", "job-11"),
        ("job-12:stu-c", "stu-c", "job-12"),
    ):
        await container.review_service.store.put(
            make_item(review_id, student_id, job_id)
        )
    assert (
        await client.post("/review/job-10:stu-a/approve", headers=auth_headers)
    ).status_code == 200
    assert (
        await client.post("/review/job-11:stu-b/dismiss", headers=auth_headers)
    ).status_code == 200
    assert (
        await client.post(
            "/review/job-12:stu-c/override",
            headers=auth_headers,
            json={"scores": [{"criterion_id": "crit-a", "score": 1.0}]},
        )
    ).status_code == 200

    response = await client.get("/labels", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 3
    decisions = {item["review_id"]: item["decision"] for item in payload["items"]}
    assert decisions == {
        "job-10:stu-a": "approve",
        "job-11:stu-b": "dismiss",
        "job-12:stu-c": "override",
    }
    override_label = next(
        item for item in payload["items"] if item["decision"] == "override"
    )
    assert override_label["human_percentage"] == 25.0
    assert override_label["machine_percentage"] == 50.0
    assert override_label["scores"] == [
        {
            "criterion_id": "crit-a",
            "machine_score": None,
            "human_score": 1.0,
            "max_score": None,
        }
    ]

    filtered = await client.get(
        "/labels", headers=auth_headers, params={"job_id": "job-11"}
    )
    assert filtered.json()["count"] == 1
    assert filtered.json()["items"][0]["decision"] == "dismiss"

    limited = await client.get("/labels", headers=auth_headers, params={"limit": 2})
    assert limited.json()["count"] == 2


async def test_labels_without_rubric_maxima_are_skipped_by_the_loader(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    from autocurricula.core.evolution.calibration_labels import load_labelled_samples

    await container.review_service.store.put(
        make_item("job-20:stu-x", "stu-x", "job-20")
    )
    response = await client.post(
        "/review/job-20:stu-x/override",
        headers=auth_headers,
        json={"scores": [{"criterion_id": "crit-a", "score": 3.0}]},
    )
    assert response.status_code == 200
    labels = await container.review_service.label_store.list_labels()
    assert [label.decision.value for label in labels] == ["override"]
    assert labels[0].scores[0].max_score is None
    assert await load_labelled_samples(container.review_service.label_store) == []
