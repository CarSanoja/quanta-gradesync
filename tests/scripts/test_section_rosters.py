import sys
from collections import Counter
from pathlib import Path

import pytest

sys.path.insert(0, str(Path("scripts").resolve()))

from sample_batch.lots import SECTION_LOTS, SECTION_ROSTERS
from sample_batch.roster_demo import RAW_PROFILES
from sample_batch.roster_sections import section_profiles
from sample_batch.rosters import ROSTER_NAMES, profiles_for
from sample_batch.section_names import SECTION_NAMES

SECTIONS = ("10A", "10B", "10C")


def test_the_three_sections_carry_more_than_a_hundred_papers() -> None:
    """The number is the argument: one lot of 36 reads like an afternoon."""
    total = sum(len(section_profiles(section)) for section in SECTIONS)

    assert total == 108
    assert all(len(section_profiles(section)) == 36 for section in SECTIONS)


def test_no_student_appears_in_two_sections() -> None:
    """student_id is the key in the SIS ledger; a repeat would overwrite a grade."""
    ids = [profile.student_id for section in SECTIONS for profile in section_profiles(section)]

    assert len(ids) == len(set(ids)) == 108
    names = [name for roster in SECTION_NAMES.values() for name in roster]
    assert len(names) == len(set(names)) == 108


def test_every_section_carries_its_own_trouble() -> None:
    """A teacher does not get an easy section.

    Grading one clean batch proves less than surviving the same four refusals
    three times, so each section keeps its own injection, authority note and
    pair of unreadable pages.
    """
    for section in SECTIONS:
        expected = Counter(profile.expected for profile in section_profiles(section))
        assert expected["auto-sync"] == 32, section
        assert expected["hold - illegible scan"] == 2, section
        assert expected["hold - armor"] == 2, section


def test_a_section_is_not_another_one_with_the_names_swapped() -> None:
    """Same paper, so the same answers — but never the same rendered page."""
    for left, right in (("10A", "10B"), ("10B", "10C"), ("10A", "10C")):
        a, b = section_profiles(left), section_profiles(right)
        assert [p.ink for p in a] != [p.ink for p in b], (left, right)
        assert [p.tilt for p in a] != [p.tilt for p in b], (left, right)


def test_the_section_lots_never_collide_with_the_existing_fixtures() -> None:
    """reference and demo both use Parcial1; a shared lot code shares a bucket."""
    codes = {name: SECTION_LOTS[name].lot_code for name in SECTION_ROSTERS}

    assert set(codes.values()) == {
        "2026_Matematicas_10A_Parcial2",
        "2026_Matematicas_10B_Parcial2",
        "2026_Matematicas_10C_Parcial2",
    }
    assert all("Parcial 2" in SECTION_LOTS[name].header_line for name in SECTION_ROSTERS)


def test_the_sections_are_reachable_through_the_roster_registry() -> None:
    for name in SECTION_ROSTERS:
        assert name in ROSTER_NAMES
        assert len(profiles_for(name)) == 36


def test_a_roster_that_does_not_match_the_paper_count_fails_loudly() -> None:
    """Silently zipping to the shorter list would drop papers with no warning."""
    original = SECTION_NAMES["10A"]
    SECTION_NAMES["10A"] = original[:10]
    try:
        with pytest.raises(ValueError, match="10 names for"):
            section_profiles("10A")
    finally:
        SECTION_NAMES["10A"] = original


def test_the_paper_count_is_the_one_the_script_says_out_loud() -> None:
    """108 and 96 are spoken in the video; they come from here."""
    assert len(RAW_PROFILES) * 3 == 108
    synced = sum(
        1
        for section in SECTIONS
        for profile in section_profiles(section)
        if profile.expected == "auto-sync"
    )
    assert synced == 96


def test_the_three_sections_share_one_bucket_root() -> None:
    """A bucket root holds many batch prefixes — that is what a bucket is.

    Giving each section its own root buried the pages four directories down and
    made three sibling lots look like three unrelated exports.
    """
    import generate_sample_batch as generator

    roots = {generator.DEFAULT_TARGETS[name] for name in SECTION_ROSTERS}

    assert roots == {generator.VIDEO_ROOT}
    assert generator.DEFAULT_TARGETS["demo"] == generator.VIDEO_ROOT


def test_a_shared_root_names_each_lots_artefacts_after_its_lot() -> None:
    """Unsuffixed, the second section silently overwrote the first one's notes."""
    import generate_sample_batch as generator

    lot = SECTION_LOTS["section-10a"]
    assert generator.artefact_name("demo-notes", ".md", lot, True) == "demo-notes-10A.md"
    assert generator.artefact_name("push-event", ".json", lot, True) == "push-event-10A.json"
    # A roster that owns its root keeps the plain name it always had.
    assert generator.artefact_name("demo-notes", ".md", lot, False) == "demo-notes.md"


def test_the_three_lots_never_write_over_each_other() -> None:
    import generate_sample_batch as generator

    written = [
        generator.artefact_name(stem, suffix, SECTION_LOTS[name], True)
        for name in SECTION_ROSTERS
        for stem, suffix in (("demo-notes", ".md"), ("contact-sheet", ".png"), ("push-event", ".json"))
    ]

    assert len(written) == len(set(written)) == 9
