import json
from pathlib import Path
from typing import Any

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.schemas.live_events import LIVE_SUBCOLLECTION

LIVE_DIRECTORY = "live"
FIELD_SEQ = "seq"
ASCENDING = "ASCENDING"


def event_seq(event: dict[str, Any]) -> int:
    value = event.get(FIELD_SEQ)
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def read_local_live_events(
    settings: Settings, job_id: str, after: int, limit: int
) -> list[dict[str, Any]]:
    directory = (Path(settings.local_data_dir) / LIVE_DIRECTORY).resolve()
    path = (directory / f"{job_id}.jsonl").resolve()
    if not path.is_relative_to(directory) or not path.is_file():
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
        if isinstance(event, dict) and event_seq(event) > after:
            events.append(event)
    events.sort(key=event_seq)
    return events[:limit]


def _after_filtered(query: Any, after: int) -> Any:
    try:
        from google.cloud.firestore_v1 import FieldFilter
    except ImportError:
        return query.where(FIELD_SEQ, ">", after)
    return query.where(filter=FieldFilter(FIELD_SEQ, ">", after))


def read_remote_live_events(
    settings: Settings,
    job_id: str,
    after: int,
    limit: int,
    client: Any | None = None,
) -> list[dict[str, Any]]:
    active = client if client is not None else get_firestore_client()
    if active is None:
        raise RuntimeError("live feed reads require a configured firestore client")
    collection = (
        active.collection(settings.firestore_audit_collection)
        .document(job_id)
        .collection(LIVE_SUBCOLLECTION)
    )
    snapshots = (
        _after_filtered(collection, after)
        .order_by(FIELD_SEQ, direction=ASCENDING)
        .limit(limit)
        .stream()
    )
    events = [
        payload
        for snapshot in snapshots
        if isinstance(payload := snapshot.to_dict(), dict)
    ]
    events.sort(key=event_seq)
    return events[:limit]
