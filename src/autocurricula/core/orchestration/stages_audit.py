from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.core.fleet import CURRICULUM_AUDITOR_ID, authorize_llm
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.core.orchestration.agent_span import agent_span
from autocurricula.core.orchestration.concurrency import (
    DEFAULT_MODEL_CONCURRENCY,
    gather_limited,
)
from autocurricula.core.orchestration.context import (
    STAGE_AUDIT,
    AuditOutputs,
    JobContext,
    StageCallable,
)


def build_audit_step(
    memory_manager: MemoryManager,
    auditor: CurriculumAuditor,
    model_concurrency: int = DEFAULT_MODEL_CONCURRENCY,
) -> StageCallable:
    async def run(context: JobContext) -> JobContext:
        standard = context.curriculum_standard
        query = " ".join(
            f"{competency.code} {competency.description}"
            for competency in standard.competencies
        )
        retrieved = await memory_manager.l2.search(query)
        authorize_llm(
            CURRICULUM_AUDITOR_ID,
            context.job_id,
            model_id=getattr(auditor, "model_id", ""),
            recorder=context.recorder,
        )
        model_id = getattr(auditor, "model_id", "")
        student_by_submission = {
            submission.submission_id: submission.student_id
            for submission in context.batch.submissions
        }

        async def audited(result):
            with agent_span(
                context.recorder,
                f"Audit_{result.submission_id}",
                CURRICULUM_AUDITOR_ID,
                stage="AUDIT",
                attributes={
                    "submission_id": result.submission_id,
                    "student_id": student_by_submission.get(result.submission_id, ""),
                    "gen_ai.model": model_id,
                },
            ):
                return await auditor.audit(result, standard, retrieved)

        audits = await gather_limited(
            (audited(result) for result in context.grade_result.results),
            model_concurrency,
        )
        context.complete(STAGE_AUDIT, AuditOutputs(audits=list(audits)))
        return context

    return run
