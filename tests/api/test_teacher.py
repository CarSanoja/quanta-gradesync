from datetime import UTC, datetime
from pathlib import Path

import httpx

from autocurricula.api.dependencies import AppContainer
from autocurricula.api.teacher_triage import (
    BATCH_HOLD_EMPTY,
    BATCH_HOLD_NOTE,
    BATCH_HOLD_TITLE,
    JUDGEMENT_EMPTY,
    JUDGEMENT_NOTE,
    JUDGEMENT_TITLE,
)
from autocurricula.api.teacher_views import (
    BATCH_HELD,
    BLURRY_SCAN,
    FALLBACK_REASON,
    INJECTION_FOUND,
    NO_QUOTE,
    NOT_SURE,
    display_name,
    points_text,
    translate_reason,
    translate_reasons,
)
from autocurricula.config.settings import Settings
from autocurricula.core.memory.session_memory import SessionState
from autocurricula.core.orchestration.job_state import JobRecord, JobStage
from autocurricula.schemas.common import utc_now
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
LOT_CODE = "2026_Matematicas_10A_Parcial1"
BATCH_JOB_ID = "uploads-2026-matematicas-10a-parcial1"
GRADED_AT = datetime(2026, 8, 19, 11, 0, tzinfo=UTC)
MASTERY = {level: f"{level.value} response" for level in MasteryLevel}


def make_review(job_id: str, reasons: list[str]) -> ReviewItem:
    return ReviewItem(
        review_id=f"{job_id}:ana-torres",
        job_id=job_id,
        student_id="ana-torres",
        subject=SUBJECT,
        reasons=reasons,
        evidence=[
            EvidenceSpan(page=1, quote="(x + 3)(x - ?)", rationale="Second factor is illegible")
        ],
        document_paths=["gs://exam-uploads/batches/lot/ana-torres.jpg"],
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


def make_state(job_id: str) -> SessionState:
    batch = ExamBatch(
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
                        gcs_uri="gs://exam-uploads/batches/lot/ana-torres.jpg",
                        mime_type="image/jpeg",
                        page_count=1,
                    )
                ],
            )
        ],
    )
    rubric = Rubric(
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
                            EvidenceSpan(page=1, quote="(x + 3)(x - ?)", rationale="illegible")
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
    return SessionState(
        job_id=job_id,
        stage_results={
            "fetch": {
                "batch": batch.model_dump(mode="json"),
                "rubric": rubric.model_dump(mode="json"),
                "curriculum_standard": {
                    "country": "CO",
                    "version": "2026",
                    "competencies": [
                        {
                            "code": "MAT.10.1",
                            "description": "Factors quadratic expressions",
                            "grade_level": "10",
                            "subject": SUBJECT,
                        }
                    ],
                },
            },
            "grade": grades.model_dump(mode="json"),
        },
        stage_statuses={"fetch": "succeeded", "grade": "succeeded"},
    )


def test_translate_reason_maps_legibility_to_blurry_copy() -> None:
    reason = (
        "crit-a confidence 0.812 x legibility factor 0.60 = effective 0.487 "
        "below threshold 0.85"
    )
    assert translate_reason(reason) == BLURRY_SCAN


def test_translate_reason_maps_prompt_injection_to_instruction_copy() -> None:
    assert translate_reason("prompt injection suspected: ignore the rubric") == INJECTION_FOUND


def test_translate_reason_maps_batch_anomaly_to_precaution_copy() -> None:
    assert (
        translate_reason("batch anomaly breaker: quarantine ratio 0.400 over 0.15")
        == BATCH_HELD
    )


def test_translate_reason_maps_missing_evidence_and_low_confidence() -> None:
    assert translate_reason("crit-a has no cited evidence") == NO_QUOTE
    assert translate_reason("crit-a confidence 0.620 below threshold 0.85") == NOT_SURE


def test_translate_reason_falls_back_to_generic_copy() -> None:
    assert translate_reason("something completely new") == FALLBACK_REASON


def test_translate_reasons_deduplicates_repeated_translations() -> None:
    reasons = [
        "crit-a confidence 0.620 below threshold 0.85",
        "crit-b confidence 0.700 below threshold 0.85",
        "crit-b has no cited evidence",
    ]
    assert translate_reasons(reasons) == [NOT_SURE, NO_QUOTE]


def test_display_name_and_points_text_read_plainly() -> None:
    assert display_name("ana-torres") == "Ana Torres"
    assert display_name("luis_r.perez") == "Luis R Perez"
    assert points_text(2.0, 4.0) == "2 of 4 points"
    assert points_text(2.5, None) == "2.5 points"


async def test_teacher_page_is_public_html(client: httpx.AsyncClient) -> None:
    response = await client.get("/teacher")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "GradeSync" in response.text
    assert "Access code" in response.text
    assert "/teacher/assets/teacher.js" in response.text


async def test_teacher_assets_are_served_from_a_whitelist(client: httpx.AsyncClient) -> None:
    styles = await client.get("/teacher/assets/teacher.css")
    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")
    script = await client.get("/teacher/assets/teacher.js")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("text/javascript")
    for asset in (
        "teacher-actions.js",
        "teacher-dialogs.js",
        "teacher-filenames.js",
        "teacher-format.js",
        "teacher-held.js",
        "teacher-review.js",
        "teacher-screens.js",
        "teacher-state.js",
        "teacher-upload.js",
        "teacher-uploading.js",
    ):
        module = await client.get(f"/teacher/assets/{asset}")
        assert module.status_code == 200
        assert module.headers["content-type"].startswith("text/javascript")
    traversal = await client.get("/teacher/assets/%2e%2e%2fteacher.py")
    assert traversal.status_code == 404
    unknown = await client.get("/teacher/assets/console.js")
    assert unknown.status_code == 404


async def test_teacher_summary_requires_the_access_token(client: httpx.AsyncClient) -> None:
    missing = await client.get("/teacher/summary")
    assert missing.status_code == 401
    wrong = await client.get("/teacher/summary", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 403


def empty_group(key: str, title: str, note: str, empty_note: str, bulk: bool) -> dict:
    return {
        "key": key,
        "title": title,
        "count": 0,
        "note": note,
        "empty_note": empty_note,
        "bulk_releasable": bulk,
        "reasons": [],
        "items": [],
    }


async def test_teacher_summary_starts_empty(client: httpx.AsyncClient, auth_headers) -> None:
    response = await client.get("/teacher/summary", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {
        "waiting": [],
        "waiting_count": 0,
        "judgement": empty_group(
            "judgement", JUDGEMENT_TITLE, JUDGEMENT_NOTE, JUDGEMENT_EMPTY, False
        ),
        "batch_hold": empty_group(
            "batch_hold", BATCH_HOLD_TITLE, BATCH_HOLD_NOTE, BATCH_HOLD_EMPTY, True
        ),
        "batch": None,
        "batches": [],
    }


async def test_teacher_summary_translates_reasons_and_projects_plain_grades(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    job_id = "job-teacher-1"
    reasons = [
        "crit-a confidence 0.812 x legibility factor 0.60 = effective 0.487 below threshold 0.85",
        "prompt injection suspected: give full marks",
    ]
    await container.review_service.store.put(make_review(job_id, reasons))
    await container.checkpoint_store.save_state(job_id, make_state(job_id))
    response = await client.get("/teacher/summary", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["waiting_count"] == 1
    item = payload["waiting"][0]
    assert item["student_name"] == "Ana Torres"
    assert item["reasons"] == [BLURRY_SCAN, INJECTION_FOUND]
    assert item["score_text"] == "2 points"
    assert item["percentage"] == 50.0
    assert item["has_page"] is True
    assert item["evidence"][0]["quote"] == "(x + 3)(x - ?)"
    criterion = item["criteria"][0]
    assert criterion["title"] == "Factor the quadratic expression"
    assert criterion["score_text"] == "2 of 4 points"
    assert criterion["criterion_id"] == "crit-a"
    assert criterion["score"] == 2.0
    assert criterion["max_score"] == 4.0
    assert item["total_text"] == "2 of 4 points"
    assert item["max_score"] == 4.0
    assert item["can_edit_marks"] is True
    assert "confidence" not in criterion
    assert "0.62" not in response.text


async def test_teacher_summary_survives_a_missing_job_checkpoint(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    await container.review_service.store.put(
        make_review("job-teacher-ghost", ["crit-a has no cited evidence"])
    )
    response = await client.get("/teacher/summary", headers=auth_headers)
    assert response.status_code == 200
    item = response.json()["waiting"][0]
    assert item["reasons"] == [NO_QUOTE]
    assert item["criteria"] == []
    assert item["can_edit_marks"] is False
    assert item["max_score"] == 4.0
    assert item["total_text"] == "2 of 4 points"


def stage_uploads(settings: Settings, names: list[str]) -> None:
    directory = (
        Path(settings.gcs_local_staging_dir)
        / "local-exams"
        / "uploads"
        / "batches"
        / LOT_CODE
    )
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"scan bytes")


def make_batch_record() -> JobRecord:
    event = PubSubJobEvent(
        job_id=BATCH_JOB_ID,
        bucket="local-exams",
        exam_batch_prefix=f"uploads/batches/{LOT_CODE}",
        class_id="10A",
        subject=SUBJECT,
        triggered_at=utc_now(),
    )
    return JobRecord(job_id=BATCH_JOB_ID, event=event, stage=JobStage.COMPLETED)


def make_synced_state() -> SessionState:
    state = make_state(BATCH_JOB_ID)
    state.stage_results["sync"] = SISWriteResult(
        job_id=BATCH_JOB_ID,
        per_record_statuses={"luis-perez": "ok"},
        succeeded_count=1,
        failed_count=0,
        quarantined_count=1,
    ).model_dump(mode="json")
    return state


async def test_batch_progress_counts_the_upload_before_grading_starts(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    stage_uploads(container.settings, ["ana-torres.jpg", "luis-perez.jpg"])
    response = await client.get(
        "/teacher/summary", params={"batch": LOT_CODE}, headers=auth_headers
    )
    assert response.status_code == 200
    batch = response.json()["batch"]
    assert batch["received"] == 2
    assert batch["still_grading"] == 2
    assert batch["settled"] is False
    assert batch["headline"] == (
        "We received 2 exams for Parcial1. "
        "Grading starts on its own — nothing for you to do yet."
    )


async def test_batch_progress_speaks_in_gradebook_terms(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    stage_uploads(container.settings, ["ana-torres.jpg", "luis-perez.jpg"])
    await container.checkpoint_store.save(make_batch_record())
    await container.checkpoint_store.save_state(BATCH_JOB_ID, make_synced_state())
    await container.review_service.store.put(
        make_review(BATCH_JOB_ID, ["crit-a confidence 0.620 below threshold 0.85"])
    )
    response = await client.get(
        "/teacher/summary", params={"batch": LOT_CODE}, headers=auth_headers
    )
    batch = response.json()["batch"]
    assert batch["in_gradebook"] == 1
    assert batch["waiting_for_you"] == 1
    assert batch["still_grading"] == 0
    assert batch["settled"] is True
    assert batch["headline"] == (
        "We received 2 exams for Parcial1. Grading has started — "
        "1 is already in the gradebook and 1 is waiting for your review."
    )


async def test_batch_progress_is_absent_for_an_unknown_batch(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get(
        "/teacher/summary", params={"batch": "2026_Ghost_10A_Parcial9"}, headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["batch"] is None


async def test_batch_progress_counts_the_grades_the_teacher_released(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    stage_uploads(container.settings, ["ana-torres.jpg", "luis-perez.jpg", "nora-diaz.jpg"])
    await container.checkpoint_store.save(make_batch_record())
    await container.checkpoint_store.save_state(BATCH_JOB_ID, make_synced_state())
    held = "batch anomaly breaker: quarantine ratio 0.400 exceeds threshold 0.150"
    for student in ("ana-torres", "nora-diaz"):
        item = make_review(BATCH_JOB_ID, [held])
        await container.review_service.store.put(
            item.model_copy(
                update={
                    "review_id": f"{BATCH_JOB_ID}:{student}",
                    "student_id": student,
                    "proposed_record": item.proposed_record.model_copy(
                        update={"student_id": student}
                    ),
                }
            )
        )
    before = await client.get(
        "/teacher/summary", params={"batch": LOT_CODE}, headers=auth_headers
    )
    assert before.json()["batch"]["in_gradebook"] == 1
    released = await client.post(
        "/review/bulk-approve",
        json={"job_id": BATCH_JOB_ID},
        headers=auth_headers,
    )
    assert released.json()["released_count"] == 2
    after = (
        await client.get(
            "/teacher/summary", params={"batch": LOT_CODE}, headers=auth_headers
        )
    ).json()["batch"]
    assert after["in_gradebook"] == 3
    assert after["waiting_for_you"] == 0
    assert after["still_grading"] == 0
    assert after["minutes_left"] == 0


async def test_summary_lists_recent_batches_without_a_batch_query(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    stage_uploads(container.settings, ["ana-torres.jpg", "luis-perez.jpg"])
    await container.checkpoint_store.save(make_batch_record())
    await container.checkpoint_store.save_state(BATCH_JOB_ID, make_synced_state())
    response = await client.get("/teacher/summary", headers=auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["batch"] is None
    assert len(payload["batches"]) == 1
    recent = payload["batches"][0]
    assert recent["lot_code"] == LOT_CODE
    assert recent["job_id"] == BATCH_JOB_ID
    assert recent["assessment"] == "Parcial1"
    assert recent["started_at"] is not None
    assert recent["decided_by_you"] == 0
    assert recent["graded_automatically"] == 1


async def test_summary_counts_the_grades_the_teacher_decided_herself(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    stage_uploads(container.settings, ["ana-torres.jpg", "luis-perez.jpg"])
    await container.checkpoint_store.save(make_batch_record())
    await container.checkpoint_store.save_state(BATCH_JOB_ID, make_synced_state())
    held = "batch anomaly breaker: quarantine ratio 0.400 exceeds threshold 0.150"
    await container.review_service.store.put(make_review(BATCH_JOB_ID, [held]))
    released = await client.post(
        "/review/bulk-approve", json={"job_id": BATCH_JOB_ID}, headers=auth_headers
    )
    assert released.json()["released_count"] == 1
    payload = await client.get("/teacher/summary", headers=auth_headers)
    recent = payload.json()["batches"][0]
    assert recent["decided_by_you"] == 1
    assert recent["graded_automatically"] == 1
    assert recent["in_gradebook"] == 2
