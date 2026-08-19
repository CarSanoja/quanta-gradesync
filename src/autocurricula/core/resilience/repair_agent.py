import inspect
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

DEFAULT_REPAIR_BUDGET = 2


class RepairBudgetExhausted(Exception):
    def __init__(self, attempts: int, cause: Exception) -> None:
        super().__init__(
            f"schema repair budget exhausted after {attempts} attempt(s): "
            f"{type(cause).__name__}: {cause}"
        )
        self.attempts = attempts
        self.cause = cause


class SchemaRepairAgent:
    def __init__(self, budget: int = DEFAULT_REPAIR_BUDGET) -> None:
        if budget < 0:
            raise ValueError("repair budget must be non-negative")
        self._budget = budget
        self.last_attempts = 0

    @property
    def budget(self) -> int:
        return self._budget

    async def run(self, operation: Callable[[], Awaitable[T]]) -> T:
        attempts = 0
        last_error: Exception | None = None
        while attempts <= self._budget:
            try:
                result = await _call(operation, attempts)
                self.last_attempts = attempts
                return result
            except ValueError as error:
                last_error = error
                attempts += 1
        self.last_attempts = attempts
        raise RepairBudgetExhausted(attempts, last_error)


async def _call(operation: Callable[[], Awaitable[T]], attempt: int) -> T:
    try:
        parameters = inspect.signature(operation).parameters
    except (TypeError, ValueError):
        return await operation()
    if "attempt" in parameters:
        return await operation(attempt)
    return await operation()
