import asyncio
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.telemetry import TypedSpan


@runtime_checkable
class AuditLogger(Protocol):
    async def append(
        self,
        job_id: str,
        trace_id: str,
        spans: list[TypedSpan],
        summary: dict[str, Any],
    ) -> None: ...


def audit_event(
    job_id: str,
    trace_id: str,
    spans: list[TypedSpan],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "recorded_at": utc_now().isoformat(),
        "job_id": job_id,
        "trace_id": trace_id,
        "summary": summary,
        "spans": [span.model_dump(mode="json") for span in spans],
    }


class LocalAuditLogger:
    def __init__(self, data_dir: Path) -> None:
        self._dir = Path(data_dir) / "audit"

    async def append(
        self,
        job_id: str,
        trace_id: str,
        spans: list[TypedSpan],
        summary: dict[str, Any],
    ) -> None:
        line = json.dumps(
            audit_event(job_id, trace_id, spans, summary), sort_keys=True
        )
        await asyncio.to_thread(self._append_line, job_id, line)

    def _append_line(self, job_id: str, line: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with (self._dir / f"{job_id}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class FirestoreAuditLogger:
    def __init__(self, collection: str, client: Any | None = None) -> None:
        self._collection = collection
        self._client = client if client is not None else get_firestore_client()
        if self._client is None:
            raise RuntimeError("firestore audit logger requires a configured client")

    async def append(
        self,
        job_id: str,
        trace_id: str,
        spans: list[TypedSpan],
        summary: dict[str, Any],
    ) -> None:
        payload = audit_event(job_id, trace_id, spans, summary)

        def _write() -> None:
            self._client.collection(self._collection).document(job_id).collection(
                "events"
            ).document(payload["recorded_at"]).set(payload)

        await asyncio.to_thread(_write)


def build_audit_logger(settings: Settings) -> AuditLogger:
    if settings.local_mode:
        return LocalAuditLogger(settings.local_data_dir)
    return FirestoreAuditLogger(settings.firestore_audit_collection)
