import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol

import httpx

from autocurricula.config import Settings
from autocurricula.core.fleet.credentials import (
    sis_writer_authorization,
    sis_writer_firestore_client,
)
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.sis_sync import SISWriteRequest, SISWriteResult

logger = logging.getLogger(__name__)

SUCCESS_STATUSES = frozenset({"ok", "success", "written", "accepted"})
MAX_ATTEMPTS = 3
RETRY_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})
BACKOFF_BASE_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30.0


class SisWriteError(Exception):
    pass


class SISConnector(Protocol):
    async def write_grades(self, request: SISWriteRequest) -> SISWriteResult: ...


class HttpSISConnector:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        self._url = f"{settings.sis_base_url.rstrip('/')}/grades"
        self._token = settings.sis_api_token
        self._client = client if client is not None else httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        self._owns_client = client is None

    async def write_grades(self, request: SISWriteRequest) -> SISWriteResult:
        authorization = await asyncio.to_thread(
            sis_writer_authorization, self._settings, self._token
        )
        headers = {"Authorization": authorization}
        body = request.model_dump(mode="json")
        last_error = "sis write failed"
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await self._client.post(self._url, json=body, headers=headers)
            except httpx.HTTPError as error:
                last_error = f"{type(error).__name__}: {error}"
                await self._sleep_backoff(attempt)
                continue
            if (
                response.status_code in RETRY_STATUS_CODES
                and attempt < MAX_ATTEMPTS - 1
            ):
                last_error = f"sis returned retryable status {response.status_code}"
                await self._sleep_backoff(attempt)
                continue
            return self._result_from_response(request, response)
        raise SisWriteError(last_error)

    @staticmethod
    async def _sleep_backoff(attempt: int) -> None:
        await asyncio.sleep(BACKOFF_BASE_SECONDS * (2**attempt))

    @staticmethod
    def _result_from_response(
        request: SISWriteRequest, response: httpx.Response
    ) -> SISWriteResult:
        if not 200 <= response.status_code < 300:
            suffix = f"error:HTTP_{response.status_code}"
            statuses = {
                record.student_id: suffix for record in request.records
            }
        else:
            reported = HttpSISConnector._parse_statuses(response)
            statuses = {
                record.student_id: reported.get(record.student_id, "ok")
                for record in request.records
            }
        succeeded = sum(1 for status in statuses.values() if status in SUCCESS_STATUSES)
        return SISWriteResult(
            job_id=request.job_id,
            per_record_statuses=statuses,
            succeeded_count=succeeded,
            failed_count=len(statuses) - succeeded,
        )

    @staticmethod
    def _parse_statuses(response: httpx.Response) -> dict[str, str]:
        try:
            payload = response.json()
        except ValueError:
            return {}
        raw = payload.get("statuses", {}) if isinstance(payload, dict) else {}
        return {str(key): str(value) for key, value in raw.items()}

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class LocalSISConnector:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "sis_writes.jsonl"

    async def write_grades(self, request: SISWriteRequest) -> SISWriteResult:
        event = {
            "written_at": utc_now().isoformat(),
            "request": request.model_dump(mode="json"),
        }
        await asyncio.to_thread(self._append_event, event)
        statuses = {record.student_id: "ok" for record in request.records}
        return SISWriteResult(
            job_id=request.job_id,
            per_record_statuses=statuses,
            succeeded_count=len(statuses),
            failed_count=0,
        )

    def _append_event(self, event: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")


def build_sis_connector(settings: Settings) -> SISConnector:
    if settings.local_mode:
        return LocalSISConnector(data_dir=settings.local_data_dir)
    if not settings.sis_base_url:
        from autocurricula.tools.sis_firestore import FirestoreSISConnector

        logger.info(
            "sis_base_url is empty in gcp mode; grade writes go to the firestore "
            "sis ledger collection"
        )
        return FirestoreSISConnector(
            settings=settings, client=sis_writer_firestore_client(settings)
        )
    return HttpSISConnector(settings=settings)
