import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from autocurricula.api.dependencies import AppContainer
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.curriculum import Competency, CurriculumStandard
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.exam import ExamBatch, ExamFile, ExamSubmission
from autocurricula.schemas.grading import (
    CriterionScore,
    EvidenceSpan,
    GradingBatchResult,
    GradingResult,
)
from autocurricula.schemas.review import ReviewItem
from autocurricula.schemas.rubric import MasteryLevel, Rubric, RubricCriterion
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteResult

SUBJECT = "matematicas"
BUCKET = "exam-uploads"
PREFIX = "batches/2026_Matematicas_10A_Parcial1"
GRADED_AT = datetime(2026, 8, 17, 11, 0, tzinfo=UTC)
MASTERY = {level: f"{level.value} response" for level in MasteryLevel}


def make_rubric() -> Rubric:
    return Rubric(
        rubric_id="mat-10-parcial1",
        subject=SUBJECT,
        version=1,
        criteria=[
            RubricCriterion(
                criterion_id="crit-a",
                description="Factor the quadratic expression",
                weight=1.0,
                max_score=4.0,
                mastery_descriptions=MASTERY,
            )
        ],
    )


def make_standard() -> CurriculumStandard:
    return CurriculumStandard(
        country="CO",
        version="2026",
        competencies=[
            Competency(
                code="MAT.10.1",
                description="Factors quadratic expressions",
                grade_level="10",
                subject=SUBJECT,
            )
        ],
    )


def make_batch(job_id: str) -> ExamBatch:
    return ExamBatch(
        job_id=job_id,
        class_id="10A",
        subject=SUBJECT,
        grade_level="10",
        rubric_id="mat-10-parcial1",
        submissions=[
            ExamSubmission(
                submission_id="ana-torres",
                student_id="ana-torres",
                files=[
                    ExamFile(
                        gcs_uri=f"gs://{BUCKET}/{PREFIX}/ana-torres.jpg",
                        mime_type="image/jpeg",
                        page_count=1,
                    )
                ],
            )
        ],
    )


def make_state(job_id: str) -> SessionState:
    grades = GradingBatchResult(
        job_id=job_id,
        results=[
            GradingResult(
                submission_id="ana-torres",
                criterion_scores=[
                    CriterionScore(
                        criterion_id="crit-a",
                        score=2.0,
                        comment="Partial factoring with an unreadable final step",
                        evidence=[
                            EvidenceSpan(
                                page=1,
                                quote="(x + 3)(x - ?)",
                                rationale="Second factor is illegible",
                            )
                        ],
                        confidence=0.62,
                    )
                ],
                total_score=2.0,
                percentage=50.0,
                feedback="Review the factoring of the independent term.",
            )
        ],
        graded_at=GRADED_AT,
        model_id="gemini-3.5-flash",
    )
    sync = SISWriteResult(
        job_id=job_id,
        per_record_statuses={},
        succeeded_count=0,
        failed_count=0,
        quarantined_count=1,
    )
    return SessionState(
        job_id=job_id,
        stage_results={
            "fetch": {
                "batch": make_batch(job_id).model_dump(mode="json"),
                "rubric": make_rubric().model_dump(mode="json"),
                "curriculum_standard": make_standard().model_dump(mode="json"),
            },
            "grade": grades.model_dump(mode="json"),
            "sync": sync.model_dump(mode="json"),
        },
        stage_statuses={
            "fetch": "succeeded",
            "grade": "succeeded",
            "audit": "succeeded",
            "risk": "succeeded",
            "sync": "succeeded",
        },
    )


def make_record(job_id: str) -> JobRecord:
    event = PubSubJobEvent(
        job_id=job_id,
        bucket=BUCKET,
        exam_batch_prefix=PREFIX,
        class_id="10A",
        subject=SUBJECT,
        triggered_at=GRADED_AT,
    )
    return JobRecord(
        job_id=job_id,
        event=event,
        stage=JobStage.SYNCED,
        stage_statuses=dict(make_state(job_id).stage_statuses),
    )


def make_review(job_id: str, document_paths: list[str]) -> ReviewItem:
    return ReviewItem(
        review_id=f"{job_id}:ana-torres",
        job_id=job_id,
        student_id="ana-torres",
        subject=SUBJECT,
        reasons=["crit-a confidence 0.620 below threshold 0.85"],
        evidence=[
            EvidenceSpan(page=1, quote="(x + 3)(x - ?)", rationale="Second factor is illegible")
        ],
        document_paths=document_paths,
        proposed_record=SISGradeRecord(
            student_id="ana-torres",
            subject=SUBJECT,
            score=2.0,
            percentage=50.0,
            feedback="Review the factoring of the independent term.",
            competency_codes=["MAT.10.1"],
            graded_at=GRADED_AT,
        ),
        created_at=utc_now(),
    )


def stage_page(container: AppContainer, name: str = "ana-torres.jpg") -> Path:
    path = Path(container.settings.gcs_local_staging_dir) / BUCKET / PREFIX / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8\xff\xdb scanned page bytes")
    return path


@pytest.fixture
async def saved_job(container: AppContainer) -> str:
    job_id = "job-console-1"
    await container.checkpoint_store.save(make_record(job_id))
    await container.checkpoint_store.save_state(job_id, make_state(job_id))
    return job_id


async def test_console_page_is_public_html(client: httpx.AsyncClient) -> None:
    response = await client.get("/console")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Operations console" in response.text


async def test_console_assets_are_served_from_a_whitelist(client: httpx.AsyncClient) -> None:
    styles = await client.get("/console/assets/console.css")
    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    script = await client.get("/console/assets/console.js")
    assert script.status_code == 200
    traversal = await client.get("/console/assets/%2e%2e%2fmain.py")
    assert traversal.status_code == 404
    unknown = await client.get("/console/assets/secrets.env")
    assert unknown.status_code == 404


async def test_jobs_endpoint_requires_the_push_token(client: httpx.AsyncClient) -> None:
    missing = await client.get("/jobs")
    assert missing.status_code == 401
    wrong = await client.get("/jobs", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 403


async def test_jobs_endpoint_starts_empty(client: httpx.AsyncClient, auth_headers) -> None:
    response = await client.get("/jobs", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}


async def test_jobs_endpoint_lists_checkpointed_stages(
    client: httpx.AsyncClient, auth_headers, saved_job: str
) -> None:
    response = await client.get("/jobs", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    job = payload["items"][0]
    assert job["job_id"] == saved_job
    assert job["stage"] == "synced"
    assert job["subject"] == SUBJECT
    stages = {stage["name"]: stage["status"] for stage in job["stages"]}
    assert stages["fetch"] == "succeeded"
    assert stages["optimize"] == "pending"


async def test_job_detail_projects_students_and_criteria(
    client: httpx.AsyncClient, auth_headers, saved_job: str
) -> None:
    response = await client.get(f"/jobs/{saved_job}", headers=auth_headers)
    assert response.status_code == 200
    detail = response.json()
    assert detail["submission_count"] == 1
    assert detail["graded_count"] == 1
    assert detail["quarantined_count"] == 1
    student = detail["students"][0]
    assert student["student_id"] == "ana-torres"
    assert student["sis_status"] == "quarantined"
    assert student["review_id"] == f"{saved_job}:ana-torres"
    criterion = student["criteria"][0]
    assert criterion["criterion_id"] == "crit-a"
    assert criterion["max_score"] == 4.0
    assert criterion["evidence_count"] == 1


async def test_job_detail_reflects_review_decisions(
    client: httpx.AsyncClient, container: AppContainer, auth_headers, saved_job: str
) -> None:
    item = make_review(saved_job, [f"gs://{BUCKET}/{PREFIX}/ana-torres.jpg"])
    await container.review_service.store.put(item)
    pending = await client.get(f"/jobs/{saved_job}", headers=auth_headers)
    assert pending.json()["students"][0]["sis_status"] == "quarantined"
    stage_page(container)
    approved = await client.post(f"/review/{item.review_id}/approve", headers=auth_headers)
    assert approved.status_code == 200
    response = await client.get(f"/jobs/{saved_job}", headers=auth_headers)
    assert response.json()["students"][0]["sis_status"] == "approved"


async def test_unknown_job_returns_404(client: httpx.AsyncClient, auth_headers) -> None:
    response = await client.get("/jobs/job-ghost", headers=auth_headers)
    assert response.status_code == 404


async def test_page_image_serves_the_staged_scan(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    stage_page(container)
    await container.review_service.store.put(
        make_review("job-img", [f"gs://{BUCKET}/{PREFIX}/ana-torres.jpg"])
    )
    response = await client.get("/review/job-img:ana-torres/page-image", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")


async def test_page_image_requires_authorization(
    client: httpx.AsyncClient, container: AppContainer
) -> None:
    stage_page(container)
    await container.review_service.store.put(
        make_review("job-img-auth", [f"gs://{BUCKET}/{PREFIX}/ana-torres.jpg"])
    )
    response = await client.get("/review/job-img-auth:ana-torres/page-image")
    assert response.status_code == 401


async def test_page_image_rejects_path_traversal(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_review("job-escape", [f"gs://{BUCKET}/../../../../etc/passwd"])
    )
    response = await client.get("/review/job-escape:ana-torres/page-image", headers=auth_headers)
    assert response.status_code == 403


async def test_page_image_rejects_absolute_paths_outside_the_data_roots(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(make_review("job-abs", ["/etc/hosts"]))
    response = await client.get("/review/job-abs:ana-torres/page-image", headers=auth_headers)
    assert response.status_code == 403


async def test_page_image_rejects_unsupported_document_types(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_review("job-type", [f"gs://{BUCKET}/{PREFIX}/notes.txt"])
    )
    response = await client.get("/review/job-type:ana-torres/page-image", headers=auth_headers)
    assert response.status_code == 403


async def test_page_image_returns_404_when_the_scan_is_missing(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_review("job-missing", [f"gs://{BUCKET}/{PREFIX}/ghost.jpg"])
    )
    response = await client.get("/review/job-missing:ana-torres/page-image", headers=auth_headers)
    assert response.status_code == 404


async def test_page_image_returns_404_for_unknown_review(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get("/review/job-x:ghost/page-image", headers=auth_headers)
    assert response.status_code == 404


async def test_optimizer_report_requires_authorization(client: httpx.AsyncClient) -> None:
    response = await client.get("/optimizer/report")
    assert response.status_code == 401


async def test_optimizer_report_falls_back_to_seed_variants(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get("/optimizer/report", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["cycle_count"] == 0
    variants = {variant["variant_id"]: variant for variant in payload["variants"]}
    assert "grading-v1" in variants
    assert variants["grading-v1"]["source"] == "seed"
    assert variants["grading-v1"]["active_version"] == 1
    assert variants["grading-v1"]["system_instruction"]


async def test_optimizer_report_reads_promoted_cycles(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    history = Path(container.settings.local_data_dir) / "prompts" / "optimizer.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_at": "2026-08-17T12:00:00+00:00",
        "variant_id": "grading-v1",
        "version": 2,
        "variant": {
            "variant_id": "grading-v1",
            "version": 2,
            "system_instruction": "Evolved grading instruction with stricter evidence rules.",
            "few_shots": ["cite the page before scoring"],
            "provenance": "optimizer:tournament",
        },
        "report": {
            "iteration": 1,
            "previous_metrics": {
                "mae": 0.42,
                "quadratic_weighted_kappa": 0.81,
                "bias": 0.05,
                "per_criterion": {},
            },
            "candidate_metrics": {
                "mae": 0.28,
                "quadratic_weighted_kappa": 0.89,
                "bias": 0.02,
                "per_criterion": {},
            },
            "delta_mae": -0.14,
            "accepted": True,
            "rejected_reasons": [],
        },
    }
    history.write_text(json.dumps(record) + "\n", encoding="utf-8")
    response = await client.get("/optimizer/report", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["cycle_count"] == 1
    cycle = payload["cycles"][0]
    assert cycle["variant_id"] == "grading-v1"
    assert cycle["accepted"] is True
    assert cycle["candidate"]["mae"] == 0.28
    grading = next(item for item in payload["variants"] if item["variant_id"] == "grading-v1")
    assert grading["active_version"] == 2
    assert grading["source"] == "history"
    assert grading["promoted_cycles"] == 1
    assert grading["latest_metrics"]["quadratic_weighted_kappa"] == 0.89
