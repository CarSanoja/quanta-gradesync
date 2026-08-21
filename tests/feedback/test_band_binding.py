import json
from typing import Any

import pytest

from autocurricula.agents.evaluator import GradingValidationError, bind_feedback_band
from autocurricula.agents.grading_agent import AdkGradingEvaluator
from autocurricula.config.settings import Settings
from autocurricula.schemas.feedback import FeedbackBand
from autocurricula.schemas.grading import GradingResult
from tests.feedback.fixtures import make_context, make_result, make_rubric, make_submission


class _Session:
    id = "session-feedback-1"


class _SessionService:
    async def create_session(self, *, app_name: str, user_id: str) -> _Session:
        return _Session()


class _Part:
    def __init__(self, text: str) -> None:
        self.text = text


class _Content:
    def __init__(self, text: str) -> None:
        self.parts = [_Part(text)]


class _Event:
    def __init__(self, text: str) -> None:
        self.content = _Content(text)


class _Runner:
    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    async def run_async(self, *, user_id: str, session_id: str, new_message: Any):
        self.prompts.append(
            "\n".join(part.text for part in new_message.parts if getattr(part, "text", None))
        )
        yield _Event(self.replies.pop(0) if self.replies else "{}")


def build_evaluator(settings: Settings, replies: list[str]) -> tuple[AdkGradingEvaluator, _Runner]:
    runner = _Runner(replies)
    evaluator = AdkGradingEvaluator(
        settings,
        runner_factory=lambda agent, service: runner,
        session_service=_SessionService(),
    )
    return evaluator, runner


def reply_with(band: str | None, malformed: bool = False) -> str:
    payload = json.loads(make_result().model_dump_json())
    if band is not None:
        feedback = {
            "band": band,
            "headline": "You found the factor pair that works.",
            "strengths": [],
            "growth": [],
            "next_step": "Expand your factors and compare with the question.",
            "teacher_note": None,
        }
        if malformed:
            feedback.pop("next_step")
        payload["student_feedback"] = feedback
    return json.dumps(payload)


async def test_the_band_block_reaches_the_model_for_the_bound_grade_level(
    settings: Settings,
) -> None:
    evaluator, runner = build_evaluator(settings, [reply_with("early_primary")])
    bound = evaluator.for_grade_level("2")
    assert bound.feedback_band is FeedbackBand.EARLY_PRIMARY
    await bound.grade(make_submission(), make_rubric(), make_context())
    prompt = runner.prompts[0]
    assert "STUDENT FEEDBACK BAND FOR THIS SUBMISSION: early_primary" in prompt
    assert "at most 10 words" in prompt
    assert "upper_secondary" not in prompt


async def test_an_unknown_grade_level_asks_for_no_band_at_all(settings: Settings) -> None:
    evaluator, runner = build_evaluator(settings, [reply_with(None)])
    bound = evaluator.for_grade_level("adult education")
    assert bound.feedback_band is None
    result = await bound.grade(make_submission(), make_rubric(), make_context())
    assert "STUDENT FEEDBACK BAND FOR THIS SUBMISSION" not in runner.prompts[0]
    assert result.student_feedback is None
    assert result.feedback


async def test_the_engine_overwrites_a_band_the_model_invented(settings: Settings) -> None:
    evaluator, _ = build_evaluator(settings, [reply_with("upper_secondary")])
    bound = evaluator.for_grade_level("2")
    result = await bound.grade(make_submission(), make_rubric(), make_context())
    assert result.student_feedback is not None
    assert result.student_feedback.band is FeedbackBand.EARLY_PRIMARY


async def test_feedback_volunteered_without_a_band_is_dropped_not_guessed(
    settings: Settings,
) -> None:
    evaluator, _ = build_evaluator(settings, [reply_with("lower_secondary")])
    bound = evaluator.for_grade_level(None)
    result = await bound.grade(make_submission(), make_rubric(), make_context())
    assert result.student_feedback is None
    assert result.feedback


async def test_unusable_feedback_is_dropped_and_the_grade_still_ships(
    settings: Settings,
) -> None:
    replies = [reply_with("early_primary", malformed=True)] * 2
    evaluator, runner = build_evaluator(settings, replies)
    bound = evaluator.for_grade_level("1")
    result = await bound.grade(make_submission(), make_rubric(), make_context())
    assert isinstance(result, GradingResult)
    assert result.student_feedback is None
    assert result.total_score == 3.0
    assert result.feedback
    assert len(runner.prompts) == 2


async def test_a_grade_that_is_unusable_beyond_feedback_still_raises(
    settings: Settings,
) -> None:
    evaluator, _ = build_evaluator(settings, ["{\"submission_id\": \"camila-rios\"}"] * 2)
    bound = evaluator.for_grade_level("1")
    with pytest.raises(GradingValidationError):
        await bound.grade(make_submission(), make_rubric(), make_context())


async def test_an_evaluator_without_band_support_is_returned_untouched() -> None:
    class Scripted:
        async def grade(self, submission, rubric, context):
            return make_result()

    scripted = Scripted()
    assert bind_feedback_band(scripted, "10") is scripted
    assert bind_feedback_band(None, "10") is None


async def test_binding_does_not_mutate_the_shared_evaluator(settings: Settings) -> None:
    evaluator, _ = build_evaluator(settings, [])
    primary = evaluator.for_grade_level("2")
    secondary = evaluator.for_grade_level("11")
    assert evaluator.feedback_band is None
    assert primary.feedback_band is FeedbackBand.EARLY_PRIMARY
    assert secondary.feedback_band is FeedbackBand.UPPER_SECONDARY
    assert primary.model == evaluator.model
    assert primary.variant_id == evaluator.variant_id
