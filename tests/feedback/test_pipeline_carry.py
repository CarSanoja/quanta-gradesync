import asyncio
from pathlib import Path

from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.job_state import JobStage
from autocurricula.schemas.feedback import (
    FeedbackBand,
    FeedbackPoint,
    StudentFeedback,
    band_for_grade_level,
)
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult
from tests.orchestration.incident_fixtures import build_incident_runner, synced_records
from tests.review.flow_stack import (
    LOW_CONFIDENCE_STUDENT,
    make_event,
    make_settings,
    stage_batch,
)

JOB_ID = "job-feedback-carry"


class BandAwareEvaluator:
    def __init__(self, band: FeedbackBand | None = None, log: list | None = None) -> None:
        self.band = band
        self.log = log if log is not None else []

    def for_grade_level(self, grade_level: str | None) -> "BandAwareEvaluator":
        self.log.append(grade_level)
        return BandAwareEvaluator(band_for_grade_level(grade_level), self.log)

    async def grade(self, submission, rubric, context) -> GradingResult:
        await asyncio.sleep(0)
        criterion = rubric.criteria[0]
        confidence = 0.6 if submission.student_id == LOW_CONFIDENCE_STUDENT else 0.95
        score = criterion.max_score * 0.75
        student_feedback = (
            None
            if self.band is None
            else StudentFeedback(
                band=self.band,
                headline=f"Your setup is complete, {submission.student_id}.",
                strengths=[FeedbackPoint(text="You wrote the ratio before solving.")],
                growth=[FeedbackPoint(text="Next time, write the unit beside each number.")],
                next_step="Write the unit beside each number on the next question.",
                teacher_note="crit-a proficient; units are the missing move.",
            )
        )
        return GradingResult(
            submission_id=submission.submission_id,
            criterion_scores=[
                CriterionScore(
                    criterion_id=criterion.criterion_id,
                    score=score,
                    comment="assessed with cited page",
                    evidence=[
                        EvidenceSpan(
                            page=1,
                            quote=f"visible answer of {submission.student_id}",
                            rationale="matches rubric criterion",
                        )
                    ],
                    confidence=confidence,
                )
            ],
            total_score=score,
            percentage=100.0 * score / criterion.max_score,
            feedback=f"feedback for {submission.student_id}",
            student_feedback=student_feedback,
        )


async def run_pipeline(tmp_path: Path):
    settings = make_settings(tmp_path)
    memory_manager = MemoryManager.from_settings(settings)
    stage_batch(settings, JOB_ID)
    evaluator = BandAwareEvaluator()
    runner, review_store = build_incident_runner(
        settings, memory_manager, evaluator, verify_max_iterations=0
    )
    record = await runner.process(make_event(JOB_ID))
    assert record.stage == JobStage.COMPLETED
    return settings, review_store, evaluator


async def test_the_grade_stage_binds_the_band_of_the_batch_grade_level(
    tmp_path: Path,
) -> None:
    _, _, evaluator = await run_pipeline(tmp_path)
    assert evaluator.log == ["grade-8"]
    assert band_for_grade_level("grade-8") is FeedbackBand.LOWER_SECONDARY


async def test_synced_sis_records_carry_the_student_feedback(tmp_path: Path) -> None:
    settings, _, _ = await run_pipeline(tmp_path)
    records = synced_records(settings)
    assert records
    for record in records:
        assert record["student_id"] != LOW_CONFIDENCE_STUDENT
        feedback = record["student_feedback"]
        assert feedback["band"] == FeedbackBand.LOWER_SECONDARY.value
        assert feedback["next_step"]
        assert record["feedback"]


async def test_quarantined_review_items_carry_the_student_feedback(tmp_path: Path) -> None:
    _, review_store, _ = await run_pipeline(tmp_path)
    pending = await review_store.list_pending()
    held = [item for item in pending if item.student_id == LOW_CONFIDENCE_STUDENT]
    assert len(held) == 1
    proposed = held[0].proposed_record
    assert proposed.student_feedback is not None
    assert proposed.student_feedback.band is FeedbackBand.LOWER_SECONDARY
    assert proposed.student_feedback.teacher_note
    assert proposed.feedback
