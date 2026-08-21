import asyncio
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from autocurricula.config import Settings, get_firestore_client
from autocurricula.core.review.store import (
    FirestoreReviewStore,
    LocalReviewStore,
    ReviewStore,
)
from autocurricula.schemas.labels import Label

LABELS_COLLECTION = "labels"
DEFAULT_LABEL_LIMIT = 100


@runtime_checkable
class LabelStore(Protocol):
    async def put(self, label: Label) -> None: ...

    async def list_labels(
        self, job_id: str | None = None, limit: int = DEFAULT_LABEL_LIMIT
    ) -> list[Label]: ...


def parse_label(payload: str | bytes) -> Label:
    try:
        return Label.model_validate_json(payload)
    except ValidationError as error:
        raise ValueError(f"label failed schema validation: {error}") from error


def _select(labels: list[Label], job_id: str | None, limit: int) -> list[Label]:
    matching = [label for label in labels if job_id is None or label.job_id == job_id]
    ordered = sorted(
        matching, key=lambda label: (label.created_at, label.label_id), reverse=True
    )
    return ordered[:limit]


class InMemoryLabelStore:
    def __init__(self) -> None:
        self._labels: dict[str, Label] = {}

    async def put(self, label: Label) -> None:
        self._labels[label.label_id] = label

    async def list_labels(
        self, job_id: str | None = None, limit: int = DEFAULT_LABEL_LIMIT
    ) -> list[Label]:
        return _select(list(self._labels.values()), job_id, limit)


class LocalLabelStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir) / "labels"

    async def put(self, label: Label) -> None:
        await asyncio.to_thread(self._write, label)

    async def list_labels(
        self, job_id: str | None = None, limit: int = DEFAULT_LABEL_LIMIT
    ) -> list[Label]:
        if not await asyncio.to_thread(self._dir.is_dir):
            return []
        paths = await asyncio.to_thread(lambda: sorted(self._dir.glob("*.json")))
        labels = [
            parse_label(await asyncio.to_thread(path.read_bytes)) for path in paths
        ]
        return _select(labels, job_id, limit)

    def _write(self, label: Label) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        stem = label.label_id.replace(":", "__").replace("/", "__")
        (self._dir / f"{stem}.json").write_text(
            label.model_dump_json(), encoding="utf-8"
        )


class FirestoreLabelStore:
    def __init__(self, collection: str = LABELS_COLLECTION, client: Any = None) -> None:
        self._collection = collection
        self._client = client if client is not None else get_firestore_client()
        if self._client is None:
            raise RuntimeError("firestore label store requires a configured client")

    async def put(self, label: Label) -> None:
        payload = json.loads(label.model_dump_json())

        def _write() -> None:
            self._client.collection(self._collection).document(label.label_id).set(
                payload
            )

        await asyncio.to_thread(_write)

    async def list_labels(
        self, job_id: str | None = None, limit: int = DEFAULT_LABEL_LIMIT
    ) -> list[Label]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        def _query() -> list[Any]:
            collection = self._client.collection(self._collection)
            if job_id is not None:
                collection = collection.where(
                    filter=FieldFilter("job_id", "==", job_id)
                )
            return list(collection.stream())

        snapshots = await asyncio.to_thread(_query)
        labels = [
            parse_label(json.dumps(snapshot.to_dict(), default=str))
            for snapshot in snapshots
        ]
        return _select(labels, job_id, limit)


def build_label_store(settings: Settings) -> LabelStore:
    if settings.local_mode:
        return LocalLabelStore(data_dir=settings.local_data_dir)
    return FirestoreLabelStore(collection=LABELS_COLLECTION)


def label_store_for(review_store: ReviewStore) -> LabelStore:
    if isinstance(review_store, LocalReviewStore):
        return LocalLabelStore(data_dir=review_store.data_dir)
    if isinstance(review_store, FirestoreReviewStore):
        return FirestoreLabelStore(client=review_store.client)
    return InMemoryLabelStore()
