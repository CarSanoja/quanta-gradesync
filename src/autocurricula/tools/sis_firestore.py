import asyncio
import logging
from typing import Any
from urllib.parse import quote

from autocurricula.config.clients import get_firestore_client
from autocurricula.config.settings import Settings
from autocurricula.core.orchestration.manifest_inference import parse_lot_code
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteRequest, SISWriteResult

logger = logging.getLogger(__name__)

SIS_RECORDS_COLLECTION = "sis_records"
SESSION_DOCUMENT_SUFFIX = "::session"
STAGE_FETCH_KEY = "fetch"
STAGE_GRADE_KEY = "grade"


def sis_document_id(job_id: str, student_id: str) -> str:
    return f"{quote(job_id, safe='')}__{quote(student_id, safe='')}"


def term_from_prefix(prefix: str) -> str:
    try:
        return parse_lot_code(prefix).assessment
    except Exception:
        return ""


def criteria_by_student(stage_results: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    fetch = stage_results.get(STAGE_FETCH_KEY) or {}
    grade = stage_results.get(STAGE_GRADE_KEY) or {}
    submissions = (fetch.get("batch") or {}).get("submissions") or []
    student_by_submission = {
        submission.get("submission_id"): submission.get("student_id")
        for submission in submissions
        if isinstance(submission, dict)
    }
    criteria: dict[str, list[dict[str, Any]]] = {}
    for result in grade.get("results") or []:
        if not isinstance(result, dict):
            continue
        student_id = student_by_submission.get(result.get("submission_id"))
        if not student_id:
            continue
        rows = criteria.setdefault(str(student_id), [])
        for score in result.get("criterion_scores") or []:
            if not isinstance(score, dict):
                continue
            rows.append(
                {
                    "criterion_id": str(score.get("criterion_id", "")),
                    "score": score.get("score"),
                    "confidence": score.get("confidence"),
                }
            )
    return criteria


def build_ledger_document(
    job_id: str,
    record: SISGradeRecord,
    context: dict[str, Any],
    written_at: str,
) -> dict[str, Any]:
    payload = record.model_dump(mode="json")
    criteria = context.get("criteria") or {}
    return {
        "job_id": job_id,
        "student_id": record.student_id,
        "subject": record.subject,
        "class_id": str(context.get("class_id") or ""),
        "term": str(context.get("term") or ""),
        "total_score": record.score,
        "percentage": record.percentage,
        "feedback": record.feedback,
        "competency_codes": list(record.competency_codes),
        "criterion_scores": criteria.get(record.student_id, []),
        "provenance": payload.get("provenance"),
        "graded_at": payload.get("graded_at"),
        "written_at": written_at,
    }


class FirestoreSISConnector:
    def __init__(
        self,
        settings: Settings,
        client: Any | None = None,
        collection: str = SIS_RECORDS_COLLECTION,
    ) -> None:
        self._client = client if client is not None else get_firestore_client()
        if self._client is None:
            raise RuntimeError("firestore sis connector requires a configured client")
        self._collection = collection
        self._checkpoints_collection = settings.firestore_checkpoints_collection

    async def write_grades(self, request: SISWriteRequest) -> SISWriteResult:
        context = await asyncio.to_thread(self._job_context, request.job_id)
        written_at = utc_now().isoformat()

        def _write() -> None:
            target = self._client.collection(self._collection)
            for record in request.records:
                document_id = sis_document_id(request.job_id, record.student_id)
                target.document(document_id).set(
                    build_ledger_document(request.job_id, record, context, written_at)
                )

        await asyncio.to_thread(_write)
        statuses = {record.student_id: "ok" for record in request.records}
        return SISWriteResult(
            job_id=request.job_id,
            per_record_statuses=statuses,
            succeeded_count=len(statuses),
            failed_count=0,
        )

    def _job_context(self, job_id: str) -> dict[str, Any]:
        context: dict[str, Any] = {"class_id": "", "term": "", "criteria": {}}
        try:
            checkpoints = self._client.collection(self._checkpoints_collection)
            record_document = checkpoints.document(job_id).get()
            if getattr(record_document, "exists", False):
                event = (record_document.to_dict() or {}).get("event") or {}
                context["class_id"] = str(event.get("class_id") or "")
                context["term"] = term_from_prefix(str(event.get("exam_batch_prefix") or ""))
            state_document = checkpoints.document(
                f"{job_id}{SESSION_DOCUMENT_SUFFIX}"
            ).get()
            if getattr(state_document, "exists", False):
                stage_results = (state_document.to_dict() or {}).get("stage_results") or {}
                context["criteria"] = criteria_by_student(stage_results)
        except Exception as error:
            logger.warning(
                "sis ledger enrichment failed for job %s: %s", job_id, error
            )
        return context
