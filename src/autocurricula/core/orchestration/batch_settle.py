import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from autocurricula.config import Settings, get_storage_client
from autocurricula.schemas.events import PubSubJobEvent

logger = logging.getLogger(__name__)

DEFAULT_SETTLE_MAX_ROUNDS = 6
LISTING_FAILED = -1

Sleeper = Callable[[float], Awaitable[None]]


class BatchLister(Protocol):
    async def count_objects(self, bucket: str, prefix: str) -> int: ...


class LocalBatchLister:
    def __init__(self, staging_dir: Path) -> None:
        self._staging_dir = Path(staging_dir)

    async def count_objects(self, bucket: str, prefix: str) -> int:
        def _count() -> int:
            root = self._staging_dir / bucket / prefix.rstrip("/")
            if not root.is_dir():
                return 0
            return sum(1 for path in root.iterdir() if path.is_file())

        return await asyncio.to_thread(_count)


class GcsBatchLister:
    def __init__(self, storage_client: Any) -> None:
        self._client = storage_client

    async def count_objects(self, bucket: str, prefix: str) -> int:
        normalized = prefix.rstrip("/") + "/"

        def _count() -> int:
            return sum(
                1
                for blob in self._client.list_blobs(bucket, prefix=normalized)
                if "/" not in blob.name[len(normalized) :]
            )

        return await asyncio.to_thread(_count)


class BatchSettler:
    def __init__(
        self,
        lister: BatchLister,
        interval_seconds: float,
        max_rounds: int = DEFAULT_SETTLE_MAX_ROUNDS,
        sleeper: Sleeper = asyncio.sleep,
    ) -> None:
        self._lister = lister
        self._interval = float(interval_seconds)
        self._max_rounds = int(max_rounds)
        self._sleeper = sleeper

    @property
    def interval_seconds(self) -> float:
        return self._interval

    async def wait(self, event: PubSubJobEvent) -> int:
        if self._interval <= 0 or self._max_rounds < 1:
            return LISTING_FAILED
        previous = await self._count(event)
        for _ in range(self._max_rounds):
            await self._sleeper(self._interval)
            current = await self._count(event)
            if current == previous:
                return current
            previous = current
        logger.warning(
            "batch gs://%s/%s never settled after %s rounds; proceeding with %s objects",
            event.bucket,
            event.exam_batch_prefix,
            self._max_rounds,
            previous,
        )
        return previous

    async def _count(self, event: PubSubJobEvent) -> int:
        try:
            return await self._lister.count_objects(
                event.bucket, event.exam_batch_prefix
            )
        except Exception as error:
            logger.warning(
                "settle listing failed for gs://%s/%s: %s",
                event.bucket,
                event.exam_batch_prefix,
                error,
            )
            return LISTING_FAILED


def build_batch_lister(
    settings: Settings, storage_client: Any | None = None
) -> BatchLister | None:
    if settings.local_mode:
        return LocalBatchLister(staging_dir=settings.gcs_local_staging_dir)
    client = storage_client if storage_client is not None else get_storage_client()
    if client is None:
        return None
    return GcsBatchLister(client)


def build_batch_settler(
    settings: Settings, storage_client: Any | None = None
) -> BatchSettler | None:
    if settings.batch_settle_interval_seconds <= 0:
        return None
    lister = build_batch_lister(settings, storage_client)
    if lister is None:
        logger.warning("upload settle disabled: no storage client is configured")
        return None
    return BatchSettler(
        lister=lister,
        interval_seconds=settings.batch_settle_interval_seconds,
        max_rounds=settings.batch_settle_max_rounds,
    )
