import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field

from autocurricula.api.dependencies import AppContainer, get_container
from autocurricula.api.sis_ledger_sources import (
    read_local_documents,
    read_remote_documents,
)
from autocurricula.api.webhooks import require_push_token
from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.labels import LabelDecision
from autocurricula.tools.sis_firestore import criteria_by_student

sis_router = APIRouter(tags=["sis"])

DEFAULT_RECORD_LIMIT = 50
MAX_RECORD_LIMIT = 200

SOURCE_LOCAL = "local"
SOURCE_FIRESTORE = "firestore"


class SISCriterionScoreView(StrictBaseModel):
    criterion_id: str
    title: str | None = None
    score: float | None = None
    confidence: float | None = None


class SISRecordView(StrictBaseModel):
    job_id: str
    student_id: str
    subject: str
    class_id: str = ""
    term: str = ""
    total_score: float | None = None
    percentage: float | None = None
    competency_codes: list[str] = Field(default_factory=list)
    criterion_scores: list[SISCriterionScoreView] = Field(default_factory=list)
    prompt_variant_id: str | None = None
    graded_at: str | None = None
    written_at: str = ""


class SISRecordsResponse(StrictBaseModel):
    items: list[SISRecordView] = Field(default_factory=list)
    count: int = Field(ge=0)
    source: str


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _criterion_views(raw: Any) -> list[SISCriterionScoreView]:
    if not isinstance(raw, list):
        return []
    views: list[SISCriterionScoreView] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        views.append(
            SISCriterionScoreView(
                criterion_id=str(entry.get("criterion_id") or ""),
                title=str(entry.get("title")) if entry.get("title") else None,
                score=_as_float(entry.get("score")),
                confidence=_as_float(entry.get("confidence")),
            )
        )
    return views


def record_view_from_document(document: dict[str, Any]) -> SISRecordView:
    provenance = document.get("provenance")
    prompt_variant_id = (
        str(provenance.get("prompt_variant_id"))
        if isinstance(provenance, dict) and provenance.get("prompt_variant_id")
        else None
    )
    return SISRecordView(
        job_id=str(document.get("job_id") or ""),
        student_id=str(document.get("student_id") or ""),
        subject=str(document.get("subject") or ""),
        class_id=str(document.get("class_id") or ""),
        term=str(document.get("term") or ""),
        total_score=_as_float(document.get("total_score")),
        percentage=_as_float(document.get("percentage")),
        competency_codes=[str(code) for code in document.get("competency_codes") or []],
        criterion_scores=_criterion_views(document.get("criterion_scores")),
        prompt_variant_id=prompt_variant_id,
        graded_at=str(document.get("graded_at")) if document.get("graded_at") else None,
        written_at=str(document.get("written_at") or ""),
    )



async def _enrich_criteria(
    container: AppContainer, documents: list[dict[str, Any]]
) -> None:
    by_job: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        job_id = str(document.get("job_id") or "")
        if job_id:
            by_job.setdefault(job_id, []).append(document)
    for job_id, job_documents in by_job.items():
        try:
            state = await container.checkpoint_store.load_state(job_id)
        except Exception:
            state = None
        machine = criteria_by_student(state.stage_results) if state is not None else {}
        try:
            labels = await container.review_service.label_store.list_labels(
                job_id=job_id, limit=1000
            )
        except Exception:
            labels = []
        decisions = {
            label.student_id: label
            for label in labels
            if label.decision in {LabelDecision.APPROVE, LabelDecision.OVERRIDE}
        }
        for document in job_documents:
            student_id = str(document.get("student_id") or "")
            base = machine.get(student_id) or document.get("criterion_scores") or []
            label = decisions.get(student_id)
            if label is None or not label.scores:
                document["criterion_scores"] = base
                continue
            indexed = {str(row.get("criterion_id") or ""): row for row in base}
            document["criterion_scores"] = [
                {
                    "criterion_id": score.criterion_id,
                    "title": str(indexed.get(score.criterion_id, {}).get("title") or ""),
                    "score": (
                        score.human_score
                        if score.human_score is not None
                        else score.machine_score
                    ),
                    "confidence": indexed.get(score.criterion_id, {}).get("confidence"),
                }
                for score in label.scores
            ]
@sis_router.get(
    "/sis/records",
    response_model=SISRecordsResponse,
    response_model_exclude_none=True,
)
async def list_sis_records(
    request: Request,
    job_id: str | None = Query(default=None),
    student_id: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=DEFAULT_RECORD_LIMIT, ge=1, le=MAX_RECORD_LIMIT),
    container: AppContainer = Depends(get_container),
) -> SISRecordsResponse:
    require_push_token(request, container.settings.pubsub_push_token)
    try:
        if container.settings.local_mode:
            source = SOURCE_LOCAL
            documents = await read_local_documents(
                container, job_id, limit, student_id
            )
        else:
            source = SOURCE_FIRESTORE
            documents = await asyncio.to_thread(
                read_remote_documents,
                container.settings,
                job_id,
                limit,
                student_id,
            )
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"sis ledger unavailable: {error}",
        ) from error
    await _enrich_criteria(container, documents)
    items = [record_view_from_document(document) for document in documents]
    return SISRecordsResponse(items=items, count=len(items), source=source)
