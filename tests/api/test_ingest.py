import re
from collections import defaultdict
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from autocurricula.api import ingest as ingest_module
from autocurricula.api import ingest_storage
from autocurricula.api.dependencies import AppContainer, build_container, set_container
from autocurricula.api.main import create_app
from autocurricula.config.settings import Settings

INGEST_TOKEN = "ingest-test-token"
LOT = "2026_Matematicas_10A_Parcial1"
JPEG_BYTES = b"\xff\xd8\xff\xdb ingest scan bytes"


class FakeBlob:
    def __init__(self, store, name):
        self._store = store
        self.name = name

    def upload_from_string(self, payload, content_type=None, if_generation_match=None):
        if if_generation_match == 0 and self.name in self._store:
            error = Exception("precondition failed")
            error.code = 412
            raise error
        self._store[self.name] = (payload, content_type)


class FakeBucket:
    def __init__(self, store):
        self._store = store

    def blob(self, name):
        return FakeBlob(self._store, name)

    def copy_blob(self, blob, destination_bucket, new_name):
        destination_bucket._store[new_name] = blob._store[blob.name]


class FakeStorageClient:
    def __init__(self):
        self.buckets = defaultdict(dict)

    def bucket(self, name):
        return FakeBucket(self.buckets[name])

    def list_blobs(self, bucket_name, prefix=""):
        store = self.buckets[bucket_name]
        return [
            FakeBlob(store, name)
            for name in sorted(store)
            if name.startswith(prefix)
        ]


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "local_mode": True,
        "gcp_project_id": "",
        "pubsub_push_token": INGEST_TOKEN,
        "local_data_dir": tmp_path / "local_data",
        "gcs_local_staging_dir": tmp_path / "staging",
        "batch_settle_interval_seconds": 0.0,
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def ingest_settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def ingest_container(ingest_settings: Settings) -> AppContainer:
    return build_container(ingest_settings)


@pytest.fixture
def ingest_app(ingest_container: AppContainer) -> FastAPI:
    application = create_app()
    set_container(application, ingest_container)
    return application


@pytest.fixture
async def ingest_client(ingest_app: FastAPI):
    transport = httpx.ASGITransport(app=ingest_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gradesync.test"
    ) as active:
        yield active


@pytest.fixture
def ingest_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {INGEST_TOKEN}"}


@pytest.fixture
def fake_storage(monkeypatch: pytest.MonkeyPatch) -> FakeStorageClient:
    fake = FakeStorageClient()
    monkeypatch.setattr(ingest_storage, "get_storage_client", lambda: fake)
    return fake


def upload_body(
    name: str = "ana-torres.jpg",
    lot_code: str = LOT,
    mode: str | None = None,
    new_student_name: str | None = None,
    payload: bytes = JPEG_BYTES,
):
    data = {"lot_code": lot_code}
    if mode is not None:
        data["mode"] = mode
    if new_student_name is not None:
        data["new_student_name"] = new_student_name
    return {"data": data, "files": {"file": (name, payload, "image/jpeg")}}


async def test_ingest_requires_the_push_token(ingest_client: httpx.AsyncClient) -> None:
    response = await ingest_client.post("/ingest/exam", **upload_body())
    assert response.status_code == 401
    sample = await ingest_client.post("/ingest/sample-batch")
    assert sample.status_code == 401


async def test_local_upload_lands_in_the_staging_layout(
    ingest_client: httpx.AsyncClient,
    ingest_container: AppContainer,
    ingest_headers: dict[str, str],
) -> None:
    response = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body()
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "stored"
    assert payload["student_id"] == "ana-torres"
    assert payload["object"] == f"uploads/batches/{LOT}/ana-torres.jpg"
    staged = (
        Path(ingest_container.settings.gcs_local_staging_dir)
        / payload["bucket"]
        / payload["object"]
    )
    assert staged.read_bytes() == JPEG_BYTES


async def test_collision_then_replace_then_rename_flow(
    ingest_client: httpx.AsyncClient,
    ingest_container: AppContainer,
    ingest_headers: dict[str, str],
) -> None:
    first = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body()
    )
    assert first.status_code == 200
    duplicate = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body()
    )
    assert duplicate.status_code == 409
    body = duplicate.json()
    assert body["collision"] is True
    assert body["student_id"] == "ana-torres"
    replaced = await ingest_client.post(
        "/ingest/exam",
        headers=ingest_headers,
        **upload_body(mode="replace", payload=b"\xff\xd8\xff\xdb rescanned"),
    )
    assert replaced.status_code == 200
    staged = (
        Path(ingest_container.settings.gcs_local_staging_dir)
        / replaced.json()["bucket"]
        / replaced.json()["object"]
    )
    assert staged.read_bytes().endswith(b"rescanned")
    renamed = await ingest_client.post(
        "/ingest/exam",
        headers=ingest_headers,
        **upload_body(mode="rename", new_student_name="ana-torres-2"),
    )
    assert renamed.status_code == 200
    assert renamed.json()["student_id"] == "ana-torres-2"
    assert renamed.json()["object"] == f"uploads/batches/{LOT}/ana-torres-2.jpg"
    missing_name = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(mode="rename")
    )
    assert missing_name.status_code == 422


async def test_upload_validation_rules(
    ingest_client: httpx.AsyncClient,
    ingest_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_extension = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(name="notes.txt")
    )
    assert bad_extension.status_code == 415
    bad_lot = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(lot_code="parcial-1")
    )
    assert bad_lot.status_code == 422
    bad_stem = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(name="ana torres.jpg")
    )
    assert bad_stem.status_code == 422
    bad_mode = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(mode="upsert")
    )
    assert bad_mode.status_code == 422
    monkeypatch.setattr(ingest_module, "MAX_UPLOAD_BYTES", 16)
    oversize = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(payload=b"x" * 32)
    )
    assert oversize.status_code == 413


async def test_traversal_file_names_are_flattened_to_the_basename(
    ingest_client: httpx.AsyncClient,
    ingest_container: AppContainer,
    ingest_headers: dict[str, str],
) -> None:
    response = await ingest_client.post(
        "/ingest/exam",
        headers=ingest_headers,
        **upload_body(name="../../escape.jpg"),
    )
    assert response.status_code == 200
    assert response.json()["object"] == f"uploads/batches/{LOT}/escape.jpg"
    hidden = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(name=".env.jpg")
    )
    assert hidden.status_code == 422


async def test_batch_object_count_limit(
    ingest_client: httpx.AsyncClient,
    ingest_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ingest_module, "MAX_BATCH_OBJECTS", 2)
    for name in ("a1.jpg", "a2.jpg"):
        stored = await ingest_client.post(
            "/ingest/exam", headers=ingest_headers, **upload_body(name=name)
        )
        assert stored.status_code == 200
    rejected = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(name="a3.jpg")
    )
    assert rejected.status_code == 422
    replaced = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body(name="a1.jpg", mode="replace")
    )
    assert replaced.status_code == 200


async def test_gcs_upload_uses_generation_preconditions(
    ingest_client: httpx.AsyncClient,
    ingest_container: AppContainer,
    ingest_headers: dict[str, str],
    fake_storage: FakeStorageClient,
    tmp_path: Path,
) -> None:
    ingest_container.settings = make_settings(
        tmp_path,
        local_mode=False,
        gcp_project_id="test-project",
        gcs_bucket="quanta-gradesync-exams",
    )
    first = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body()
    )
    assert first.status_code == 200
    assert first.json()["bucket"] == "quanta-gradesync-exams"
    object_name = f"uploads/batches/{LOT}/ana-torres.jpg"
    assert fake_storage.buckets["quanta-gradesync-exams"][object_name] == (
        JPEG_BYTES,
        "image/jpeg",
    )
    duplicate = await ingest_client.post(
        "/ingest/exam", headers=ingest_headers, **upload_body()
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["collision"] is True
    replaced = await ingest_client.post(
        "/ingest/exam",
        headers=ingest_headers,
        **upload_body(mode="replace", payload=b"\xff\xd8\xff\xdb v2"),
    )
    assert replaced.status_code == 200
    assert fake_storage.buckets["quanta-gradesync-exams"][object_name][0].endswith(
        b"v2"
    )


async def test_sample_batch_requires_gcp_mode(
    ingest_client: httpx.AsyncClient, ingest_headers: dict[str, str]
) -> None:
    response = await ingest_client.post("/ingest/sample-batch", headers=ingest_headers)
    assert response.status_code == 400


async def test_sample_batch_copies_the_demo_objects_server_side(
    ingest_client: httpx.AsyncClient,
    ingest_container: AppContainer,
    ingest_headers: dict[str, str],
    fake_storage: FakeStorageClient,
    tmp_path: Path,
) -> None:
    ingest_container.settings = make_settings(
        tmp_path,
        local_mode=False,
        gcp_project_id="test-project",
        gcs_bucket="quanta-gradesync-exams",
    )
    source_prefix = ingest_storage.DEMO_SOURCE_PREFIX
    students = [
        "ana-torres", "camila-rios", "diego-castro", "julian-pardo",
        "luis-gomez", "mariana-ruiz", "sofia-morales", "tomas-vega",
    ]
    for student in students:
        fake_storage.buckets["quanta-gradesync-exams"][
            f"{source_prefix}{student}.jpg"
        ] = (b"scan", "image/jpeg")
    response = await ingest_client.post(
        "/ingest/sample-batch", headers=ingest_headers
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "copied"
    assert payload["count"] == 8
    assert re.fullmatch(
        r"demo/[0-9a-f]{8}/batches/2026_Matematicas_10A_Parcial1/",
        payload["destination_prefix"],
    )
    assert payload["expected_job_id"].startswith("demo-")
    for name in payload["objects"]:
        assert fake_storage.buckets["quanta-gradesync-exams"][name] == (
            b"scan",
            "image/jpeg",
        )
    again = await ingest_client.post("/ingest/sample-batch", headers=ingest_headers)
    assert again.json()["destination_prefix"] != payload["destination_prefix"]
