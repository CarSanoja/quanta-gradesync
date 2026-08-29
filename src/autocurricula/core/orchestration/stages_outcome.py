from collections.abc import Callable, Sequence

from autocurricula.agents.meta_optimizer import MetaOptimizerAgent
from autocurricula.agents.risk_detector import RiskDetector
from autocurricula.core.fleet import (
    META_OPTIMIZER_AUDIT_ID,
    META_OPTIMIZER_GRADING_ID,
    RISK_DETECTOR_ID,
)
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.agent_span import agent_span
from autocurricula.core.orchestration.context import (
    STAGE_OPTIMIZE,
    STAGE_RISK,
    JobContext,
    OptimizeOutputs,
    RiskOutputs,
    StageCallable,
)
from autocurricula.schemas.events import PubSubJobEvent
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.metrics import OptimizerReport
from autocurricula.schemas.risk import RiskAssessment

TERM_PREFIX = "term"

OPTIMIZER_AGENTS = {
    "grading-v1": META_OPTIMIZER_GRADING_ID,
    "auditor-v1": META_OPTIMIZER_AUDIT_ID,
}

TermResolver = Callable[[PubSubJobEvent], str]


def default_term(event: PubSubJobEvent) -> str:
    return f"{TERM_PREFIX}-{event.triggered_at.strftime('%Y-%m')}"


def build_risk_step(
    memory_manager: MemoryManager, risk_detector: RiskDetector
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        batch = context.batch
        grouped: dict[str, list[GradingResult]] = {
            submission.student_id: [] for submission in batch.submissions
        }
        student_by_submission = {
            submission.submission_id: submission.student_id
            for submission in batch.submissions
        }
        for result in context.grade_result.results:
            student_id = student_by_submission.get(result.submission_id)
            if student_id is not None:
                grouped[student_id].append(result)
        assessments: list[RiskAssessment] = []
        for student_id, student_results in grouped.items():
            if not student_results:
                continue
            profile = await memory_manager.load_student_history(student_id)
            with agent_span(
                context.recorder,
                f"Risk_{student_id}",
                RISK_DETECTOR_ID,
                stage="RISK",
                attributes={"student_id": student_id},
            ):
                assessments.append(
                    await risk_detector.assess(
                        profile,
                        student_results,
                        context.job_id,
                        student_id=student_id,
                    )
                )
        context.complete(STAGE_RISK, RiskOutputs(assessments=assessments))
        return context

    return run


def build_optimize_step(
    optimizers: Sequence[MetaOptimizerAgent],
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        reports: list[OptimizerReport] = []
        for optimizer in optimizers:
            variant = getattr(optimizer, "variant_id", "")
            with agent_span(
                context.recorder,
                f"Optimize_{variant or 'variant'}",
                OPTIMIZER_AGENTS.get(variant, META_OPTIMIZER_GRADING_ID),
                stage="OPTIMIZE",
                attributes={"prompt.variant_id": variant},
            ) as span:
                try:
                    winners = await optimizer.run_until_convergence()
                except (FileNotFoundError, OSError, ValueError) as error:
                    # The tournament needs a calibration set on disk, and a
                    # deployed container has none. Swallowing it silently left a
                    # span carrying an agent id and a prompt variant for work
                    # that raised on its first statement — the one place the
                    # telemetry said something untrue. A skip is now a skip.
                    if span is not None:
                        span.set("optimize.skipped", True)
                        span.set("optimize.skipped_reason", type(error).__name__)
                    continue
                reports.extend(winners)
        context.complete(STAGE_OPTIMIZE, OptimizeOutputs(reports=reports))
        return context

    return run
