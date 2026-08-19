from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass
class UsageLedger:
    parent: "UsageLedger | None" = None
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0

    def add(self, input_tokens: int, output_tokens: int, total_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.total_tokens += total_tokens
        if self.parent is not None:
            self.parent.add(input_tokens, output_tokens, total_tokens)


_current_ledger: ContextVar[UsageLedger | None] = ContextVar(
    "autocurricula_usage_ledger", default=None
)


@contextmanager
def usage_scope() -> Iterator[UsageLedger]:
    ledger = UsageLedger(parent=_current_ledger.get())
    token = _current_ledger.set(ledger)
    try:
        yield ledger
    finally:
        _current_ledger.reset(token)


def _count(metadata: Any, name: str) -> int:
    value = getattr(metadata, name, None)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0
    return int(value)


def record_usage(metadata: Any) -> None:
    ledger = _current_ledger.get()
    if ledger is None or metadata is None:
        return
    input_tokens = _count(metadata, "prompt_token_count")
    output_tokens = _count(metadata, "candidates_token_count") + _count(
        metadata, "thoughts_token_count"
    )
    total_tokens = _count(metadata, "total_token_count") or (
        input_tokens + output_tokens
    )
    if not (input_tokens or output_tokens or total_tokens):
        return
    ledger.add(input_tokens, output_tokens, total_tokens)


def record_event_usage(event: Any) -> None:
    if getattr(event, "partial", False):
        return
    record_usage(getattr(event, "usage_metadata", None))
