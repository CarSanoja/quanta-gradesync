from autocurricula.config.settings import Settings
from autocurricula.core.memory.manager import MemoryManager
from autocurricula.schemas.memory import (
    EpisodicStudentProfile,
    FactSource,
    TermSnapshot,
)
from tests.core_memory.fact_builders import STUDENT, TERM, persist, snapshot


async def test_two_assessments_in_one_month_both_survive(settings: Settings) -> None:
    manager = MemoryManager.from_settings(settings)

    await persist(manager, "job-parcial-1", 82.0)
    await persist(manager, "job-parcial-2", 62.0)

    term = await snapshot(manager)
    assert term.submissions_count == 2
    assert term.avg_percentage == 72.0
    facts = await manager.fact_store.list_for_student(STUDENT)
    assert [fact.job_id for fact in facts] == ["job-parcial-1", "job-parcial-2"]
    assert {fact.source for fact in facts} == {FactSource.BATCH_SYNC}


async def test_redelivery_of_the_same_job_does_not_double_count(
    settings: Settings,
) -> None:
    manager = MemoryManager.from_settings(settings)

    await persist(manager, "job-parcial-1", 82.0)
    await persist(manager, "job-parcial-1", 82.0)

    term = await snapshot(manager)
    assert term.submissions_count == 1
    assert term.avg_percentage == 82.0
    assert len(await manager.fact_store.list_for_student(STUDENT)) == 1


async def test_human_approval_is_not_erased_by_a_later_batch(
    settings: Settings,
) -> None:
    manager = MemoryManager.from_settings(settings)

    await persist(manager, "job-parcial-1", 82.0)
    await manager.persist_student_percentage(
        student_id=STUDENT,
        term=TERM,
        percentage=79.0,
        job_id="job-parcial-1-review",
        source=FactSource.HUMAN_APPROVAL,
    )
    await persist(manager, "job-parcial-2", 61.0)

    term = await snapshot(manager)
    assert term.submissions_count == 3
    assert term.avg_percentage == (82.0 + 79.0 + 61.0) / 3
    facts = await manager.fact_store.list_for_student(STUDENT)
    sources = {fact.job_id: fact.source for fact in facts}
    assert sources["job-parcial-1-review"] == FactSource.HUMAN_APPROVAL
    assert sources["job-parcial-2"] == FactSource.BATCH_SYNC


async def test_repeated_approval_of_the_same_review_is_idempotent(
    settings: Settings,
) -> None:
    manager = MemoryManager.from_settings(settings)

    for _ in range(3):
        await manager.persist_student_percentage(
            student_id=STUDENT,
            term=TERM,
            percentage=79.0,
            job_id="job-parcial-1-review",
            source=FactSource.HUMAN_APPROVAL,
        )

    term = await snapshot(manager)
    assert term.submissions_count == 1
    assert term.avg_percentage == 79.0


async def test_projection_preserves_risk_history_and_untouched_terms(
    settings: Settings,
) -> None:
    manager = MemoryManager.from_settings(settings)
    await manager.persistent_store.put_profile(
        EpisodicStudentProfile(
            student_id=STUDENT,
            terms=[
                TermSnapshot(
                    term="term-2026-07",
                    avg_percentage=90.0,
                    submissions_count=2,
                    risk_history=[0.1, 0.2],
                ),
                TermSnapshot(
                    term=TERM,
                    avg_percentage=50.0,
                    submissions_count=1,
                    risk_history=[0.7],
                ),
            ],
        )
    )

    await persist(manager, "job-parcial-2", 60.0)

    profile = await manager.persistent_store.get_profile(STUDENT)
    assert profile is not None
    by_term = {term.term: term for term in profile.terms}
    assert by_term["term-2026-07"].avg_percentage == 90.0
    assert by_term["term-2026-07"].submissions_count == 2
    assert by_term[TERM].risk_history == [0.7]
    assert by_term[TERM].submissions_count == 1
    assert by_term[TERM].avg_percentage == 60.0


async def test_facts_survive_a_fresh_store_instance(settings: Settings) -> None:
    manager = MemoryManager.from_settings(settings)
    await persist(manager, "job-parcial-1", 82.0)

    reloaded = MemoryManager.from_settings(settings)
    await persist(reloaded, "job-parcial-2", 62.0)

    term = await snapshot(reloaded)
    assert term.submissions_count == 2
    assert term.avg_percentage == 72.0


async def test_a_redelivered_batch_cannot_overwrite_a_human_decision(
    settings: Settings,
) -> None:
    manager = MemoryManager.from_settings(settings)

    await manager.persist_student_percentage(
        student_id=STUDENT,
        term=TERM,
        percentage=79.0,
        job_id="job-parcial-1",
        source=FactSource.HUMAN_OVERRIDE,
    )
    await persist(manager, "job-parcial-1", 41.0)

    term = await snapshot(manager)
    assert term.submissions_count == 1
    assert term.avg_percentage == 79.0
    facts = await manager.fact_store.list_for_student(STUDENT)
    assert [fact.source for fact in facts] == [FactSource.HUMAN_OVERRIDE]


async def test_a_human_decision_still_supersedes_its_own_machine_fact(
    settings: Settings,
) -> None:
    manager = MemoryManager.from_settings(settings)

    await persist(manager, "job-parcial-1", 41.0)
    await manager.persist_student_percentage(
        student_id=STUDENT,
        term=TERM,
        percentage=79.0,
        job_id="job-parcial-1",
        source=FactSource.HUMAN_OVERRIDE,
    )

    term = await snapshot(manager)
    assert term.submissions_count == 1
    assert term.avg_percentage == 79.0
