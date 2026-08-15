from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.catalog import LocalJobCatalog
from autocurricula.core.orchestration.job_state import LocalCheckpointStore
from autocurricula.core.orchestration.runner import JobRunner
from autocurricula.core.review import LocalReviewStore
from autocurricula.schemas.grading import CriterionScore, EvidenceSpan, GradingResult
from autocurricula.schemas.verification import VerificationReport
from autocurricula.tools.gcs_fetcher import LocalStagingFetcher
from autocurricula.tools.sis_connector import LocalSISConnector
from tests.review.flow_stack import ScriptedAuditor


def _result_for(submission, rubric, confidence: float) -> GradingResult:
    criterion = rubric.criteria[0]
    factor = 0.9 if confidence >= 0.85 else 0.5
    score = criterion.max_score * factor
    return GradingResult(
        submission_id=submission.submission_id,
        criterion_scores=[
            CriterionScore(
                criterion_id=criterion.criterion_id,
                score=score,
                comment="assessed",
                evidence=[
                    EvidenceSpan(
                        page=1,
                        quote=f"visible answer of {submission.student_id}",
                        rationale="matches criterion",
                    )
                ],
                confidence=confidence,
            )
        ],
        total_score=score,
        percentage=100.0 * factor,
        feedback=f"feedback for {submission.student_id}",
    )


class ConfidenceMapEvaluator:
    def __init__(self, confidence_by_student: dict[str, float]) -> None:
        self._confidences = confidence_by_student

    async def grade(self, submission, rubric, context) -> GradingResult:
        return _result_for(submission, rubric, self._confidences[submission.student_id])


class FixedReworkEvaluator(ConfidenceMapEvaluator):
    def __init__(self, confidence: float, students: tuple[str, ...]) -> None:
        super().__init__({student: confidence for student in students})


class StatefulReworkEvaluator:
    def __init__(self, low_calls: int, confidence: float = 0.95) -> None:
        self._remaining_low = low_calls
        self._confidence = confidence

    async def grade(self, submission, rubric, context) -> GradingResult:
        confidence = self._confidence if self._remaining_low <= 0 else 0.6
        self._remaining_low -= 1
        return _result_for(submission, rubric, confidence)


def build_runner(
    settings,
    memory_manager: MemoryManager,
    primary,
    rework=None,
    verify_max_iterations: int = 2,
) -> tuple[JobRunner, LocalReviewStore]:
    review_store = LocalReviewStore(data_dir=settings.local_data_dir)
    runner = JobRunner(
        memory_manager=memory_manager,
        fetcher=LocalStagingFetcher(staging_dir=settings.gcs_local_staging_dir),
        grading_evaluator=primary,
        auditor=ScriptedAuditor(),
        risk_detector=RiskDetector(),
        sis_connector=LocalSISConnector(data_dir=settings.local_data_dir),
        checkpoint_store=LocalCheckpointStore(data_dir=settings.local_data_dir),
        catalog=LocalJobCatalog(staging_dir=settings.gcs_local_staging_dir),
        review_store=review_store,
        rework_evaluator=rework,
        verify_max_iterations=verify_max_iterations,
    )
    return runner, review_store


async def verification_report(settings, job_id: str) -> VerificationReport:
    state = await LocalCheckpointStore(data_dir=settings.local_data_dir).load_state(job_id)
    raw = state.stage_results["verify"]
    return VerificationReport.model_validate(raw)
