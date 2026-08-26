import json
import logging
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import StatusCode

from autocurricula.config.settings import Settings
from autocurricula.core.telemetry.live_context import get_scope
from autocurricula.schemas.live_events import LiveEventKind, LiveEventStatus, LlmExchange

logger = logging.getLogger(__name__)

LLM_SPAN_NAME = "call_llm"
ATTR_REQUEST = "gcp.vertex.agent.llm_request"
ATTR_RESPONSE = "gcp.vertex.agent.llm_response"
ATTR_MODEL = "gen_ai.request.model"
ATTR_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
ATTR_FINISH_REASONS = "gen_ai.response.finish_reasons"


def is_llm_span(name: str) -> bool:
    return name == LLM_SPAN_NAME


def _text_of(parts: Any) -> str:
    if not isinstance(parts, list):
        return ""
    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(text for text in texts if isinstance(text, str) and text)


def _loads(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        payload = json.loads(value)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def request_text(raw: Any) -> str:
    contents = _loads(raw).get("contents")
    if not isinstance(contents, list) or not contents:
        return ""
    last = contents[-1]
    return _text_of(last.get("parts")) if isinstance(last, dict) else ""


def response_text(raw: Any) -> str:
    content = _loads(raw).get("content")
    return _text_of(content.get("parts")) if isinstance(content, dict) else ""


def _count(attributes: Any, key: str) -> int:
    value = attributes.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def _finish_reason(attributes: Any) -> str:
    value = attributes.get(ATTR_FINISH_REASONS)
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    return ""


class LlmSpanCapture(SpanProcessor):
    def __init__(self, settings: Settings) -> None:
        self._max_chars = settings.telemetry_payload_max_chars

    def on_end(self, span: ReadableSpan) -> None:
        try:
            self._handle(span)
        except Exception as error:
            logger.debug("llm span capture failed: %s", error)

    def _handle(self, span: ReadableSpan) -> None:
        name = span.name or ""
        if not is_llm_span(name):
            return
        scope = get_scope()
        if scope is None:
            return
        attributes = dict(span.attributes or {})
        exchange, truncated = self._exchange(attributes)
        status = LiveEventStatus.OK
        if span.status is not None and span.status.status_code is StatusCode.ERROR:
            status = LiveEventStatus.ERROR
        scope.emit(
            kind=LiveEventKind.LLM_CALL,
            name=name,
            status=status,
            llm=exchange,
            attributes={
                "gen_ai.request.model": exchange.model,
                "gen_ai.usage.tokens": exchange.total_tokens,
                "payload.truncated": truncated,
            },
        )

    def _exchange(self, attributes: dict[str, Any]) -> tuple[LlmExchange, bool]:
        request, request_cut = self._clip(request_text(attributes.get(ATTR_REQUEST)))
        response, response_cut = self._clip(response_text(attributes.get(ATTR_RESPONSE)))
        input_tokens = _count(attributes, ATTR_INPUT_TOKENS)
        output_tokens = _count(attributes, ATTR_OUTPUT_TOKENS)
        total_tokens = _count(attributes, ATTR_TOTAL_TOKENS) or input_tokens + output_tokens
        model = attributes.get(ATTR_MODEL)
        truncated = request_cut or response_cut
        exchange = LlmExchange(
            model=str(model) if model else "",
            request_excerpt=request,
            response_excerpt=response,
            finish_reason=_finish_reason(attributes),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            truncated=truncated,
        )
        return exchange, truncated

    def _clip(self, text: str) -> tuple[str, bool]:
        if len(text) <= self._max_chars:
            return text, False
        return text[: self._max_chars], True
