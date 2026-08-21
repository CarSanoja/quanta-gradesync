import copy
from collections.abc import Callable
from typing import Any

from autocurricula.agents.base import (
    make_user_content,
    resolve_model,
    run_agent_for_text,
    structured_output_with_retry,
    text_part,
)
from autocurricula.agents.evaluator import (
    GradingEvaluator,
    GradingValidationError,
    salvage_without_student_feedback,
    stamp_feedback_band,
)
from autocurricula.agents.grading_tools import build_grading_tools
from autocurricula.agents.prompts.grading_parts import (
    MAX_INLINE_FILE_BYTES,
    build_grading_parts,
)
from autocurricula.agents.prompts.grading_prompts import (
    build_grading_prompt_variant,
    grading_repair_instruction,
)
from autocurricula.config.settings import Settings
from autocurricula.core.evolution.prompt_mutator import PromptVariant
from autocurricula.schemas.exam import ExamSubmission
from autocurricula.schemas.feedback import FeedbackBand, band_for_grade_level
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric

GRADING_AGENT_NAME = "grading_agent"
GRADING_APP_NAME = "gradesync_grading"
GRADING_USER_ID = "gradesync_worker"

RunnerFactory = Callable[[Any, Any], Any]


def compose_system_instruction(variant: PromptVariant) -> str:
    blocks = [variant.system_instruction]
    for index, shot in enumerate(variant.few_shots, start=1):
        blocks.append(f"Worked example {index}:\n{shot}")
    return "\n\n".join(blocks)


def _validation_error(message: str, raw: str, cause: Exception) -> GradingValidationError:
    return GradingValidationError(message, raw=raw, cause=cause)


def _build_agent(*, model: str, instruction: str, tools: list[Any]) -> Any:
    from google.adk.agents import LlmAgent

    return LlmAgent(
        name=GRADING_AGENT_NAME,
        model=model,
        instruction=instruction,
        description="Multimodal rubric-grounded exam grading specialist",
        tools=tools,
        output_schema=GradingResult,
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


def _default_session_service() -> Any:
    from google.adk.sessions import InMemorySessionService

    return InMemorySessionService()


def _default_runner_factory(agent: Any, session_service: Any) -> Any:
    from google.adk.runners import Runner

    return Runner(agent=agent, app_name=GRADING_APP_NAME, session_service=session_service)


class AdkGradingEvaluator(GradingEvaluator):
    def __init__(
        self,
        settings: Settings,
        *,
        variant: PromptVariant | None = None,
        runner_factory: RunnerFactory | None = None,
        session_service: Any | None = None,
        max_inline_bytes: int = MAX_INLINE_FILE_BYTES,
    ) -> None:
        self._settings = settings
        self._band: FeedbackBand | None = None
        self._variant = variant if variant is not None else build_grading_prompt_variant()
        self._model = resolve_model(settings)
        self._max_inline_bytes = max_inline_bytes
        self._session_service = (
            session_service if session_service is not None else _default_session_service()
        )
        self._runner_factory = (
            runner_factory if runner_factory is not None else _default_runner_factory
        )
        self._agent = _build_agent(
            model=self._model,
            instruction=compose_system_instruction(self._variant),
            tools=build_grading_tools(settings),
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def variant_id(self) -> str:
        return self._variant.variant_id

    @property
    def feedback_band(self) -> FeedbackBand | None:
        return self._band

    def for_grade_level(self, grade_level: str | None) -> "AdkGradingEvaluator":
        bound = copy.copy(self)
        bound._band = band_for_grade_level(grade_level)
        return bound

    async def grade(
        self, submission: ExamSubmission, rubric: Rubric, context: RetrievedContext
    ) -> GradingResult:
        session = await self._session_service.create_session(
            app_name=GRADING_APP_NAME, user_id=GRADING_USER_ID
        )
        runner = self._runner_factory(self._agent, self._session_service)
        parts = await build_grading_parts(
            submission,
            rubric,
            context,
            max_inline_bytes=self._max_inline_bytes,
            band=self._band,
        )

        async def call(repair: str | None) -> str:
            message_parts = list(parts)
            if repair is not None:
                message_parts.append(text_part(repair))
            message = make_user_content(message_parts)
            return await run_agent_for_text(runner, GRADING_USER_ID, session.id, message)

        try:
            result = await structured_output_with_retry(
                call,
                GradingResult,
                _validation_error,
                build_repair=grading_repair_instruction,
            )
        except GradingValidationError as error:
            salvaged = salvage_without_student_feedback(error)
            if salvaged is None:
                raise
            result = salvaged
        return stamp_feedback_band(result, self._band)


def build_grading_evaluator(
    settings: Settings,
    *,
    variant: PromptVariant | None = None,
    runner_factory: RunnerFactory | None = None,
    session_service: Any | None = None,
) -> AdkGradingEvaluator:
    return AdkGradingEvaluator(
        settings,
        variant=variant,
        runner_factory=runner_factory,
        session_service=session_service,
    )
