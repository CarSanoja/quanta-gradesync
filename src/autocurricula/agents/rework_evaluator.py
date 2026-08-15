from autocurricula.agents.evaluator import GradingEvaluator
from autocurricula.agents.grading_agent import build_grading_evaluator
from autocurricula.config.settings import Settings


def build_rework_evaluator(settings: Settings) -> GradingEvaluator | None:
    if settings.local_mode:
        return None
    second_opinion = settings.model_copy(
        update={"gemini_pro_model": settings.gemini_flash_model}
    )
    return build_grading_evaluator(second_opinion)
