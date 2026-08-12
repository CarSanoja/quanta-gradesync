import asyncio
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import quote

from pydantic import Field

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.schemas.common import JobId, StrictBaseModel, TzAwareDatetime, utc_now
from autocurricula.schemas.events import PubSubJobEvent

STATE_KEY_SUFFIX = "::session"
STATE_FILE_SUFFIX = ".session.json"


class JobStage(StrEnum):
    RECEIVED = "received"
    FETCHED = "fetched"
    GRADED = "graded"
    AUDITED = "audited"
    RISK_ASSESSED = "risk_assessed"
    SYNCED = "synced"
    VERIFIED = "verified"
    OPTIMIZED = "optimized"
    COMPLETED = "completed"
    FAILED = "failed"


class JobRecord(StrictBaseModel):
    job_id: JobId
    event: PubSubJobEvent
    stage: JobStage = JobStage.RECEIVED
    stage_statuses: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    updated_at: TzAwareDatetime = Field(default_factory=utc_now)


@runtime_checkable
class CheckpointStore(Protocol):
    async def save(self, record: JobRecord) -> None: ...

    async def get(self, job_id: str) -> JobRecord | None: ...

    async def save_state(self, job_id: str, state: SessionState) -> None: ...

    async def load_state(self, job_id: str) -> SessionState | None: ...


def state_document_id(job_id: str) -> str:
    return f"{job_id}{STATE_KEY_SUFFIX}"


def job_file_stem(job_id: str) -> str:
    return quote(job_id, safe="")


class LocalCheckpointStore:
    def __init__(self, data_dir: Path) -> None:
        self._jobs_dir = Path(data_dir) / "jobs"
        self._lock = asyncio.Lock()

    def _record_path(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_file_stem(job_id)}.json"

    def _state_path(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_file_stem(job_id)}{STATE_FILE_SUFFIX}"

    async def save(self, record: JobRecord) -> None:
        payload = record.model_dump_json(indent=2)
        async with self._lock:
            await self._write(self._record_path(record.job_id), payload)

    async def get(self, job_id: str) -> JobRecord | None:
        path = self._record_path(job_id)
        if not path.is_file():
            return None
        content = await asyncio.to_thread(path.read_text, "utf-8")
        return JobRecord.model_validate_json(content)

    async def save_state(self, job_id: str, state: SessionState) -> None:
        payload = state.model_dump_json(indent=2)
        async with self._lock:
            await self._write(self._state_path(job_id), payload)

    async def load_state(self, job_id: str) -> SessionState | None:
        path = self._state_path(job_id)
        if not path.is_file():
            return None
        content = await asyncio.to_thread(path.read_text, "utf-8")
        return SessionState.model_validate_json(content)

    @staticmethod
    async def _write(path: Path, payload: str) -> None:
        def _persist() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload, encoding="utf-8")

        await asyncio.to_thread(_persist)


class FirestoreCheckpointStore:
    def __init__(self, client: object, collection: str) -> None:
        if client is None:
            raise ValueError(
                "FirestoreCheckpointStore requires a Firestore client; "
                "set GRADESYNC_GCP_PROJECT_ID or keep local_mode enabled"
            )
        self._client = client
        self._collection = collection

    async def save(self, record: JobRecord) -> None:
        payload = record.model_dump(mode="json")
        document_id = record.job_id

        def _persist() -> None:
            self._client.collection(self._collection).document(document_id).set(payload)

        await asyncio.to_thread(_persist)

    async def get(self, job_id: str) -> JobRecord | None:
        def _load() -> JobRecord | None:
            document = self._client.collection(self._collection).document(job_id).get()
            if not document.exists:
                return None
            return JobRecord.model_validate(document.to_dict())

        return await asyncio.to_thread(_load)

    async def save_state(self, job_id: str, state: SessionState) -> None:
        payload = state.model_dump(mode="json")
        document_id = state_document_id(job_id)

        def _persist() -> None:
            self._client.collection(self._collection).document(document_id).set(payload)

        await asyncio.to_thread(_persist)

    async def load_state(self, job_id: str) -> SessionState | None:
        document_id = state_document_id(job_id)

        def _load() -> SessionState | None:
            document = self._client.collection(self._collection).document(document_id).get()
            if not document.exists:
                return None
            return SessionState.model_validate(document.to_dict())

        return await asyncio.to_thread(_load)


def build_checkpoint_store(settings: Settings) -> CheckpointStore:
    if settings.local_mode:
        return LocalCheckpointStore(data_dir=settings.local_data_dir)
    return FirestoreCheckpointStore(
        client=get_firestore_client(),
        collection=settings.firestore_checkpoints_collection,
    )
