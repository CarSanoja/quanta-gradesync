import asyncio
import json
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from autocurricula.config import Settings
from autocurricula.config.clients import get_firestore_client
from autocurricula.schemas.common import FrozenStrictModel, utc_now


class DeadLetterStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    EXHAUSTED = "exhausted"


class DeadLetterEntry(FrozenStrictModel):
    kind: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    target: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    status: DeadLetterStatus = DeadLetterStatus.PENDING
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())

    @property
    def exhausted(self) -> bool:
        return self.attempts >= self.max_attempts


@runtime_checkable
class DeadLetterStore(Protocol):
    async def record(self, entry: DeadLetterEntry) -> None: ...

    async def list_pending(self, job_id: str, kind: str) -> list[DeadLetterEntry]: ...

    async def list_exhausted(self, job_id: str, kind: str) -> list[DeadLetterEntry]: ...

    async def resolve(self, job_id: str, kind: str, target: str) -> None: ...


def _entry_key(entry: DeadLetterEntry) -> str:
    return f"{entry.kind}::{entry.target}"


class LocalDeadLetterStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = Path(data_dir) / "dead_letter.json"
        self._lock = asyncio.Lock()

    async def record(self, entry: DeadLetterEntry) -> None:
        async with self._lock:
            state = await self._load()
            state[_entry_key(entry)] = entry.model_dump(mode="json")
            await self._save(state)

    async def list_pending(self, job_id: str, kind: str) -> list[DeadLetterEntry]:
        return [
            entry
            for entry in await self._all(job_id, kind)
            if entry.status == DeadLetterStatus.PENDING
        ]

    async def list_exhausted(self, job_id: str, kind: str) -> list[DeadLetterEntry]:
        return [
            entry
            for entry in await self._all(job_id, kind)
            if entry.status == DeadLetterStatus.EXHAUSTED
        ]

    async def resolve(self, job_id: str, kind: str, target: str) -> None:
        async with self._lock:
            state = await self._load()
            key = f"{kind}::{target}"
            payload = state.get(key)
            if payload is None or payload["job_id"] != job_id:
                return
            payload["status"] = DeadLetterStatus.RESOLVED.value
            state[key] = payload
            await self._save(state)

    async def _all(self, job_id: str, kind: str) -> list[DeadLetterEntry]:
        state = await self._load()
        return [
            DeadLetterEntry.model_validate(payload)
            for payload in state.values()
            if payload["job_id"] == job_id and payload["kind"] == kind
        ]

    async def _load(self) -> dict[str, Any]:
        def _read() -> dict[str, Any]:
            if not self._path.is_file():
                return {}
            return json.loads(self._path.read_text(encoding="utf-8"))

        return await asyncio.to_thread(_read)

    async def _save(self, state: dict[str, Any]) -> None:
        await asyncio.to_thread(
            self._path.write_text,
            json.dumps(state, indent=2, sort_keys=True),
            "utf-8",
        )


class FirestoreDeadLetterStore:
    def __init__(self, collection: str, client: Any | None = None) -> None:
        self._collection = collection
        self._client = client if client is not None else get_firestore_client()
        if self._client is None:
            raise RuntimeError("firestore dead letter store requires a client")

    async def record(self, entry: DeadLetterEntry) -> None:
        payload = entry.model_dump(mode="json")

        def _write() -> None:
            self._client.collection(self._collection).document(
                f"{entry.job_id}:{_entry_key(entry)}"
            ).set(payload)

        await asyncio.to_thread(_write)

    async def list_pending(self, job_id: str, kind: str) -> list[DeadLetterEntry]:
        return [
            entry
            for entry in await self._list(job_id)
            if entry.kind == kind and entry.status == DeadLetterStatus.PENDING
        ]

    async def list_exhausted(self, job_id: str, kind: str) -> list[DeadLetterEntry]:
        return [
            entry
            for entry in await self._list(job_id)
            if entry.kind == kind and entry.status == DeadLetterStatus.EXHAUSTED
        ]

    async def resolve(self, job_id: str, kind: str, target: str) -> None:
        def _write() -> None:
            self._client.collection(self._collection).document(
                f"{job_id}:{kind}::{target}"
            ).set({"status": DeadLetterStatus.RESOLVED.value}, merge=True)

        await asyncio.to_thread(_write)

    async def _list(self, job_id: str) -> list[DeadLetterEntry]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        def _read() -> list[dict[str, Any]]:
            return [
                document.to_dict()
                for document in self._client.collection(self._collection)
                .where(filter=FieldFilter("job_id", "==", job_id))
                .stream()
            ]

        return [DeadLetterEntry.model_validate(payload) for payload in await asyncio.to_thread(_read)]


def build_dead_letter_store(settings: Settings) -> DeadLetterStore:
    if settings.local_mode:
        return LocalDeadLetterStore(settings.local_data_dir)
    return FirestoreDeadLetterStore(settings.firestore_dead_letter_collection)
