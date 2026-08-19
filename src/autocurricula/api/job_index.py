import asyncio
from pathlib import Path

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.core.orchestration.job_state import STATE_FILE_SUFFIX, JobRecord

JOBS_DIRECTORY = "jobs"
SESSION_DOCUMENT_SUFFIX = "::session"


def jobs_directory(settings: Settings) -> Path:
    return Path(settings.local_data_dir) / JOBS_DIRECTORY


def parse_record(payload: str) -> JobRecord | None:
    try:
        return JobRecord.model_validate_json(payload)
    except ValueError:
        return None


def read_local_records(settings: Settings) -> list[JobRecord]:
    directory = jobs_directory(settings)
    if not directory.is_dir():
        return []
    records: list[JobRecord] = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith(STATE_FILE_SUFFIX):
            continue
        try:
            payload = path.read_text(encoding="utf-8")
        except OSError:
            continue
        record = parse_record(payload)
        if record is not None:
            records.append(record)
    return records


def read_remote_records(settings: Settings) -> list[JobRecord]:
    client = get_firestore_client()
    if client is None:
        return []
    records: list[JobRecord] = []
    for document in client.collection(settings.firestore_checkpoints_collection).stream():
        if document.id.endswith(SESSION_DOCUMENT_SUFFIX):
            continue
        try:
            records.append(JobRecord.model_validate(document.to_dict()))
        except ValueError:
            continue
    return records


async def list_job_records(settings: Settings) -> list[JobRecord]:
    reader = read_local_records if settings.local_mode else read_remote_records
    records = await asyncio.to_thread(reader, settings)
    return sorted(
        records, key=lambda record: (record.updated_at, record.job_id), reverse=True
    )
