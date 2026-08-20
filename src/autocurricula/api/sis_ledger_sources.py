import asyncio
import json
from pathlib import Path
from typing import Any

from autocurricula.api.dependencies import AppContainer
from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.sis_sync import SISGradeRecord
from autocurricula.tools.sis_firestore import (
    SIS_RECORDS_COLLECTION,
    build_ledger_document,
    criteria_by_student,
    term_from_prefix,
)

SIS_WRITES_FILE = "sis_writes.jsonl"
FIELD_JOB_ID = "job_id"
FIELD_WRITTEN_AT = "written_at"
DESCENDING = "DESCENDING"


def _written_at(document: dict[str, Any]) -> str:
    return str(document.get(FIELD_WRITTEN_AT) or "")


def read_local_events(settings: Settings) -> list[dict[str, Any]]:
    path = Path(settings.local_data_dir) / SIS_WRITES_FILE
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


async def _job_context(container: AppContainer, job_id: str) -> dict[str, Any]:
    context: dict[str, Any] = {"class_id": "", "term": "", "criteria": {}}
    try:
        record = await container.checkpoint_store.get(job_id)
    except Exception:
        record = None
    if record is not None:
        context["class_id"] = record.event.class_id
        context["term"] = term_from_prefix(record.event.exam_batch_prefix)
    try:
        state = await container.checkpoint_store.load_state(job_id)
    except Exception:
        state = None
    if state is not None:
        context["criteria"] = criteria_by_student(state.stage_results)
    return context


async def read_local_documents(
    container: AppContainer, job_id: str | None, limit: int
) -> list[dict[str, Any]]:
    events = await asyncio.to_thread(read_local_events, container.settings)
    contexts: dict[str, dict[str, Any]] = {}
    documents: list[dict[str, Any]] = []
    for event in events:
        request = event.get("request") or {}
        event_job_id = str(request.get("job_id") or "")
        if not event_job_id or (job_id is not None and event_job_id != job_id):
            continue
        if event_job_id not in contexts:
            contexts[event_job_id] = await _job_context(container, event_job_id)
        for raw in request.get("records") or []:
            try:
                record = SISGradeRecord.model_validate(raw)
            except ValueError:
                continue
            documents.append(
                build_ledger_document(
                    event_job_id,
                    record,
                    contexts[event_job_id],
                    str(event.get(FIELD_WRITTEN_AT) or ""),
                )
            )
    documents.sort(key=_written_at, reverse=True)
    return documents[:limit]


def _job_filtered(query: Any, job_id: str) -> Any:
    try:
        from google.cloud.firestore_v1 import FieldFilter
    except ImportError:
        return query.where(FIELD_JOB_ID, "==", job_id)
    return query.where(filter=FieldFilter(FIELD_JOB_ID, "==", job_id))


def read_remote_documents(
    settings: Settings,
    job_id: str | None,
    limit: int,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    active = client if client is not None else get_firestore_client()
    if active is None:
        raise RuntimeError("sis ledger reads require a configured firestore client")
    collection = active.collection(SIS_RECORDS_COLLECTION)
    if job_id is not None:
        snapshots = _job_filtered(collection, job_id).stream()
    else:
        snapshots = (
            collection.order_by(FIELD_WRITTEN_AT, direction=DESCENDING)
            .limit(limit)
            .stream()
        )
    documents = [
        payload
        for snapshot in snapshots
        if isinstance(payload := snapshot.to_dict(), dict)
    ]
    documents.sort(key=_written_at, reverse=True)
    return documents[:limit]
