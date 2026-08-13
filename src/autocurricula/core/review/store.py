import asyncio
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from autocurricula.config import Settings, get_firestore_client
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.review import ReviewItem, ReviewStatus


@runtime_checkable
class ReviewStore(Protocol):
    async def put(self, item: ReviewItem) -> None: ...

    async def get(self, review_id: str) -> ReviewItem | None: ...

    async def list_pending(self) -> list[ReviewItem]: ...


def serialize_item(item: ReviewItem) -> str:
    return item.model_dump_json()


def parse_item(payload: str | bytes) -> ReviewItem:
    try:
        return ReviewItem.model_validate_json(payload)
    except ValidationError as error:
        raise ValueError(f"review item failed schema validation: {error}") from error


class LocalReviewStore:
    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir) / "reviews"

    async def put(self, item: ReviewItem) -> None:
        await asyncio.to_thread(self._write, item)

    async def get(self, review_id: str) -> ReviewItem | None:
        path = self._dir / f"{self._file_stem(review_id)}.json"
        if not await asyncio.to_thread(path.is_file):
            return None
        payload = await asyncio.to_thread(path.read_bytes)
        return parse_item(payload)

    async def list_pending(self) -> list[ReviewItem]:
        if not await asyncio.to_thread(self._dir.is_dir):
            return []
        names = await asyncio.to_thread(lambda: sorted(self._dir.glob("*.json")))
        items = [parse_item(await asyncio.to_thread(path.read_bytes)) for path in names]
        pending = [item for item in items if item.status == ReviewStatus.PENDING]
        return sorted(pending, key=lambda item: (item.created_at, item.review_id))

    def _write(self, item: ReviewItem) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{self._file_stem(item.review_id)}.json"
        path.write_text(serialize_item(item), encoding="utf-8")

    @staticmethod
    def _file_stem(review_id: str) -> str:
        return review_id.replace(":", "__")


class FirestoreReviewStore:
    def __init__(self, collection: str, client: Any | None = None) -> None:
        self._collection = collection
        self._client = client if client is not None else get_firestore_client()
        if self._client is None:
            raise RuntimeError("firestore review store requires a configured client")

    async def put(self, item: ReviewItem) -> None:
        def _write() -> None:
            self._client.collection(self._collection).document(item.review_id).set(
                json.loads(item.model_dump_json())
            )

        await asyncio.to_thread(_write)

    async def get(self, review_id: str) -> ReviewItem | None:
        def _read() -> Any | None:
            return self._client.collection(self._collection).document(review_id).get()

        snapshot = await asyncio.to_thread(_read)
        if snapshot is None or not snapshot.exists:
            return None
        return parse_item(json.dumps(snapshot.to_dict(), default=str))

    async def list_pending(self) -> list[ReviewItem]:
        from google.cloud.firestore_v1.base_query import FieldFilter

        def _query() -> list[Any]:
            return (
                self._client.collection(self._collection)
                .where(filter=FieldFilter.field("status").equal(ReviewStatus.PENDING.value))
                .stream()
            )

        snapshots = list(await asyncio.to_thread(_query))
        items = [parse_item(json.dumps(snapshot.to_dict(), default=str)) for snapshot in snapshots]
        return sorted(items, key=lambda item: (item.created_at, item.review_id))


def build_review_store(settings: Settings) -> ReviewStore:
    if settings.local_mode:
        return LocalReviewStore(data_dir=settings.local_data_dir)
    return FirestoreReviewStore(collection=settings.firestore_reviews_collection)
