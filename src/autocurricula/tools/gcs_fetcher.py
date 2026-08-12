import asyncio
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from autocurricula.config import Settings, get_settings, get_storage_client
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.tools.base import ToolResult

ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "image/heic",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
    }
)


class FetchError(Exception):
    pass


class Fetcher(Protocol):
    async def fetch_batch(self, batch: ExamBatch) -> ExamBatch: ...


def split_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    without_scheme = gcs_uri.removeprefix("gs://")
    bucket, separator, blob_name = without_scheme.partition("/")
    if not bucket or not separator or not blob_name:
        raise FetchError(f"invalid gcs uri: {gcs_uri}")
    return bucket, blob_name


def _require_allowed_mime(file: ExamFile) -> None:
    if file.mime_type not in ALLOWED_MIME_TYPES:
        raise FetchError(f"unsupported mime type {file.mime_type} for {file.gcs_uri}")


def _with_local_paths(
    batch: ExamBatch, resolver: Callable[[ExamFile], str]
) -> ExamBatch:
    submissions: list[ExamSubmission] = []
    for submission in batch.submissions:
        files: list[ExamFile] = []
        for file in submission.files:
            _require_allowed_mime(file)
            files.append(file.model_copy(update={"local_path": resolver(file)}))
        submissions.append(submission.model_copy(update={"files": files}))
    return batch.model_copy(update={"submissions": submissions})


class LocalStagingFetcher:
    def __init__(self, staging_dir: Path) -> None:
        self._staging_dir = staging_dir

    async def fetch_batch(self, batch: ExamBatch) -> ExamBatch:
        def resolve(file: ExamFile) -> str:
            bucket, blob_name = split_gcs_uri(file.gcs_uri)
            local_file = self._staging_dir / bucket / blob_name
            if not local_file.is_file():
                raise FetchError(f"staged file missing for {file.gcs_uri} at {local_file}")
            return str(local_file)

        return await asyncio.to_thread(_with_local_paths, batch, resolve)


class GcsFetcher:
    def __init__(self, settings: Settings, storage_client: Any | None = None) -> None:
        self._settings = settings
        self._client = storage_client if storage_client is not None else get_storage_client()
        if self._client is None:
            raise FetchError("gcs fetcher requires a configured storage client")
        self._temp_dirs: list[Path] = []

    async def fetch_batch(self, batch: ExamBatch) -> ExamBatch:
        target_dir = Path(tempfile.mkdtemp(prefix="gradesync-fetch-"))
        self._temp_dirs.append(target_dir)

        def resolve(file: ExamFile) -> str:
            bucket, blob_name = split_gcs_uri(file.gcs_uri)
            destination = target_dir / bucket / blob_name
            destination.parent.mkdir(parents=True, exist_ok=True)
            self._client.bucket(bucket).blob(blob_name).download_to_filename(
                str(destination)
            )
            if not destination.is_file():
                raise FetchError(f"download produced no file for {file.gcs_uri}")
            return str(destination)

        return await asyncio.to_thread(_with_local_paths, batch, resolve)

    async def cleanup(self) -> None:
        dirs, self._temp_dirs = self._temp_dirs, []
        for path in dirs:
            await asyncio.to_thread(shutil.rmtree, path, True)


def build_fetcher(settings: Settings) -> Fetcher:
    if settings.local_mode:
        return LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir)
    return GcsFetcher(settings=settings)


async def fetch_exam_files(
    batch: ExamBatch | dict[str, Any],
    fetcher: Fetcher | None = None,
) -> ToolResult:
    try:
        parsed = ExamBatch.model_validate(batch) if isinstance(batch, dict) else batch
        active = fetcher if fetcher is not None else build_fetcher(get_settings())
        fetched = await active.fetch_batch(parsed)
    except Exception as error:
        return ToolResult.failure(str(error))
    files = {
        submission.submission_id: [
            file.local_path if file.local_path is not None else ""
            for file in submission.files
        ]
        for submission in fetched.submissions
    }
    return ToolResult.success(
        payload={
            "job_id": fetched.job_id,
            "class_id": fetched.class_id,
            "submission_count": len(fetched.submissions),
            "files": files,
        }
    )
