import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from autocurricula.api import sis_ledger_sources
from autocurricula.api.dependencies import AppContainer, build_container, set_container
from autocurricula.api.main import create_app
from autocurricula.config.settings import Settings
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteRequest
from autocurricula.tools import sis_connector as sis_connector_module
from autocurricula.tools import sis_firestore
from autocurricula.tools.sis_connector import (
    HttpSISConnector,
    LocalSISConnector,
    build_sis_connector,
)
from autocurricula.tools.sis_firestore import FirestoreSISConnector, sis_document_id

LEDGER_TOKEN = "ledger-test-token"
JOB_ID = "2026-matematicas-10a-parcial1"
PREFIX = "batches/2026_Matematicas_10A_Parcial1"
GRADED_AT = datetime(2026, 8, 19, 12, 0, tzinfo=UTC)


class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return deepcopy(self._data) if self._data is not None else None


class FakeDocument:
    def __init__(self, docs, key):
        self._docs = docs
        self._key = key

    def set(self, payload):
        self._docs[self._key] = deepcopy(payload)

    def get(self):
        return FakeSnapshot(self._docs.get(self._key))


class FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def where(self, *args, filter=None):
        if filter is not None:
            field, value = filter.field_path, filter.value
        else:
            field, _, value = args
        return FakeQuery([row for row in self._rows if row.get(field) == value])

    def order_by(self, field, direction="ASCENDING"):
        ordered = sorted(
            self._rows,
            key=lambda row: str(row.get(field) or ""),
            reverse=direction == "DESCENDING",
        )
        return FakeQuery(ordered)

    def limit(self, count):
        return FakeQuery(self._rows[:count])

    def stream(self):
        return [FakeSnapshot(row) for row in self._rows]


class FakeCollection(FakeQuery):
    def __init__(self, docs):
        self._docs = docs
        super().__init__([])

    def document(self, key):
        return FakeDocument(self._docs, key)

    def _current(self):
        return list(self._docs.values())

    def where(self, *args, filter=None):
        return FakeQuery(self._current()).where(*args, filter=filter)

    def order_by(self, field, direction="ASCENDING"):
        return FakeQuery(self._current()).order_by(field, direction=direction)

    def stream(self):
        return FakeQuery(self._current()).stream()


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return FakeCollection(self.collections.setdefault(name, {}))


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "local_mode": True,
        "gcp_project_id": "",
        "pubsub_push_token": LEDGER_TOKEN,
        "local_data_dir": tmp_path / "local_data",
        "gcs_local_staging_dir": tmp_path / "staging",
        "batch_settle_interval_seconds": 0.0,
    }
    values.update(overrides)
    return Settings(**values)


def make_grade_record(student_id: str) -> SISGradeRecord:
    return SISGradeRecord(
        student_id=student_id,
        subject="matematicas",
        score=8.0,
        percentage=80.0,
        feedback="Solid factoring with a readable check.",
        competency_codes=["MAT.10.1"],
        graded_at=GRADED_AT,
    )


def make_write_request(job_id: str, student_ids: list[str]) -> SISWriteRequest:
    return SISWriteRequest(
        job_id=job_id,
        records=[make_grade_record(student_id) for student_id in student_ids],
    )


def make_job_record(job_id: str) -> JobRecord:
    event = PubSubJobEvent(
        job_id=job_id,
        bucket="quanta-gradesync-exams",
        exam_batch_prefix=PREFIX,
        class_id="10A",
        subject="matematicas",
        triggered_at=GRADED_AT,
    )
    return JobRecord(job_id=job_id, event=event, stage=JobStage.COMPLETED)


def make_stage_results(student_id: str) -> dict:
    return {
        "fetch": {
            "batch": {
                "submissions": [
                    {"submission_id": student_id, "student_id": student_id}
                ]
            }
        },
        "grade": {
            "results": [
                {
                    "submission_id": student_id,
                    "criterion_scores": [
                        {"criterion_id": "crit-a", "score": 3.5, "confidence": 0.92}
                    ],
                }
            ]
        },
    }


@pytest.fixture
def ledger_settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def ledger_container(ledger_settings: Settings) -> AppContainer:
    return build_container(ledger_settings)


@pytest.fixture
def ledger_app(ledger_container: AppContainer) -> FastAPI:
    application = create_app()
    set_container(application, ledger_container)
    return application


@pytest.fixture
async def ledger_client(ledger_app: FastAPI):
    transport = httpx.ASGITransport(app=ledger_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://gradesync.test"
    ) as active:
        yield active


@pytest.fixture
def ledger_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {LEDGER_TOKEN}"}


def test_build_sis_connector_prefers_firestore_over_the_jsonl_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeFirestore()
    monkeypatch.setattr(sis_firestore, "get_firestore_client", lambda: fake)
    local = build_sis_connector(make_settings(tmp_path))
    assert isinstance(local, LocalSISConnector)
    gcp = build_sis_connector(
        make_settings(tmp_path, local_mode=False, gcp_project_id="test-project")
    )
    assert isinstance(gcp, FirestoreSISConnector)
    http = build_sis_connector(
        make_settings(
            tmp_path,
            local_mode=False,
            gcp_project_id="test-project",
            sis_base_url="https://sis.example.test/api",
            sis_api_token="sis-token",
        )
    )
    assert isinstance(http, HttpSISConnector)
    assert sis_connector_module.build_sis_connector is build_sis_connector


async def test_firestore_connector_writes_idempotent_enriched_documents(
    tmp_path: Path,
) -> None:
    fake = FakeFirestore()
    settings = make_settings(tmp_path, local_mode=False, gcp_project_id="test-project")
    checkpoints = fake.collection(settings.firestore_checkpoints_collection)
    checkpoints.document(JOB_ID).set(
        {"event": {"class_id": "10A", "exam_batch_prefix": PREFIX}}
    )
    checkpoints.document(f"{JOB_ID}::session").set(
        {"stage_results": make_stage_results("ana-torres")}
    )
    connector = FirestoreSISConnector(settings=settings, client=fake)
    request = make_write_request(JOB_ID, ["ana-torres", "luis-gomez"])
    first = await connector.write_grades(request)
    second = await connector.write_grades(request)
    assert first.succeeded_count == 2
    assert first.failed_count == 0
    assert second.per_record_statuses == first.per_record_statuses
    documents = fake.collections["sis_records"]
    assert len(documents) == 2
    ana = documents[sis_document_id(JOB_ID, "ana-torres")]
    assert ana["class_id"] == "10A"
    assert ana["term"] == "Parcial1"
    assert ana["total_score"] == 8.0
    assert ana["percentage"] == 80.0
    assert ana["competency_codes"] == ["MAT.10.1"]
    assert ana["criterion_scores"] == [
        {"criterion_id": "crit-a", "score": 3.5, "confidence": 0.92}
    ]
    assert ana["written_at"]
    luis = documents[sis_document_id(JOB_ID, "luis-gomez")]
    assert luis["criterion_scores"] == []


async def test_firestore_connector_survives_missing_checkpoints(
    tmp_path: Path,
) -> None:
    fake = FakeFirestore()
    settings = make_settings(tmp_path, local_mode=False, gcp_project_id="test-project")
    connector = FirestoreSISConnector(settings=settings, client=fake)
    result = await connector.write_grades(make_write_request("job-bare", ["ana"]))
    assert result.succeeded_count == 1
    stored = fake.collections["sis_records"][sis_document_id("job-bare", "ana")]
    assert stored["class_id"] == ""
    assert stored["term"] == ""


async def test_sis_records_requires_the_push_token(
    ledger_client: httpx.AsyncClient,
) -> None:
    missing = await ledger_client.get("/sis/records")
    assert missing.status_code == 401
    wrong = await ledger_client.get(
        "/sis/records", headers={"Authorization": "Bearer nope"}
    )
    assert wrong.status_code == 403


async def test_sis_records_reads_the_local_jsonl_newest_first(
    ledger_client: httpx.AsyncClient,
    ledger_container: AppContainer,
    ledger_headers: dict[str, str],
) -> None:
    await ledger_container.checkpoint_store.save(make_job_record(JOB_ID))
    await ledger_container.checkpoint_store.save_state(
        JOB_ID,
        SessionState(job_id=JOB_ID, stage_results=make_stage_results("ana-torres")),
    )
    connector = ledger_container.sis_connector
    await connector.write_grades(make_write_request(JOB_ID, ["ana-torres"]))
    await asyncio.sleep(0.01)
    await connector.write_grades(make_write_request("job-later", ["tomas-vega"]))
    response = await ledger_client.get("/sis/records", headers=ledger_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "local"
    assert payload["count"] == 2
    newest, oldest = payload["items"]
    assert newest["student_id"] == "tomas-vega"
    assert newest["job_id"] == "job-later"
    assert oldest["student_id"] == "ana-torres"
    assert oldest["class_id"] == "10A"
    assert oldest["term"] == "Parcial1"
    assert oldest["criterion_scores"] == [
        {"criterion_id": "crit-a", "score": 3.5, "confidence": 0.92}
    ]
    filtered = await ledger_client.get(
        f"/sis/records?job_id={JOB_ID}", headers=ledger_headers
    )
    assert [item["job_id"] for item in filtered.json()["items"]] == [JOB_ID]
    limited = await ledger_client.get("/sis/records?limit=1", headers=ledger_headers)
    assert limited.json()["count"] == 1
    assert limited.json()["items"][0]["student_id"] == "tomas-vega"


async def test_sis_records_reads_firestore_in_gcp_mode(
    ledger_client: httpx.AsyncClient,
    ledger_container: AppContainer,
    ledger_headers: dict[str, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeFirestore()
    records = fake.collection("sis_records")
    records.document("a").set(
        {
            "job_id": JOB_ID,
            "student_id": "ana-torres",
            "subject": "matematicas",
            "class_id": "10A",
            "term": "Parcial1",
            "total_score": 10.0,
            "percentage": 100.0,
            "competency_codes": ["MAT.10.1"],
            "criterion_scores": [],
            "provenance": {"prompt_variant_id": "grading-v1"},
            "graded_at": "2026-08-19T12:00:00+00:00",
            "written_at": "2026-08-19T12:00:05+00:00",
        }
    )
    records.document("b").set(
        {
            "job_id": "job-later",
            "student_id": "tomas-vega",
            "subject": "matematicas",
            "class_id": "10A",
            "term": "Parcial1",
            "total_score": 3.0,
            "percentage": 30.0,
            "written_at": "2026-08-19T13:00:00+00:00",
        }
    )
    monkeypatch.setattr(sis_ledger_sources, "get_firestore_client", lambda: fake)
    ledger_container.settings = make_settings(
        tmp_path, local_mode=False, gcp_project_id="test-project"
    )
    response = await ledger_client.get("/sis/records", headers=ledger_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "firestore"
    assert [item["student_id"] for item in payload["items"]] == [
        "tomas-vega",
        "ana-torres",
    ]
    assert payload["items"][1]["prompt_variant_id"] == "grading-v1"
    filtered = await ledger_client.get(
        "/sis/records?job_id=job-later", headers=ledger_headers
    )
    assert [item["student_id"] for item in filtered.json()["items"]] == ["tomas-vega"]


def test_ledger_document_carries_student_feedback():
    from autocurricula.schemas.common import utc_now
    from autocurricula.schemas.feedback import FeedbackBand, FeedbackPoint, StudentFeedback
    from autocurricula.schemas.sis_sync import SISGradeRecord
    from autocurricula.tools.sis_firestore import build_ledger_document

    feedback = StudentFeedback(
        band=FeedbackBand.LOWER_SECONDARY,
        headline="You factored the expression correctly.",
        strengths=[FeedbackPoint(text="You checked the factor pair by expanding.")],
        growth=[FeedbackPoint(text="Next time state the time of the maximum.")],
        next_step="Write the clock time beside the highest temperature.",
        teacher_note="Confident on factoring; graph reading is the gap.",
    )
    record = SISGradeRecord(
        student_id="ana-torres",
        subject="Matematicas",
        score=9.0,
        percentage=90.0,
        feedback="Solid work.",
        graded_at=utc_now(),
        student_feedback=feedback,
    )

    doc = build_ledger_document("job-1", record, {}, "2026-08-21T00:00:00Z")

    assert doc["student_feedback"]["headline"] == "You factored the expression correctly."
    assert doc["student_feedback"]["band"] == "lower_secondary"
    assert doc["student_feedback"]["teacher_note"]
