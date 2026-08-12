from typing import Any, TypeVar

from pydantic import BaseModel

from autocurricula.agents.base import (
    AgentResponseError,
    make_user_content,
    run_agent_for_text,
    structured_output_with_retry,
    text_part,
)

TModel = TypeVar("TModel", bound=BaseModel)

DEFAULT_TEMPERATURE = 0.1


class StructuredLlmError(AgentResponseError):
    pass


def build_structured_agent(
    *,
    name: str,
    model: str,
    instruction: str,
    output_schema: type[TModel],
    temperature: float = DEFAULT_TEMPERATURE,
) -> Any:
    if not name.strip():
        raise ValueError("agent name must not be blank")
    if not model.strip():
        raise ValueError("model must not be blank")
    from google.adk.agents import LlmAgent

    return LlmAgent(
        name=name,
        model=model,
        instruction=instruction,
        output_schema=output_schema,
        temperature=temperature,
    )


def _error(message: str, raw: str, cause: Exception) -> StructuredLlmError:
    return StructuredLlmError(message, raw=raw, cause=cause)


async def run_structured_output(
    *,
    agent: Any,
    payload: str,
    schema: type[TModel],
    app_name: str,
    user_id: str = "autocurricula",
) -> TModel:
    if not payload.strip():
        raise StructuredLlmError("structured LLM payload must not be blank")
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService

    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=app_name, user_id=user_id)
    runner = Runner(agent=agent, app_name=app_name, session_service=session_service)

    async def call(repair: str | None) -> str:
        parts = [text_part(payload)]
        if repair is not None:
            parts.append(text_part(repair))
        message = make_user_content(parts)
        return await run_agent_for_text(runner, user_id, session.id, message)

    return await structured_output_with_retry(call, schema, _error)
