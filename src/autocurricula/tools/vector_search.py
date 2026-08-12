import inspect
from typing import Any, Protocol

from autocurricula.schemas.memory import RetrievedChunk, RetrievedContext
from autocurricula.tools.base import ToolResult

DEFAULT_TOP_K = 5


class VectorSearchProvider(Protocol):
    async def search(
        self, query: str, top_k: int = DEFAULT_TOP_K
    ) -> RetrievedContext: ...


class MemoryVectorProvider:
    def __init__(self, memory: Any) -> None:
        self._memory = memory

    async def search(
        self, query: str, top_k: int = DEFAULT_TOP_K
    ) -> RetrievedContext:
        vector_memory = getattr(self._memory, "l2", self._memory)
        outcome = vector_memory.search(query=query, top_k=top_k)
        if inspect.isawaitable(outcome):
            outcome = await outcome
        if isinstance(outcome, RetrievedContext):
            return outcome
        chunks = [chunk for chunk in outcome if isinstance(chunk, RetrievedChunk)]
        return RetrievedContext(query=query, chunks=chunks)


def _resolve_provider(provider: Any) -> VectorSearchProvider:
    if hasattr(provider, "search"):
        return provider
    return MemoryVectorProvider(memory=provider)


async def search_rubrics(
    query: str,
    subject: str = "",
    top_k: int = DEFAULT_TOP_K,
    provider: Any = None,
) -> RetrievedContext:
    if provider is None:
        raise ValueError("a vector search provider is required")
    effective_query = " ".join(part for part in (subject, query) if part)
    return await _resolve_provider(provider).search(query=effective_query, top_k=top_k)


async def search_competencies(
    query: str,
    subject: str = "",
    grade_level: str = "",
    top_k: int = DEFAULT_TOP_K,
    provider: Any = None,
) -> RetrievedContext:
    if provider is None:
        raise ValueError("a vector search provider is required")
    effective_query = " ".join(
        part for part in (subject, grade_level, query) if part
    )
    return await _resolve_provider(provider).search(query=effective_query, top_k=top_k)


def retrieved_context_to_result(context: RetrievedContext) -> ToolResult:
    return ToolResult.success(
        payload={
            "query": context.query,
            "chunks": [chunk.model_dump(mode="json") for chunk in context.chunks],
        }
    )
