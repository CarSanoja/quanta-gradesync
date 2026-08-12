import asyncio
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.metrics import OptimizerReport

VARIANT_KEY_SEPARATOR = "::"


@runtime_checkable
class PromptVariantStore(Protocol):
    async def append(self, variant: PromptVariant, report: OptimizerReport) -> None: ...

    async def list_variants(self, variant_id: str) -> list[PromptVariant]: ...


def variant_document_id(variant_id: str, version: int) -> str:
    return f"{variant_id}{VARIANT_KEY_SEPARATOR}{version}"


def _record(variant: PromptVariant, report: OptimizerReport) -> dict[str, Any]:
    return {
        "recorded_at": utc_now().isoformat(),
        "variant_id": variant.variant_id,
        "version": variant.version,
        "variant": variant.to_dict(),
        "report": report.model_dump(mode="json"),
    }


class LocalPromptVariantStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = Path(data_dir) / "prompts" / "optimizer.jsonl"
        self._lock = asyncio.Lock()

    async def append(self, variant: PromptVariant, report: OptimizerReport) -> None:
        line = json.dumps(_record(variant, report), ensure_ascii=False, sort_keys=True)
        async with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    async def list_variants(self, variant_id: str) -> list[PromptVariant]:
        if not self._path.exists():
            return []
        content = await asyncio.to_thread(self._path.read_text, "utf-8")
        variants: list[PromptVariant] = []
        for line in content.splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            variant = PromptVariant.from_dict(record["variant"])
            if variant.variant_id == variant_id:
                variants.append(variant)
        return sorted(variants, key=lambda item: item.version)


class FirestorePromptVariantStore:
    def __init__(self, client: Any, collection: str) -> None:
        if client is None:
            raise ValueError(
                "FirestorePromptVariantStore requires a Firestore client; "
                "set GRADESYNC_GCP_PROJECT_ID or keep local_mode enabled"
            )
        self._client = client
        self._collection = collection

    async def append(self, variant: PromptVariant, report: OptimizerReport) -> None:
        payload = _record(variant, report)
        document_id = variant_document_id(variant.variant_id, variant.version)

        def _write() -> None:
            self._client.collection(self._collection).document(document_id).set(payload)

        await asyncio.to_thread(_write)

    async def list_variants(self, variant_id: str) -> list[PromptVariant]:
        def _read() -> list[dict[str, Any]]:
            return [
                document.to_dict()
                for document in self._client.collection(self._collection).stream()
            ]

        records = await asyncio.to_thread(_read)
        variants = [
            PromptVariant.from_dict(record["variant"])
            for record in records
            if record.get("variant_id") == variant_id
        ]
        return sorted(variants, key=lambda item: item.version)


def build_prompt_variant_store(settings: Settings) -> PromptVariantStore:
    if settings.local_mode:
        return LocalPromptVariantStore(settings.local_data_dir)
    return FirestorePromptVariantStore(
        client=get_firestore_client(),
        collection=settings.firestore_prompts_collection,
    )
