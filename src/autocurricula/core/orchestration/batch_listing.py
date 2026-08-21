import asyncio
import logging
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from autocurricula.config import Settings, get_settings, get_storage_client
from autocurricula.core.orchestration.manifest_inference import MIME_BY_EXTENSION
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.verification import MissingFilesReport

logger = logging.getLogger(__name__)


@runtime_checkable
class BatchObjectLister(Protocol):
    async def list_names(self, event: PubSubJobEvent, batch: ExamBatch) -> list[str]: ...


def is_gradable(name: str) -> bool:
    return Path(name).suffix.lower() in MIME_BY_EXTENSION


def gradable_names(names: list[str]) -> set[str]:
    return {name for name in names if is_gradable(name)}


def manifest_names(batch: ExamBatch) -> set[str]:
    return {
        Path(file.gcs_uri).name
        for submission in batch.submissions
        for file in submission.files
    }


def _staged_root(batch: ExamBatch) -> Path | None:
    for submission in batch.submissions:
        for file in submission.files:
            if file.local_path:
                return Path(file.local_path).parent
    return None


class LocalBatchLister:
    def __init__(self, staging_dir: Path) -> None:
        self._staging_dir = Path(staging_dir)

    async def list_names(self, event: PubSubJobEvent, batch: ExamBatch) -> list[str]:
        return await asyncio.to_thread(self._read, event, batch)

    def _read(self, event: PubSubJobEvent, batch: ExamBatch) -> list[str]:
        root = self._staging_dir / event.bucket / event.exam_batch_prefix.rstrip("/")
        if not root.is_dir():
            staged = _staged_root(batch)
            if staged is None or not staged.is_dir():
                raise FileNotFoundError(f"no staged batch directory at {root}")
            root = staged
        return [path.name for path in root.iterdir() if path.is_file()]


class GcsBatchLister:
    def __init__(self, storage_client: Any | None = None) -> None:
        self._client = (
            storage_client if storage_client is not None else get_storage_client()
        )
        if self._client is None:
            raise RuntimeError("batch listing requires a configured storage client")

    async def list_names(self, event: PubSubJobEvent, batch: ExamBatch) -> list[str]:
        prefix = event.exam_batch_prefix.rstrip("/") + "/"

        def _list() -> list[str]:
            return [
                blob.name[len(prefix) :]
                for blob in self._client.list_blobs(event.bucket, prefix=prefix)
                if "/" not in blob.name[len(prefix) :]
            ]

        return await asyncio.to_thread(_list)


def build_batch_lister(settings: Settings | None = None) -> BatchObjectLister:
    active = settings if settings is not None else get_settings()
    if active.local_mode:
        return LocalBatchLister(staging_dir=active.gcs_local_staging_dir)
    return GcsBatchLister()


async def compare_batch_objects(
    event: PubSubJobEvent,
    batch: ExamBatch,
    lister: BatchObjectLister | None = None,
) -> MissingFilesReport:
    expected = manifest_names(batch)
    try:
        active = lister if lister is not None else build_batch_lister()
        listed = gradable_names(await active.list_names(event, batch))
    except Exception as error:
        logger.warning(
            "batch completeness listing unavailable for job %s: %s", event.job_id, error
        )
        return MissingFilesReport(
            checked=False,
            manifest_count=len(expected),
            detail=f"batch listing unavailable: {type(error).__name__}: {error}",
        )
    missing = sorted(listed - expected)
    return MissingFilesReport(
        checked=True,
        manifest_count=len(expected),
        listed_count=len(listed),
        missing=missing,
        detail=_completeness_detail(len(expected), len(listed), missing),
    )


def _completeness_detail(expected: int, listed: int, missing: list[str]) -> str:
    if not missing:
        return f"{listed}/{expected} gradable objects under the prefix are in the manifest"
    return (
        f"{len(missing)} gradable objects arrived after grading started and were "
        f"never graded ({listed} under the prefix, {expected} in the manifest): "
        f"{', '.join(missing)}"
    )
