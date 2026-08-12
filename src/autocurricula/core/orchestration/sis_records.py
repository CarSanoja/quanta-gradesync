from collections.abc import Sequence

from autocurricula.schemas.curriculum import CurriculumAuditResult
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import GradingBatchResult, GradingResult
from autocurricula.schemas.sis_sync import SISGradeRecord, SISWriteRequest

FEEDBACK_SEPARATOR = " | "


def ordered_student_ids(batch: ExamBatch) -> list[str]:
    return list(dict.fromkeys(s.student_id for s in batch.submissions))


def group_results_by_student(
    batch: ExamBatch, results: Sequence[GradingResult]
) -> dict[str, list[GradingResult]]:
    student_by_submission = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    grouped: dict[str, list[GradingResult]] = {
        student_id: [] for student_id in ordered_student_ids(batch)
    }
    for result in results:
        student_id = student_by_submission.get(result.submission_id)
        if student_id is not None:
            grouped[student_id].append(result)
    return grouped


def covered_codes_by_student(
    batch: ExamBatch, audits: Sequence[CurriculumAuditResult]
) -> dict[str, set[str]]:
    student_by_submission = {
        submission.submission_id: submission.student_id
        for submission in batch.submissions
    }
    covered: dict[str, set[str]] = {}
    for audit in audits:
        student_id = student_by_submission.get(audit.submission_id)
        if student_id is None:
            continue
        covered.setdefault(student_id, set()).update(audit.covered_codes)
    return covered


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def build_sis_write_request(
    batch: ExamBatch,
    batch_result: GradingBatchResult,
    audits: Sequence[CurriculumAuditResult],
) -> SISWriteRequest:
    grouped = group_results_by_student(batch, batch_result.results)
    covered = covered_codes_by_student(batch, audits)
    records: list[SISGradeRecord] = []
    for student_id in ordered_student_ids(batch):
        student_results = grouped.get(student_id, [])
        if not student_results:
            continue
        feedback = FEEDBACK_SEPARATOR.join(
            dict.fromkeys(result.feedback for result in student_results)
        )
        records.append(
            SISGradeRecord(
                student_id=student_id,
                subject=batch.subject,
                score=_mean([result.total_score for result in student_results]),
                percentage=_mean([result.percentage for result in student_results]),
                feedback=feedback,
                competency_codes=sorted(covered.get(student_id, set())),
                graded_at=batch_result.graded_at,
            )
        )
    return SISWriteRequest(job_id=batch.job_id, records=records)
