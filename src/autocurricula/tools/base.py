from collections.abc import Callable
from typing import Any, Self

from pydantic import Field, model_validator

from autocurricula.schemas.common import StrictBaseModel


class ToolResult(StrictBaseModel):
    ok: bool = True
    error: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _error_matches_status(self) -> Self:
        if self.ok and self.error is not None:
            raise ValueError("error must be None when ok is true")
        if not self.ok and (self.error is None or not self.error.strip()):
            raise ValueError("a non-empty error is required when ok is false")
        return self

    @classmethod
    def success(cls, payload: dict[str, Any] | None = None) -> Self:
        return cls(ok=True, error=None, payload=payload if payload is not None else {})

    @classmethod
    def failure(cls, error: str) -> Self:
        return cls(ok=False, error=error, payload={})


def as_function_tool(func: Callable[..., Any]) -> Any:
    try:
        from google.adk.tools import FunctionTool
    except ImportError:
        return func
    try:
        return FunctionTool(func=func)
    except Exception:
        return func
