from typing import Protocol

from autocurricula.agents.base import AgentResponseError
from autocurricula.schemas.exam import ExamSubmission
from autocurricula.schemas.grading import GradingResult
from autocurricula.schemas.memory import RetrievedContext
from autocurricula.schemas.rubric import Rubric


class GradingValidationError(AgentResponseError):
    pass


class GradingEvaluator(Protocol):
    async def grade(
        self, submission: ExamSubmission, rubric: Rubric, context: RetrievedContext
    ) -> GradingResult: ...
