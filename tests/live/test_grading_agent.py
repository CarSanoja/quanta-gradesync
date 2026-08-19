import re
from pathlib import Path

import pytest

from autocurricula.agents.grading_agent import AdkGradingEvaluator
from autocurricula.config.settings import Settings
from autocurricula.schemas.grading import GradingResult
from tests.live.exam_fixtures import (
    CRITERION_ID,
    MAX_SCORE,
    SUBMISSION_ID,
    build_context,
    build_rubric,
    build_submission,
)
from tests.live.exam_image import ANSWER_LINES
from tests.live.guard import live_only

pytestmark = [pytest.mark.live, live_only]

_NOISE = re.compile(r"[^a-z0-9+\-()^=]")


def normalize(text: str) -> str:
    lowered = text.lower().replace("²", "^2").replace("−", "-")
    return _NOISE.sub("", lowered)


def page_text() -> str:
    return normalize(" ".join(ANSWER_LINES))


def quote_is_grounded(quote: str) -> bool:
    normalized = normalize(quote)
    return bool(normalized) and normalized in page_text()


async def test_grading_agent_grades_real_exam_image(
    live_settings: Settings, answer_sheet_path: Path
) -> None:
    evaluator = AdkGradingEvaluator(live_settings)
    rubric = build_rubric()
    result = await evaluator.grade(
        build_submission(answer_sheet_path), rubric, build_context()
    )
    assert isinstance(result, GradingResult)
    assert result.submission_id == SUBMISSION_ID
    assert [score.criterion_id for score in result.criterion_scores] == [CRITERION_ID]
    criterion = result.criterion_scores[0]
    assert 0.0 <= criterion.score <= MAX_SCORE
    assert 0.0 <= criterion.confidence <= 1.0
    assert result.feedback.strip()
    assert criterion.evidence, "grading result carried no evidence spans"
    for span in criterion.evidence:
        assert span.page == 1
    grounded = [span.quote for span in criterion.evidence if quote_is_grounded(span.quote)]
    assert grounded, f"no evidence quote matched the rendered page: {criterion.evidence}"
