import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal, TypeVar

from pydantic import BaseModel

from autocurricula.config.settings import Settings

ModelAttr = Literal["gemini_pro_model", "gemini_flash_model"]
DEFAULT_REPAIR_TEMPLATE = (
    "Your previous response failed validation: {error}\n"
    "Return only a corrected JSON object that satisfies the required output schema."
)

ModelT = TypeVar("ModelT", bound=BaseModel)
CallFn = Callable[[str | None], Awaitable[str]]
ErrorFactory = Callable[[str, str, Exception], Exception]


class AgentResponseError(ValueError):
    def __init__(
        self, message: str, raw: str = "", cause: Exception | None = None
    ) -> None:
        super().__init__(message)
        self.raw = raw
        self.cause = cause


def resolve_model(settings: Settings, model_attr: ModelAttr = "gemini_pro_model") -> str:
    value = getattr(settings, model_attr)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"settings.{model_attr} must be a non-empty model name")
    return value.strip()


def strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    return cleaned.strip()


def parse_model_json(text: str) -> Any:
    cleaned = strip_code_fences(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    candidate = cleaned if start < 0 else cleaned[start : end + 1]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as error:
        raise AgentResponseError(
            f"agent response is not valid JSON: {error}", raw=text, cause=error
        ) from error


def text_part(text: str) -> Any:
    from google.genai import types as genai_types

    return genai_types.Part.from_text(text=text)


async def inline_file_part(
    local_path: str, mime_type: str, *, max_bytes: int
) -> Any | None:
    from google.genai import types as genai_types

    path = Path(local_path)
    try:
        stat = await asyncio.to_thread(path.stat)
    except OSError:
        return None
    if stat.st_size <= 0 or stat.st_size > max_bytes:
        return None
    data = await asyncio.to_thread(path.read_bytes)
    return genai_types.Part.from_bytes(data=data, mime_type=mime_type)


def make_user_content(parts: Sequence[Any]) -> Any:
    from google.genai import types as genai_types

    return genai_types.Content(role="user", parts=list(parts))


def event_text(event: Any) -> str:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    chunks: list[str] = []
    for part in parts:
        value = getattr(part, "text", None)
        if isinstance(value, str) and value.strip():
            chunks.append(value)
    return "".join(chunks)


async def run_agent_for_text(
    runner: Any, user_id: str, session_id: str, message: Any
) -> str:
    from autocurricula.core.telemetry.usage import record_event_usage

    events = []
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=message
    ):
        record_event_usage(event)
        events.append(event)
    for event in reversed(events):
        text = event_text(event)
        if text:
            return text
    raise AgentResponseError("agent produced no textual response", raw="")


async def structured_output_with_retry(
    call: CallFn,
    output_model: type[ModelT],
    error_factory: ErrorFactory,
    *,
    build_repair: Callable[[str], str] | None = None,
    attempts: int = 2,
) -> ModelT:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    detail = ""
    last_error: Exception | None = None
    last_raw = ""
    for _ in range(attempts):
        try:
            raw = await call(detail if detail else None)
            last_raw = raw
            return output_model.model_validate(parse_model_json(raw))
        except ValueError as error:
            last_error = error
            detail = (
                build_repair(str(error))
                if build_repair is not None
                else DEFAULT_REPAIR_TEMPLATE.format(error=error)
            )
    raise error_factory(
        f"structured output failed after {attempts} attempt(s)",
        last_raw,
        last_error if last_error is not None else RuntimeError("no attempt completed"),
    )
