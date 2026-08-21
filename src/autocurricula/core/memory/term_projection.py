from collections.abc import Sequence
from datetime import datetime

from autocurricula.core.memory.fact_store import AssessmentFactStore
from autocurricula.core.memory.persistent_memory import PersistentStore
from autocurricula.schemas.common import utc_now
from autocurricula.schemas.memory import (
    AssessmentFact,
    EpisodicStudentProfile,
    FactSource,
    TermSnapshot,
    assessment_fact_id,
)


def project_terms(
    facts: Sequence[AssessmentFact], previous: Sequence[TermSnapshot]
) -> list[TermSnapshot]:
    history = {snapshot.term: list(snapshot.risk_history) for snapshot in previous}
    grouped: dict[str, list[AssessmentFact]] = {}
    for fact in facts:
        grouped.setdefault(fact.term, []).append(fact)
    snapshots = [
        _term_snapshot(term, entries, history.get(term, []))
        for term, entries in grouped.items()
    ]
    snapshots.extend(
        snapshot for snapshot in previous if snapshot.term not in grouped
    )
    return sorted(snapshots, key=lambda snapshot: snapshot.term)


def _term_snapshot(
    term: str, facts: Sequence[AssessmentFact], risk_history: list[float]
) -> TermSnapshot:
    count = sum(fact.submissions_count for fact in facts)
    total = sum(fact.avg_percentage * fact.submissions_count for fact in facts)
    return TermSnapshot(
        term=term,
        avg_percentage=min(100.0, max(0.0, total / count)) if count else 0.0,
        submissions_count=count,
        risk_history=risk_history,
    )


HUMAN_SOURCES = (FactSource.HUMAN_APPROVAL, FactSource.HUMAN_OVERRIDE)


async def record_assessment(
    profile_store: PersistentStore,
    fact_store: AssessmentFactStore,
    *,
    student_id: str,
    job_id: str,
    term: str,
    avg_percentage: float,
    submissions_count: int,
    source: FactSource,
    recorded_at: datetime | None = None,
) -> AssessmentFact:
    fact_id = assessment_fact_id(job_id, student_id)
    if source not in HUMAN_SOURCES:
        settled = await _human_fact(fact_store, student_id, fact_id)
        if settled is not None:
            return settled
    fact = AssessmentFact(
        fact_id=fact_id,
        student_id=student_id,
        job_id=job_id,
        term=term,
        avg_percentage=avg_percentage,
        submissions_count=submissions_count,
        source=source,
        recorded_at=recorded_at if recorded_at is not None else utc_now(),
    )
    await fact_store.put(fact)
    await reproject_profile(profile_store, fact_store, student_id)
    return fact


async def _human_fact(
    fact_store: AssessmentFactStore, student_id: str, fact_id: str
) -> AssessmentFact | None:
    for fact in await fact_store.list_for_student(student_id):
        if fact.fact_id == fact_id and fact.source in HUMAN_SOURCES:
            return fact
    return None


async def reproject_profile(
    profile_store: PersistentStore,
    fact_store: AssessmentFactStore,
    student_id: str,
) -> EpisodicStudentProfile:
    facts = await fact_store.list_for_student(student_id)
    profile = await profile_store.get_profile(student_id)
    previous = profile.terms if profile is not None else []
    projected = EpisodicStudentProfile(
        student_id=student_id, terms=project_terms(facts, previous)
    )
    await profile_store.put_profile(projected)
    return projected
