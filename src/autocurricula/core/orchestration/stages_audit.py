from autocurricula.agents.curriculum_auditor import CurriculumAuditor
from autocurricula.core.fleet import CURRICULUM_AUDITOR_ID, authorize_llm
from autocurricula.core.memory.manager import MemoryManager
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
        audits = await gather_limited(
            (
                auditor.audit(result, standard, retrieved)
                for result in context.grade_result.results
            ),
            model_concurrency,
        )
        context.complete(STAGE_AUDIT, AuditOutputs(audits=list(audits)))
        return context

    return run
