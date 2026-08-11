from __future__ import annotations

from typing import Any

from autocurricula.config.settings import Settings
from autocurricula.core.memory.outcome_writers import (
    merge_student_percentage,
    write_class_snapshots,
    write_profiles,
)
from autocurricula.core.memory.persistent_memory import (
    PersistentStore,
    build_persistent_store,
)
from autocurricula.core.memory.session_memory import SessionMemory
from autocurricula.core.memory.vector_memory import (
    VectorDoc,
    VectorMemory,
    build_vector_memory,
)
from autocurricula.schemas.common import JobId
from autocurricula.schemas.exam import ExamBatch
from autocurricula.schemas.grading import GradingBatchResult
from autocurricula.schemas.memory import (
    EpisodicStudentProfile,
    RetrievedContext,
)
from autocurricula.schemas.rubric import Rubric

_RUBRIC_CONTEXT_TOP_K = 5


def _rubric_query_text(subject: str, rubric: Rubric) -> str:
    parts = [subject, rubric.subject]
    parts.extend(criterion.description for criterion in rubric.criteria)
    return " ".join(part for part in parts if part)


def _rubric_document(rubric: Rubric) -> VectorDoc:
    body = " ".join(
        " ".join(
            [f"{criterion.criterion_id}: {criterion.description}"]
            + [f"{level}: {text}" for level, text in criterion.mastery_descriptions.items()]
        )
        for criterion in rubric.criteria
    )
    metadata: dict[str, Any] = {
        "source": rubric.rubric_id,
        "subject": rubric.subject,
        "version": rubric.version,
    }
    return rubric.rubric_id, body, metadata


class VectorSearchFacade:
    def __init__(self, vector_memory: VectorMemory, default_top_k: int = 5) -> None:
        self._vector_memory = vector_memory
        self._default_top_k = default_top_k

    async def search(self, query: str, top_k: int | None = None) -> RetrievedContext:
        effective_top_k = top_k if top_k is not None else self._default_top_k
        chunks = await self._vector_memory.query(query, top_k=effective_top_k)
        return RetrievedContext(query=query, chunks=chunks)


class MemoryManager:
    def __init__(
        self, vector_memory: VectorMemory, persistent_store: PersistentStore
    ) -> None:
        self._vector_memory = vector_memory
        self._persistent_store = persistent_store
        self._l2 = VectorSearchFacade(vector_memory)

    @classmethod
    def from_settings(cls, settings: Settings) -> MemoryManager:
        return cls(
            vector_memory=build_vector_memory(settings),
            persistent_store=build_persistent_store(settings),
        )

    @property
    def vector_memory(self) -> VectorMemory:
        return self._vector_memory

    @property
    def persistent_store(self) -> PersistentStore:
        return self._persistent_store

    @property
    def l2(self) -> VectorSearchFacade:
        return self._l2

    @property
    def l3(self) -> PersistentStore:
        return self._persistent_store

    def new_session(self, job_id: JobId, batch: ExamBatch | None = None) -> SessionMemory:
        return SessionMemory(job_id=job_id, batch=batch)

    async def retrieve_rubric_context(
        self, rubric: Rubric, subject: str
    ) -> RetrievedContext:
        await self._vector_memory.upsert([_rubric_document(rubric)])
        query = _rubric_query_text(subject, rubric)
        return await self._l2.search(query, top_k=_RUBRIC_CONTEXT_TOP_K)

    async def load_student_history(
        self, student_id: str
    ) -> EpisodicStudentProfile | None:
        return await self._persistent_store.get_profile(student_id)

    async def persist_student_percentage(
        self, student_id: str, term: str, percentage: float
    ) -> None:
        await merge_student_percentage(
            self._persistent_store, student_id, term, percentage
        )

    async def persist_outcomes(
        self,
        batch: ExamBatch,
        batch_result: GradingBatchResult,
        term: str,
        rubric: Rubric | None = None,
    ) -> int:
        written = await write_profiles(
            self._persistent_store, batch, batch_result, term
        )
        if rubric is not None:
            written += await write_class_snapshots(
                self._persistent_store, batch, batch_result, rubric
            )
        return written
