import asyncio
import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import ValidationError, model_validator

from autocurricula.config import Settings, get_storage_client
from autocurricula.core.orchestration.subjects import same_subject
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.curriculum import CurriculumStandard
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.rubric import Rubric

MANIFEST_NAME = "batch.json"


class CatalogError(Exception):
    pass


class ManifestNotFound(CatalogError):
    pass


class BatchManifest(StrictBaseModel):
    batch: ExamBatch
    rubric: Rubric
    curriculum_standard: CurriculumStandard

    @model_validator(mode="after")
    def _aligned_content(self) -> "BatchManifest":
        if self.rubric.rubric_id != self.batch.rubric_id:
            raise ValueError("manifest rubric_id does not match the batch rubric_id")
        if not same_subject(self.rubric.subject, self.batch.subject):
            raise ValueError(
                f"manifest rubric subject {self.rubric.subject!r} does not match the "
                f"batch subject {self.batch.subject!r}"
            )
        return self


@runtime_checkable
class JobCatalog(Protocol):
    async def load_manifest(self, event: PubSubJobEvent) -> BatchManifest: ...


def parse_manifest(payload: str | bytes) -> BatchManifest:
    try:
        document = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise CatalogError("batch manifest is not valid json") from error
    try:
        return BatchManifest.model_validate(document)
    except ValidationError as error:
        raise CatalogError(f"batch manifest failed schema validation: {error}") from error


def align_manifest(event: PubSubJobEvent, manifest: BatchManifest) -> BatchManifest:
    batch = manifest.batch
    if batch.class_id != event.class_id or batch.subject != event.subject:
        raise CatalogError(
            "batch manifest class_id/subject do not match the trigger event"
        )
    if batch.job_id != event.job_id:
        batch = batch.model_copy(update={"job_id": event.job_id})
    return manifest.model_copy(update={"batch": batch})


def manifest_blob_name(event: PubSubJobEvent) -> str:
    prefix = event.exam_batch_prefix.rstrip("/")
    return f"{prefix}/{MANIFEST_NAME}"


class LocalJobCatalog:
    def __init__(self, staging_dir: Path) -> None:
        self._staging_dir = Path(staging_dir)

    async def load_manifest(self, event: PubSubJobEvent) -> BatchManifest:
        path = self._staging_dir / event.bucket / manifest_blob_name(event)
        if not path.is_file():
            raise ManifestNotFound(f"batch manifest not found at {path}")
        content = await asyncio.to_thread(path.read_bytes)
        return align_manifest(event, parse_manifest(content))


class GcsJobCatalog:
    def __init__(self, settings: Settings, storage_client: object | None = None) -> None:
        self._settings = settings
        self._client = (
            storage_client if storage_client is not None else get_storage_client()
        )
        if self._client is None:
            raise CatalogError("gcs batch catalog requires a configured storage client")

    async def load_manifest(self, event: PubSubJobEvent) -> BatchManifest:
        blob_name = manifest_blob_name(event)

        def _download() -> bytes:
            return self._client.bucket(event.bucket).blob(blob_name).download_as_bytes()

        from google.cloud.exceptions import NotFound

        try:
            content = await asyncio.to_thread(_download)
        except NotFound as error:
            raise ManifestNotFound(
                f"batch manifest not found at gs://{event.bucket}/{blob_name}"
            ) from error
        except Exception as error:
            raise CatalogError(
                f"failed to download manifest gs://{event.bucket}/{blob_name}: {error}"
            ) from error
        return align_manifest(event, parse_manifest(content))


def build_job_catalog(settings: Settings) -> JobCatalog:
    from autocurricula.core.orchestration.manifest_inference import (
        FallbackJobCatalog,
        build_manifest_inferer,
    )

    if settings.local_mode:
        primary: JobCatalog = LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir)
    else:
        primary = GcsJobCatalog(settings=settings)
    return FallbackJobCatalog(primary, build_manifest_inferer(settings))
