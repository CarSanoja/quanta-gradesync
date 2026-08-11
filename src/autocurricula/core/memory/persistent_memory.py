import asyncio
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import TypeAdapter

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.memory import ClassCompetencySnapshot, EpisodicStudentProfile

SNAPSHOT_KEY_SEPARATOR = "::"


@runtime_checkable
class PersistentStore(Protocol):
    async def get_profile(self, student_id: str) -> EpisodicStudentProfile | None: ...

    async def put_profile(self, profile: EpisodicStudentProfile) -> None: ...

    async def get_class_snapshot(
        self, class_id: str, competency_code: str
    ) -> ClassCompetencySnapshot | None: ...

    async def put_class_snapshot(self, snapshot: ClassCompetencySnapshot) -> None: ...

    async def list_profiles(self) -> list[EpisodicStudentProfile]: ...


def _snapshot_key(class_id: str, competency_code: str) -> str:
    return f"{class_id}{SNAPSHOT_KEY_SEPARATOR}{competency_code}"


class LocalPersistentStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._profiles_path = self._data_dir / "profiles.json"
        self._snapshots_path = self._data_dir / "class_snapshots.json"
        self._lock = asyncio.Lock()
        self._profiles: dict[str, EpisodicStudentProfile] = self._read(
            self._profiles_path, dict[str, EpisodicStudentProfile]
        )
        self._snapshots: dict[str, ClassCompetencySnapshot] = self._read(
            self._snapshots_path, dict[str, ClassCompetencySnapshot]
        )

    def __len__(self) -> int:
        return len(self._profiles)

    async def get_profile(self, student_id: str) -> EpisodicStudentProfile | None:
        return self._profiles.get(student_id)

    async def put_profile(self, profile: EpisodicStudentProfile) -> None:
        async with self._lock:
            self._profiles[profile.student_id] = profile
            await self._flush()

    async def get_class_snapshot(
        self, class_id: str, competency_code: str
    ) -> ClassCompetencySnapshot | None:
        return self._snapshots.get(_snapshot_key(class_id, competency_code))

    async def put_class_snapshot(self, snapshot: ClassCompetencySnapshot) -> None:
        async with self._lock:
            key = _snapshot_key(snapshot.class_id, snapshot.competency_code)
            self._snapshots[key] = snapshot
            await self._flush()

    async def list_profiles(self) -> list[EpisodicStudentProfile]:
        return sorted(self._profiles.values(), key=lambda item: item.student_id)

    async def _flush(self) -> None:
        profiles_payload = {
            student_id: profile.model_dump(mode="json")
            for student_id, profile in self._profiles.items()
        }
        snapshots_payload = {
            key: snapshot.model_dump(mode="json")
            for key, snapshot in self._snapshots.items()
        }
        self._data_dir.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            self._profiles_path.write_text,
            json.dumps(profiles_payload, indent=2, sort_keys=True),
            "utf-8",
        )
        await asyncio.to_thread(
            self._snapshots_path.write_text,
            json.dumps(snapshots_payload, indent=2, sort_keys=True),
            "utf-8",
        )

    @staticmethod
    def _read(path: Path, adapter_type: Any) -> Any:
        if not path.exists():
            return {}
        adapter = TypeAdapter(adapter_type)
        return dict(adapter.validate_json(path.read_text(encoding="utf-8")))


class FirestorePersistentStore:
    def __init__(
        self, client: Any, profiles_collection: str, competencies_collection: str
    ) -> None:
        if client is None:
            raise ValueError(
                "FirestorePersistentStore requires a Firestore client; "
                "set GRADESYNC_GCP_PROJECT_ID or keep local_mode enabled"
            )
        self._client = client
        self._profiles_collection = profiles_collection
        self._competencies_collection = competencies_collection

    async def get_profile(self, student_id: str) -> EpisodicStudentProfile | None:
        def _read() -> EpisodicStudentProfile | None:
            document = (
                self._client.collection(self._profiles_collection)
                .document(student_id)
                .get()
            )
            if not document.exists:
                return None
            return EpisodicStudentProfile.model_validate(document.to_dict())

        return await asyncio.to_thread(_read)

    async def put_profile(self, profile: EpisodicStudentProfile) -> None:
        payload = profile.model_dump(mode="json")

        def _write() -> None:
            self._client.collection(self._profiles_collection).document(
                profile.student_id
            ).set(payload)

        await asyncio.to_thread(_write)

    async def get_class_snapshot(
        self, class_id: str, competency_code: str
    ) -> ClassCompetencySnapshot | None:
        document_id = _snapshot_key(class_id, competency_code)

        def _read() -> ClassCompetencySnapshot | None:
            document = (
                self._client.collection(self._competencies_collection)
                .document(document_id)
                .get()
            )
            if not document.exists:
                return None
            return ClassCompetencySnapshot.model_validate(document.to_dict())

        return await asyncio.to_thread(_read)

    async def put_class_snapshot(self, snapshot: ClassCompetencySnapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        document_id = _snapshot_key(snapshot.class_id, snapshot.competency_code)

        def _write() -> None:
            self._client.collection(self._competencies_collection).document(
                document_id
            ).set(payload)

        await asyncio.to_thread(_write)

    async def list_profiles(self) -> list[EpisodicStudentProfile]:
        def _list() -> list[EpisodicStudentProfile]:
            documents = self._client.collection(self._profiles_collection).stream()
            return [
                EpisodicStudentProfile.model_validate(document.to_dict())
                for document in documents
            ]

        return await asyncio.to_thread(_list)


def build_persistent_store(
    settings: Settings, data_dir: Path | None = None
) -> PersistentStore:
    if settings.local_mode:
        return LocalPersistentStore(data_dir or settings.local_data_dir)
    return FirestorePersistentStore(
        client=get_firestore_client(),
        profiles_collection=settings.firestore_profiles_collection,
        competencies_collection=settings.firestore_competencies_collection,
    )
