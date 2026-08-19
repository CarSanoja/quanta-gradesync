import asyncio
import json
from pathlib import Path
from typing import Any

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings

PROMPTS_DIRECTORY = "prompts"
HISTORY_FILE_NAME = "optimizer.jsonl"


def history_path(settings: Settings) -> Path:
    return Path(settings.local_data_dir) / PROMPTS_DIRECTORY / HISTORY_FILE_NAME


def read_local_history(settings: Settings) -> list[dict[str, Any]]:
    path = history_path(settings)
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records


def read_remote_history(settings: Settings) -> list[dict[str, Any]]:
    client = get_firestore_client()
    if client is None:
        return []
    records: list[dict[str, Any]] = []
    for document in client.collection(settings.firestore_prompts_collection).stream():
        payload = document.to_dict()
        if isinstance(payload, dict):
            records.append(payload)
    return records


async def list_history(settings: Settings) -> list[dict[str, Any]]:
    reader = read_local_history if settings.local_mode else read_remote_history
    records = await asyncio.to_thread(reader, settings)
    return sorted(
        records,
        key=lambda record: (str(record.get("recorded_at", "")), int(record.get("version", 0))),
    )
