import asyncio

import pytest

from autocurricula.core.resilience import (
    FallbackEvaluator,
    RepairBudgetExhausted,
    ResourceExhaustedError,
    SchemaRepairAgent,
)
from tests.review.flow_stack import make_rubric
from tests.orchestration.verifier_fixtures import ConfidenceMapEvaluator
from tests.review.flow_stack import STUDENTS


class FlakyThenValid:
    def __init__(self, failures: int) -> None:
        self._failures = failures
        self.calls = 0

    async def __call__(self, attempt: int = 0) -> str:
        self.calls += 1
        if self.calls <= self._failures:
            raise ValueError(f"broken payload #{self.calls}")
        return "repaired"


async def test_repair_agent_recovers_within_budget() -> None:
    agent = SchemaRepairAgent(budget=2)
    operation = FlakyThenValid(failures=2)

    result = await agent.run(operation)

    assert result == "repaired"
    assert operation.calls == 3
    assert agent.last_attempts == 2


async def test_repair_agent_exhausts_budget_and_reports_attempts() -> None:
    agent = SchemaRepairAgent(budget=2)
    operation = FlakyThenValid(failures=99)

    with pytest.raises(RepairBudgetExhausted, match="after 3 attempt"):
        await agent.run(operation)

    assert operation.calls == 3


async def test_repair_agent_passes_attempt_index_when_supported() -> None:
    agent = SchemaRepairAgent(budget=1)
    seen: list[int] = []

    async def operation(attempt: int = 0) -> str:
        seen.append(attempt)
        if attempt == 0:
            raise ValueError("first try broken")
        return "ok"

    assert await agent.run(operation) == "ok"
    assert seen == [0, 1]


def test_repair_agent_rejects_negative_budget() -> None:
    with pytest.raises(ValueError):
        SchemaRepairAgent(budget=-1)


def _submission(student: str):
    class Submission:
        submission_id = f"sub-{student}"
        student_id = student

    return Submission()


def _context():
    class Context:
        query = "rubric"
        chunks = []

    return Context()


def _result(confidence: float):
    evaluator = ConfidenceMapEvaluator({student: confidence for student in STUDENTS})
    return asyncio.run(_grade(evaluator, "stu-001"))


async def _grade(evaluator, student):
    return await evaluator.grade(_submission(student), make_rubric(), _context())


async def test_fallback_triggers_on_transient_error_and_scales_confidence() -> None:
    class TimingOut:
        async def grade(self, submission, rubric, context):
            raise TimeoutError("gemini pro timed out")

    fallback = ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})
    controller = FallbackEvaluator(
        TimingOut(),
        fallback,
        latency_seconds=15.0,
        confidence_factor=0.9,
    )

    result = await controller.grade(_submission("stu-001"), make_rubric(), _context())

    assert controller.last_used_fallback is True
    assert result.criterion_scores[0].confidence == pytest.approx(0.855)


async def test_fallback_triggers_on_resource_exhausted() -> None:
    class Exhausted:
        async def grade(self, submission, rubric, context):
            raise ResourceExhaustedError("429 quota")

    fallback = ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})
    controller = FallbackEvaluator(
        Exhausted(), fallback, latency_seconds=15.0, confidence_factor=0.9
    )
    result = await controller.grade(_submission("stu-001"), make_rubric(), _context())
    assert controller.last_used_fallback is True
    assert result.criterion_scores[0].confidence < 0.95


async def test_fallback_triggers_on_extreme_latency() -> None:
    class Slow:
        async def grade(self, submission, rubric, context):
            await asyncio.sleep(0.05)
            return await ConfidenceMapEvaluator(
                {student: 0.95 for student in STUDENTS}
            ).grade(submission, rubric, context)

    fallback = ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})
    controller = FallbackEvaluator(
        Slow(), fallback, latency_seconds=0.01, confidence_factor=0.9
    )
    result = await controller.grade(_submission("stu-001"), make_rubric(), _context())
    assert controller.last_used_fallback is True


async def test_healthy_primary_is_untouched() -> None:
    primary = ConfidenceMapEvaluator({student: 0.95 for student in STUDENTS})
    fallback = ConfidenceMapEvaluator({student: 0.60 for student in STUDENTS})
    controller = FallbackEvaluator(
        primary, fallback, latency_seconds=15.0, confidence_factor=0.9
    )
    result = await controller.grade(_submission("stu-001"), make_rubric(), _context())
    assert controller.last_used_fallback is False
    assert result.criterion_scores[0].confidence == pytest.approx(0.95)


async def test_no_fallback_reraises_transient_error() -> None:
    class TimingOut:
        async def grade(self, submission, rubric, context):
            raise TimeoutError("no fallback configured")

    controller = FallbackEvaluator(
        TimingOut(), None, latency_seconds=15.0, confidence_factor=0.9
    )
    with pytest.raises(TimeoutError):
        await controller.grade(_submission("stu-001"), make_rubric(), _context())
