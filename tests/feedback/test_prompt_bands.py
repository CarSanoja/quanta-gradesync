import pytest

from autocurricula.agents.prompts.feedback_bands import (
    BAND_RULES,
    FEEDBACK_CONTRACT,
    band_task_block,
    feedback_section,
)
from autocurricula.agents.prompts.grading_few_shots import GRADING_FEW_SHOTS_V1
from autocurricula.agents.prompts.grading_prompts import (
    GRADING_SYSTEM_INSTRUCTION_V1,
    build_grading_prompt_variant,
)
from autocurricula.schemas.feedback import FeedbackBand

PERSON_PRAISE = ("smart", "clever", "brilliant", "gifted", "talented")
EMPTY_PRAISE = ("Great job", "Well done", "Keep it up", "Nice work")


@pytest.mark.parametrize("band", list(FeedbackBand))
def test_every_band_has_its_own_register_rules(band: FeedbackBand) -> None:
    rules = BAND_RULES[band]
    assert band.value in rules
    assert "next_step" in rules
    assert "headline" in rules


def test_register_rules_differ_between_the_youngest_and_the_oldest_band() -> None:
    early = BAND_RULES[FeedbackBand.EARLY_PRIMARY]
    late = BAND_RULES[FeedbackBand.UPPER_SECONDARY]
    assert early != late
    assert "at most 10 words" in early
    assert "no length ceiling" in late
    assert "no self-monitoring" in early
    assert "self-regulation" in late


def test_the_contract_forbids_the_named_failure_modes() -> None:
    for word in PERSON_PRAISE:
        assert word in FEEDBACK_CONTRACT
    for phrase in EMPTY_PRAISE:
        assert phrase in FEEDBACK_CONTRACT
    assert "Exactly one next_step" in FEEDBACK_CONTRACT
    assert "never as a deficit label" in FEEDBACK_CONTRACT
    assert "criterion id" in FEEDBACK_CONTRACT
    assert "never shown to the student" in FEEDBACK_CONTRACT
    assert "Never invent work" in FEEDBACK_CONTRACT
    assert "Never praise handwriting, neatness, effort" in FEEDBACK_CONTRACT
    assert "next_step acts on one of the growth points" in FEEDBACK_CONTRACT
    assert "generic habit that would fit any exam" in FEEDBACK_CONTRACT


def test_the_system_instruction_carries_the_contract_and_all_four_bands() -> None:
    assert FEEDBACK_CONTRACT in GRADING_SYSTEM_INSTRUCTION_V1
    for band in FeedbackBand:
        assert band.value in GRADING_SYSTEM_INSTRUCTION_V1
    assert "student_feedback" in GRADING_SYSTEM_INSTRUCTION_V1
    assert feedback_section() in GRADING_SYSTEM_INSTRUCTION_V1


@pytest.mark.parametrize("band", list(FeedbackBand))
def test_the_task_block_names_one_band_and_is_self_sufficient(band: FeedbackBand) -> None:
    block = band_task_block(band)
    assert f"STUDENT FEEDBACK BAND FOR THIS SUBMISSION: {band.value}" in block
    assert BAND_RULES[band] in block
    assert FEEDBACK_CONTRACT in block
    others = [other for other in FeedbackBand if other is not band]
    for other in others:
        assert BAND_RULES[other] not in block


def test_the_task_block_states_that_the_engine_derived_the_band() -> None:
    block = band_task_block(FeedbackBand.UPPER_PRIMARY)
    assert "The engine derived this band" in block
    assert "never infer, change or guess it" in FEEDBACK_CONTRACT


def test_the_worked_examples_show_student_feedback_in_two_registers() -> None:
    variant = build_grading_prompt_variant()
    assert variant.few_shots == list(GRADING_FEW_SHOTS_V1)
    joined = "\n".join(GRADING_FEW_SHOTS_V1)
    assert '"student_feedback"' in joined
    assert '"band": "upper_secondary"' in joined
    assert '"band": "early_primary"' in joined
    assert '"teacher_note"' in joined
    lowered = joined.lower()
    for word in PERSON_PRAISE:
        assert word not in lowered
    for phrase in EMPTY_PRAISE:
        assert phrase.lower() not in lowered
