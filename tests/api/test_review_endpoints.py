import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from autocurricula.api.dependencies import AppContainer
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.review import ReviewItem
from autocurricula.schemas.sis_sync import SISGradeRecord

SUBJECT = "matematicas"
GRADED_AT = datetime(2026, 8, 17, 11, 0, tzinfo=timezone.utc)


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
