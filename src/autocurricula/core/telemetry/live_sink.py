import json
import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.live_events import (
    LIVE_SUBCOLLECTION,
    LiveEvent,
    LiveEventKind,
    LiveEventStatus,
    event_document_id,
)

logger = logging.getLogger(__name__)

LIVE_DIRECTORY = "live"


@runtime_checkable
class LiveSink(Protocol):
    def emit(self, event: LiveEvent) -> None: ...

    def flush(self, timeout: float = 5.0) -> None: ...


def log_live_event(event: LiveEvent) -> None:
    if event.kind is not LiveEventKind.LLM_CALL and event.status is not LiveEventStatus.ERROR:
        return
    fields: dict[str, Any] = {
        "kind": event.kind.value,
        "name": event.name,
        "status": event.status.value,
        "job_id": event.job_id,
        "trace_id": event.trace_id,
        "agent_id": event.agent_id or "",
        "stage": event.stage or "",
    }
    if event.llm is not None:
        fields["model"] = event.llm.model
        fields["input_tokens"] = event.llm.input_tokens
        fields["output_tokens"] = event.llm.output_tokens
        fields["total_tokens"] = event.llm.total_tokens
    logger.info("live_event", extra={"json_fields": fields})


class NullLiveSink:
    def emit(self, event: LiveEvent) -> None:
        return None

    def flush(self, timeout: float = 5.0) -> None:
        return None


class QueuedLiveSink:
    def __init__(self, worker_name: str) -> None:
        self._worker_name = worker_name
        self._queue: queue.Queue[LiveEvent] = queue.Queue()
        self._worker: threading.Thread | None = None
        self._start_lock = threading.Lock()

    def emit(self, event: LiveEvent) -> None:
        try:
            self._ensure_worker()
            self._queue.put_nowait(event)
        except Exception as error:
            logger.warning("live event enqueue failed for job %s: %s", event.job_id, error)
        log_live_event(event)

    def flush(self, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + max(timeout, 0.0)
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return
                self._queue.all_tasks_done.wait(remaining)

    def _ensure_worker(self) -> None:
        with self._start_lock:
            if self._worker is not None:
                return
            self._worker = threading.Thread(
                target=self._drain, name=self._worker_name, daemon=True
            )
            self._worker.start()

    def _drain(self) -> None:
        while True:
            event = self._queue.get()
            try:
                self._write(event)
            except Exception as error:
                logger.warning("live event write failed for job %s: %s", event.job_id, error)
            finally:
                self._queue.task_done()

    def _write(self, event: LiveEvent) -> None:
        raise NotImplementedError


class LocalLiveSink(QueuedLiveSink):
    def __init__(self, data_dir: Path) -> None:
        super().__init__("autocurricula-live-local")
        self._dir = Path(data_dir) / LIVE_DIRECTORY

    def _write(self, event: LiveEvent) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.model_dump(mode="json"), sort_keys=True)
        path = self._dir / f"{event.job_id}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


class FirestoreLiveSink(QueuedLiveSink):
    def __init__(self, collection: str, client: Any | None = None) -> None:
        super().__init__("autocurricula-live-sink")
        self._collection = collection
        self._client = client if client is not None else get_firestore_client()
        if self._client is None:
            raise RuntimeError("firestore live sink requires a configured client")

    def _write(self, event: LiveEvent) -> None:
        self._client.collection(self._collection).document(event.job_id).collection(
            LIVE_SUBCOLLECTION
        ).document(event_document_id(event.seq)).set(event.model_dump(mode="json"))


def build_live_sink(settings: Settings) -> LiveSink:
    if not settings.telemetry_live_enabled:
        return NullLiveSink()
    if settings.local_mode:
        return LocalLiveSink(settings.local_data_dir)
    return FirestoreLiveSink(settings.firestore_audit_collection)
