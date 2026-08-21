import asyncio
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import TypeAdapter

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.memory import AssessmentFact

FACTS_FILE_NAME = "assessment_facts.json"
FACTS_COLLECTION = "assessment_facts"


@runtime_checkable
class AssessmentFactStore(Protocol):
    async def put(self, fact: AssessmentFact) -> None: ...

    async def list_for_student(self, student_id: str) -> list[AssessmentFact]: ...


def _sorted(facts: list[AssessmentFact]) -> list[AssessmentFact]:
    return sorted(facts, key=lambda fact: (fact.term, fact.fact_id))


class LocalAssessmentFactStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._path = self._data_dir / FACTS_FILE_NAME
        self._lock = asyncio.Lock()
        self._facts: dict[str, AssessmentFact] = self._read()

    def __len__(self) -> int:
        return len(self._facts)

    async def put(self, fact: AssessmentFact) -> None:
        async with self._lock:
            self._facts[fact.fact_id] = fact
            payload = {
                fact_id: entry.model_dump(mode="json")
                for fact_id, entry in self._facts.items()
            }
            self._data_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(
                self._path.write_text,
                json.dumps(payload, indent=2, sort_keys=True),
                "utf-8",
            )

    async def list_for_student(self, student_id: str) -> list[AssessmentFact]:
        return _sorted(
            [fact for fact in self._facts.values() if fact.student_id == student_id]
        )

    def _read(self) -> dict[str, AssessmentFact]:
        if not self._path.exists():
            return {}
        adapter = TypeAdapter(dict[str, AssessmentFact])
        return dict(adapter.validate_json(self._path.read_text(encoding="utf-8")))


class FirestoreAssessmentFactStore:
    def __init__(self, client: Any, collection: str = FACTS_COLLECTION) -> None:
        if client is None:
            raise ValueError(
                "FirestoreAssessmentFactStore requires a Firestore client; "
                "set GRADESYNC_GCP_PROJECT_ID or keep local_mode enabled"
            )
        self._client = client
        self._collection = collection

    async def put(self, fact: AssessmentFact) -> None:
        payload = fact.model_dump(mode="json")

        def _write() -> None:
            self._client.collection(self._collection).document(fact.fact_id).set(payload)

        await asyncio.to_thread(_write)

    async def list_for_student(self, student_id: str) -> list[AssessmentFact]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        def _query() -> list[Any]:
            return list(
                self._client.collection(self._collection)
                .where(filter=FieldFilter("student_id", "==", student_id))
                .stream()
            )

        snapshots = await asyncio.to_thread(_query)
        return _sorted(
            [AssessmentFact.model_validate(snapshot.to_dict()) for snapshot in snapshots]
        )


def build_assessment_fact_store(
    settings: Settings, data_dir: Path | None = None
) -> AssessmentFactStore:
    if settings.local_mode:
        return LocalAssessmentFactStore(data_dir or settings.local_data_dir)
    return FirestoreAssessmentFactStore(client=get_firestore_client())
