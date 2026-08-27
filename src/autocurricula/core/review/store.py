import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import httpx
from pydantic import ValidationError

from autocurricula.config import Settings, get_firestore_client
from autocurricula.schemas.review import ReviewItem, ReviewStatus

logger = logging.getLogger(__name__)


@runtime_checkable
class ReviewStore(Protocol):
    async def put(self, item: ReviewItem) -> None: ...

    async def get(self, review_id: str) -> ReviewItem | None: ...

    async def list_pending(self) -> list[ReviewItem]: ...

    async def list_recent(self, limit: int = 500) -> list[ReviewItem]: ...


def serialize_item(item: ReviewItem) -> str:
    return item.model_dump_json()


def parse_item(payload: str | bytes) -> ReviewItem:
    try:
        return ReviewItem.model_validate_json(payload)
    except ValidationError as error:
        raise ValueError(f"review item failed schema validation: {error}") from error


class LocalReviewStore:
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = Path(data_dir)
        self._dir = self._data_dir / "reviews"

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    async def put(self, item: ReviewItem) -> None:
        await asyncio.to_thread(self._write, item)

    async def get(self, review_id: str) -> ReviewItem | None:
        path = self._dir / f"{self._file_stem(review_id)}.json"
        if not await asyncio.to_thread(path.is_file):
            return None
        payload = await asyncio.to_thread(path.read_bytes)
        return parse_item(payload)

    async def list_pending(self) -> list[ReviewItem]:
        items = await self.list_recent()
        pending = [item for item in items if item.status == ReviewStatus.PENDING]
        return sorted(pending, key=lambda item: (item.created_at, item.review_id))

    async def list_recent(self, limit: int = 500) -> list[ReviewItem]:
        if not await asyncio.to_thread(self._dir.is_dir):
            return []
        names = await asyncio.to_thread(lambda: sorted(self._dir.glob("*.json")))
        items = [parse_item(await asyncio.to_thread(path.read_bytes)) for path in names]
        ordered = sorted(items, key=lambda item: (item.created_at, item.review_id))
        return ordered[-limit:]

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

    @property
    def client(self) -> Any:
        return self._client

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
                .where(filter=FieldFilter("status", "==", ReviewStatus.PENDING.value))
                .stream()
            )

        snapshots = list(await asyncio.to_thread(_query))
        items = [parse_item(json.dumps(snapshot.to_dict(), default=str)) for snapshot in snapshots]
        return sorted(items, key=lambda item: (item.created_at, item.review_id))

    async def list_recent(self, limit: int = 500) -> list[ReviewItem]:
        def _query() -> list[Any]:
            return list(self._client.collection(self._collection).stream())

        snapshots = await asyncio.to_thread(_query)
        items = [
            parse_item(json.dumps(snapshot.to_dict(), default=str))
            for snapshot in snapshots
        ]
        ordered = sorted(items, key=lambda item: (item.created_at, item.review_id))
        return ordered[-limit:]


class NotifyingReviewStore:
    def __init__(
        self,
        inner: ReviewStore,
        webhook_url: str,
        timeout_seconds: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._inner = inner
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds
        self._client = client

    @property
    def inner(self) -> ReviewStore:
        return self._inner

    async def put(self, item: ReviewItem) -> None:
        previous = await self._inner.get(item.review_id)
        await self._inner.put(item)
        newly_pending = item.status == ReviewStatus.PENDING and (
            previous is None or previous.status != ReviewStatus.PENDING
        )
        if newly_pending:
            await self._notify(item)

    async def get(self, review_id: str) -> ReviewItem | None:
        return await self._inner.get(review_id)

    async def list_pending(self) -> list[ReviewItem]:
        return await self._inner.list_pending()

    async def list_recent(self, limit: int = 500) -> list[ReviewItem]:
        return await self._inner.list_recent(limit)

    async def _notify(self, item: ReviewItem) -> None:
        payload = {
            "event": "gradesync.review.pending",
            "review_id": item.review_id,
            "job_id": item.job_id,
            "student_id": item.student_id,
            "subject": item.subject,
            "reasons": item.reasons,
            "waiting_since": item.created_at.isoformat(),
        }
        try:
            if self._client is not None:
                response = await self._client.post(self._webhook_url, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                    response = await client.post(self._webhook_url, json=payload)
            response.raise_for_status()
        except Exception as error:
            logger.warning(
                "teacher notification webhook failed for review %s: %s",
                item.review_id,
                error,
            )


def build_review_store(settings: Settings) -> ReviewStore:
    inner: ReviewStore
    if settings.local_mode:
        inner = LocalReviewStore(data_dir=settings.local_data_dir)
    else:
        inner = FirestoreReviewStore(collection=settings.firestore_reviews_collection)
    if settings.teacher_notification_webhook_url:
        return NotifyingReviewStore(
            inner,
            settings.teacher_notification_webhook_url,
            settings.teacher_notification_timeout_seconds,
        )
    return inner
