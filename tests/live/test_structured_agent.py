import pytest
from pydantic import BaseModel, Field

from autocurricula.agents.adk_llm import build_structured_agent, run_structured_output
from autocurricula.config.settings import Settings
from tests.live.guard import live_only

pytestmark = [pytest.mark.live, live_only]

PROBE_APP_NAME = "gradesync_live_probe"
PROBE_INSTRUCTION = (
    "You classify a single K-12 exam question. "
    "Return only a JSON object with keys topic and difficulty. "
    "topic is a short subject label; difficulty is an integer from 1 to 5."
)


class QuestionProbe(BaseModel):
    topic: str = Field(min_length=1)
    difficulty: int = Field(ge=1, le=5)


async def test_structured_agent_round_trip(live_settings: Settings) -> None:
    agent = build_structured_agent(
        name="live_question_probe",
        model=live_settings.gemini_flash_model,
        instruction=PROBE_INSTRUCTION,
        output_schema=QuestionProbe,
        temperature=0.0,
    )
    result = await run_structured_output(
        agent=agent,
        payload="Question: factor x^2 + x - 6 into two binomials.",
        schema=QuestionProbe,
        app_name=PROBE_APP_NAME,
    )
    assert isinstance(result, QuestionProbe)
    assert result.topic.strip()
    assert 1 <= result.difficulty <= 5
