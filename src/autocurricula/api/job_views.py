from typing import Any

from pydantic import BaseModel, Field, ValidationError

from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.context import (
    PIPELINE_STAGE_ORDER,
    STAGE_FETCH,
    STAGE_GRADE,
    STAGE_SYNC,
    FetchOutputs,
)
from autocurricula.core.orchestration.job_state import JobRecord
from autocurricula.schemas.common import StrictBaseModel, TzAwareDatetime
from autocurricula.schemas.grading import GradingBatchResult, GradingResult
from autocurricula.schemas.review import build_review_id
from autocurricula.schemas.rubric import Rubric
from autocurricula.schemas.sis_sync import SISWriteResult
from autocurricula.tools.sis_connector import SUCCESS_STATUSES

STATUS_PENDING = "pending"
SIS_STATUS_QUARANTINED = "quarantined"
SIS_STATUS_SYNCED = "synced"
SIS_STATUS_FAILED = "failed"

class JobStageView(StrictBaseModel):
    name: str
    status: str


class JobSummary(StrictBaseModel):
    job_id: str
    stage: str
    subject: str
    class_id: str
    bucket: str
    exam_batch_prefix: str
    trace_id: str
    triggered_at: TzAwareDatetime
    updated_at: TzAwareDatetime
    error: str | None = None
    stages: list[JobStageView] = Field(default_factory=list)


class JobCriterionView(StrictBaseModel):
    criterion_id: str
    score: float
    max_score: float | None = None
    confidence: float
    comment: str
    evidence_count: int = Field(ge=0)


class JobStudentView(StrictBaseModel):
    student_id: str
    submission_id: str
    percentage: float | None = None
    total_score: float | None = None
    sis_status: str
    review_id: str
    document_paths: list[str] = Field(default_factory=list)
    criteria: list[JobCriterionView] = Field(default_factory=list)


class JobDetail(StrictBaseModel):
    job: JobSummary
    submission_count: int = Field(ge=0)
    graded_count: int = Field(ge=0)
    synced_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    quarantined_count: int = Field(ge=0)
    students: list[JobStudentView] = Field(default_factory=list)


def as_model[Model: BaseModel](raw: Any, model: type[Model]) -> Model | None:
    if raw is None:
        return None
    try:
        return model.model_validate(raw)
    except ValidationError:
        return None


def build_summary(record: JobRecord) -> JobSummary:
    stages = [
        JobStageView(name=name, status=record.stage_statuses.get(name, STATUS_PENDING))
        for name in PIPELINE_STAGE_ORDER
    ]
    return JobSummary(
        job_id=record.job_id,
        stage=record.stage.value,
        subject=record.event.subject,
        class_id=record.event.class_id,
        bucket=record.event.bucket,
        exam_batch_prefix=record.event.exam_batch_prefix,
        trace_id=record.event.trace_id,
        triggered_at=record.event.triggered_at,
        updated_at=record.updated_at,
        error=record.error,
        stages=stages,
    )


def _sis_status(student_id: str, sync: SISWriteResult | None) -> str:
    if sync is None:
        return STATUS_PENDING
    written = sync.per_record_statuses.get(student_id)
    if written is None:
        return SIS_STATUS_QUARANTINED
    if written in SUCCESS_STATUSES:
        return SIS_STATUS_SYNCED
    return SIS_STATUS_FAILED


def build_criteria(
    result: GradingResult | None, rubric: Rubric | None
) -> list[JobCriterionView]:
    if result is None:
        return []
    ceilings = (
        {criterion.criterion_id: criterion.max_score for criterion in rubric.criteria}
        if rubric is not None
        else {}
    )
    return [
        JobCriterionView(
            criterion_id=criterion.criterion_id,
            score=criterion.score,
            max_score=ceilings.get(criterion.criterion_id),
            confidence=criterion.confidence,
            comment=criterion.comment,
            evidence_count=len(criterion.evidence),
        )
        for criterion in result.criterion_scores
    ]


def build_students(
    fetch: FetchOutputs | None,
    grades: GradingBatchResult | None,
    sync: SISWriteResult | None,
    job_id: str,
) -> list[JobStudentView]:
    if fetch is None:
        return []
    scored = {result.submission_id: result for result in (grades.results if grades else [])}
    students: list[JobStudentView] = []
    for submission in fetch.batch.submissions:
        result = scored.get(submission.submission_id)
        students.append(
            JobStudentView(
                student_id=submission.student_id,
                submission_id=submission.submission_id,
                percentage=result.percentage if result is not None else None,
                total_score=result.total_score if result is not None else None,
                sis_status=_sis_status(submission.student_id, sync),
                review_id=build_review_id(job_id, submission.student_id),
                document_paths=[file.gcs_uri for file in submission.files],
                criteria=build_criteria(result, fetch.rubric),
            )
        )
    return students


def build_detail(record: JobRecord, state: SessionState | None) -> JobDetail:
    results = state.stage_results if state is not None else {}
    fetch = as_model(results.get(STAGE_FETCH), FetchOutputs)
    grades = as_model(results.get(STAGE_GRADE), GradingBatchResult)
    sync = as_model(results.get(STAGE_SYNC), SISWriteResult)
    students = build_students(fetch, grades, sync, record.job_id)
    return JobDetail(
        job=build_summary(record),
        submission_count=len(fetch.batch.submissions) if fetch is not None else 0,
        graded_count=len(grades.results) if grades is not None else 0,
        synced_count=sync.succeeded_count if sync is not None else 0,
        failed_count=sync.failed_count if sync is not None else 0,
        quarantined_count=(
            sync.quarantined_count
            if sync is not None
            else sum(1 for student in students if student.sis_status == SIS_STATUS_QUARANTINED)
        ),
        students=students,
    )


def apply_review_decisions(detail: JobDetail, decisions: dict[str, str]) -> JobDetail:
    if not decisions:
        return detail
    students = [
        student.model_copy(update={"sis_status": decisions[student.review_id]})
        if student.sis_status == SIS_STATUS_QUARANTINED and student.review_id in decisions
        else student
        for student in detail.students
    ]
    return detail.model_copy(update={"students": students})
