from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_MAX_CALLS_PER_ITEM = 4
DEFAULT_SCHEMA_REPAIR_ATTEMPTS = 2


class BudgetExceeded(Exception):
    pass


class ItemBudget:
    def __init__(
        self,
        max_calls: int = DEFAULT_MAX_CALLS_PER_ITEM,
        schema_repair_attempts: int = DEFAULT_SCHEMA_REPAIR_ATTEMPTS,
    ) -> None:
        if max_calls < 1:
            raise ValueError("max_calls must be at least 1")
        if schema_repair_attempts < 0:
            raise ValueError("schema_repair_attempts must be non-negative")
        self._max_calls = max_calls
        self._schema_repair_attempts = schema_repair_attempts
        self._calls = 0

    @property
    def max_calls(self) -> int:
        return self._max_calls

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def schema_repair_attempts(self) -> int:
        return self._schema_repair_attempts

    def record_call(self) -> None:
        self._calls += 1
        if self._calls > self._max_calls:
            raise BudgetExceeded(
                f"item budget exceeded: {self._calls} calls > {self._max_calls}"
            )


async def guard_item(
    operation: Callable[[], Awaitable[T]],
    budget: ItemBudget,
) -> T:
    budget.record_call()
    return await operation()
