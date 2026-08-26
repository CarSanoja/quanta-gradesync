from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any

from autocurricula.schemas.telemetry import ATTR_AGENT_ID

STUDENT_ID_KEY = "student_id"
SCOPE_KEYS = frozenset({ATTR_AGENT_ID, STUDENT_ID_KEY})


def _discard(**fields: Any) -> None:
    return None


@dataclass
class LiveScope:
    job_id: str
    trace_id: str
    emit: Callable[..., None] = _discard
    next_seq: Callable[[], int] = int
    stage: str | None = None
    agent_id: str | None = None
    student_id: str | None = None
    span_id: str | None = None


current_live_scope: ContextVar[LiveScope | None] = ContextVar(
    "autocurricula_live_scope", default=None
)


def get_scope() -> LiveScope | None:
    return current_live_scope.get()


def push_scope(scope: LiveScope) -> Token[LiveScope | None]:
    return current_live_scope.set(scope)


def reset_scope(token: Token[LiveScope | None] | None) -> None:
    if token is None:
        return
    try:
        current_live_scope.reset(token)
    except ValueError:
        current_live_scope.set(None)


def update_scope(key: str, value: Any) -> None:
    scope = current_live_scope.get()
    if scope is None or not isinstance(value, str) or not value:
        return
    if key == ATTR_AGENT_ID:
        scope.agent_id = value
    elif key == STUDENT_ID_KEY:
        scope.student_id = value
