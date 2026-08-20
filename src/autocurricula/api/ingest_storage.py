import asyncio
import secrets
from pathlib import Path
from typing import Any, Protocol

from autocurricula.api.gcs_notification import derive_job_id
from autocurricula.config.clients import get_storage_client
from autocurricula.config.settings import Settings
from autocurricula.core.orchestration.manifest_inference import MIME_BY_EXTENSION

UPLOADS_PREFIX = "uploads/batches"
LOCAL_FALLBACK_BUCKET = "local-exams"
DEMO_SOURCE_PREFIX = "demo-source/v2/batches/2026_Matematicas_10A_Parcial1/"
DEMO_LOT_CODE = "2026_Matematicas_10A_Parcial1"
DEMO_DESTINATION_ROOT = "demo"
DEMO_RUN_HEX_BYTES = 4
GCS_PRECONDITION_FAILED = 412


class IngestCollision(Exception):
    def __init__(self, object_name: str) -> None:
        super().__init__(f"object {object_name!r} already exists")
        self.object_name = object_name


class IngestUnavailable(Exception):
    pass


def ingest_bucket(settings: Settings) -> str:
    return settings.gcs_bucket or LOCAL_FALLBACK_BUCKET


def upload_object_name(lot_code: str, file_name: str) -> str:
    return f"{UPLOADS_PREFIX}/{lot_code}/{file_name}"


class IngestStorage(Protocol):
    async def store(
        self, object_name: str, payload: bytes, content_type: str, overwrite: bool
    ) -> str: ...

    async def count_objects(self, prefix: str) -> int: ...


class LocalIngestStorage:
    def __init__(self, settings: Settings) -> None:
        self._bucket = ingest_bucket(settings)
        self._root = Path(settings.gcs_local_staging_dir) / self._bucket

    async def store(
        self, object_name: str, payload: bytes, content_type: str, overwrite: bool
    ) -> str:
        target = self._root / object_name

        def _write() -> None:
            if target.exists() and not overwrite:
                raise IngestCollision(object_name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        await asyncio.to_thread(_write)
        return self._bucket

    async def count_objects(self, prefix: str) -> int:
        directory = self._root / prefix

        def _count() -> int:
            if not directory.is_dir():
                return 0
            return sum(1 for path in directory.iterdir() if path.is_file())

        return await asyncio.to_thread(_count)


class GcsIngestStorage:
    def __init__(self, settings: Settings, client: Any | None = None) -> None:
        self._bucket_name = settings.gcs_bucket
        self._client = client if client is not None else get_storage_client()
        if self._client is None or not self._bucket_name:
            raise IngestUnavailable(
                "gcs ingest requires a storage client and a configured bucket"
            )

    async def store(
        self, object_name: str, payload: bytes, content_type: str, overwrite: bool
    ) -> str:
        def _upload() -> None:
            blob = self._client.bucket(self._bucket_name).blob(object_name)
            if overwrite:
                blob.upload_from_string(payload, content_type=content_type)
                return
            try:
                blob.upload_from_string(
                    payload, content_type=content_type, if_generation_match=0
                )
            except Exception as error:
                if getattr(error, "code", None) == GCS_PRECONDITION_FAILED:
                    raise IngestCollision(object_name) from error
                raise

        await asyncio.to_thread(_upload)
        return self._bucket_name

    async def count_objects(self, prefix: str) -> int:
        def _count() -> int:
            blobs = self._client.list_blobs(self._bucket_name, prefix=prefix)
            return sum(1 for _ in blobs)

        return await asyncio.to_thread(_count)


def build_ingest_storage(settings: Settings) -> IngestStorage:
    if settings.local_mode:
        return LocalIngestStorage(settings)
    return GcsIngestStorage(settings)


async def copy_sample_batch(
    settings: Settings, client: Any | None = None
) -> dict[str, Any]:
    active = client if client is not None else get_storage_client()
    if active is None or not settings.gcs_bucket:
        raise IngestUnavailable(
            "sample batch copy requires a storage client and a configured bucket"
        )
    run_id = secrets.token_hex(DEMO_RUN_HEX_BYTES)
    destination_prefix = (
        f"{DEMO_DESTINATION_ROOT}/{run_id}/batches/{DEMO_LOT_CODE}/"
    )

    def _copy() -> list[str]:
        bucket = active.bucket(settings.gcs_bucket)
        copied: list[str] = []
        for blob in active.list_blobs(settings.gcs_bucket, prefix=DEMO_SOURCE_PREFIX):
            file_name = blob.name.rsplit("/", 1)[-1]
            if not file_name or Path(file_name).suffix.lower() not in MIME_BY_EXTENSION:
                continue
            destination = f"{destination_prefix}{file_name}"
            bucket.copy_blob(blob, bucket, destination)
            copied.append(destination)
        return copied

    copied = await asyncio.to_thread(_copy)
    if not copied:
        raise IngestUnavailable(
            f"demo source prefix {DEMO_SOURCE_PREFIX!r} holds no gradable objects"
        )
    return {
        "status": "copied",
        "bucket": settings.gcs_bucket,
        "destination_prefix": destination_prefix,
        "expected_job_id": derive_job_id(destination_prefix.rstrip("/")),
        "objects": sorted(copied),
        "count": len(copied),
    }
