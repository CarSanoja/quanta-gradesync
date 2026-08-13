import asyncio
from typing import Any

from autocurricula.config import Settings, get_storage_client
from autocurricula.core.orchestration.catalog import BatchManifest, CatalogError
from autocurricula.core.orchestration.manifest_inference import (
    DEFAULTS_NAME,
    assemble_manifest,
    ensure_lot_matches_event,
    parse_defaults,
    parse_lot_code,
)
from autocurricula.schemas.events import PubSubJobEvent


class GcsManifestInferer:
    def __init__(self, settings: Settings, storage_client: Any | None = None) -> None:
        self._client = (
            storage_client if storage_client is not None else get_storage_client()
        )
        if self._client is None:
            raise CatalogError("gcs manifest inference requires a storage client")

    async def infer_manifest(self, event: PubSubJobEvent) -> BatchManifest:
        lot = parse_lot_code(event.exam_batch_prefix)
        ensure_lot_matches_event(lot, event)
        defaults = await self._load_defaults(event)
        binding = defaults.binding_for(event.subject)
        names = await self._list_file_names(event)
        return assemble_manifest(event, binding, names)

    async def _load_defaults(self, event: PubSubJobEvent):
        def _download() -> bytes:
            return (
                self._client.bucket(event.bucket)
                .blob(DEFAULTS_NAME)
                .download_as_bytes()
            )

        try:
            content = await asyncio.to_thread(_download)
        except Exception as error:
            raise CatalogError(
                f"failed to download gs://{event.bucket}/{DEFAULTS_NAME}: {error}"
            ) from error
        return parse_defaults(content)

    async def _list_file_names(self, event: PubSubJobEvent) -> list[str]:
        prefix = event.exam_batch_prefix.rstrip("/") + "/"

        def _list() -> list[str]:
            return [
                blob.name[len(prefix) :]
                for blob in self._client.list_blobs(event.bucket, prefix=prefix)
                if "/" not in blob.name[len(prefix) :]
            ]

        try:
            return await asyncio.to_thread(_list)
        except Exception as error:
            raise CatalogError(
                f"failed to list gs://{event.bucket}/{prefix}: {error}"
            ) from error
