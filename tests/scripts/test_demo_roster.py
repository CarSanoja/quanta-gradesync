import json

import pytest

from autocurricula.core.armor.deterministic import scan_text
from autocurricula.core.armor.legibility import (
    DEFAULT_CONFIDENCE_FLOOR,
    DEFAULT_FULL_TRUST_LEGIBILITY,
    legibility_score,
)
from tests.scripts.conftest import DEMO_SEED, SCRIPTS_DIR
from tests.scripts.test_sample_batch_generator import pages_of

DEMO_PAGE_COUNT = 36
DEMO_HOLD_COUNT = 4
MAX_HOLD_PRONE_PAGES = 5
BREAKER_RATIO = 0.15


def answer_lines(batch: dict[str, object]) -> set[str]:
    return {
        line
        for profile in batch["profiles"]
        for block in profile.answers.values()
        for line in block
    }


def test_demo_roster_renders_thirty_six_unique_students(demo_batch) -> None:
    pages = pages_of(demo_batch)
    assert len(pages) == DEMO_PAGE_COUNT
    assert len({page.stem for page in pages}) == DEMO_PAGE_COUNT
    assert {page.stem for page in pages} == {
        profile.student_id for profile in demo_batch["profiles"]
    }


def test_demo_lot_targets_section_10b(demo_batch) -> None:
    lot = demo_batch["lot"]
    assert lot.class_id == "10B"
    assert lot.lot_code == "2026_Matematicas_10B_Parcial1"
    assert lot.header_line == "Mathematics  |  Grade 10B  |  Parcial 1  |  25 August 2026"
    event = json.loads(demo_batch["push_event"].read_text(encoding="utf-8"))
    assert event["message"]["attributes"]["lot_code"] == lot.lot_code


def test_demo_roster_writes_no_ground_truth(demo_batch) -> None:
    assert "ground_truth" not in demo_batch
    assert not (demo_batch["root"] / "ground_truth.json").exists()


def test_no_demo_page_leaves_a_question_unanswered(demo_batch) -> None:
    empty = [
        (profile.student_id, criterion)
        for profile in demo_batch["profiles"]
        for criterion, lines in profile.answers.items()
        if not lines
    ]
    assert not empty, empty
    for profile in demo_batch["profiles"]:
        assert len(profile.answers) == 3


def test_demo_holds_stay_under_the_batch_circuit_breaker(demo_batch) -> None:
    held = [item for item in demo_batch["profiles"] if item.expected != "auto-sync"]
    assert len(held) == DEMO_HOLD_COUNT
    assert len(held) <= MAX_HOLD_PRONE_PAGES
    assert len(held) / DEMO_PAGE_COUNT < BREAKER_RATIO


def test_demo_composition_matches_the_case_matrix(demo_batch) -> None:
    bands = [profile.quality for profile in demo_batch["profiles"]]
    assert bands.count("correct") == 22
    assert bands.count("partial") == 8
    assert bands.count("poor") == 2
    assert len(bands) == DEMO_PAGE_COUNT


def test_every_gradable_demo_page_clears_the_full_trust_gate(demo_batch) -> None:
    scores = demo_batch["scores"]
    gradable = [
        profile.student_id
        for profile in demo_batch["profiles"]
        if profile.expected != "hold - illegible scan"
    ]
    low = {student: scores[student] for student in gradable if scores[student] < 0.70}
    assert not low, low
    assert DEFAULT_FULL_TRUST_LEGIBILITY == 0.70


def test_both_illegible_holds_fall_below_the_confidence_floor(demo_batch) -> None:
    scores = demo_batch["scores"]
    held = [
        profile.student_id
        for profile in demo_batch["profiles"]
        if profile.expected == "hold - illegible scan"
    ]
    assert len(held) == 2
    for student in held:
        assert scores[student] < DEFAULT_CONFIDENCE_FLOOR, (student, scores[student])


def test_reported_scores_match_the_rendered_files(demo_batch) -> None:
    for page in pages_of(demo_batch)[:4]:
        assert demo_batch["scores"][page.stem] == pytest.approx(legibility_score(page))


def test_demo_pages_rotate_through_every_installed_handwriting_font(demo_batch) -> None:
    import sys

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from sample_batch.roster_demo import demo_fonts

    used = {profile.font_path for profile in demo_batch["profiles"]}
    assert used == set(demo_fonts())
    assert len(used) > 1


def test_a_third_of_the_demo_pages_carry_the_phone_photo_look(demo_batch) -> None:
    photo = sum(1 for profile in demo_batch["profiles"] if profile.photo_look)
    assert 8 <= photo <= 16


def test_the_plain_injection_trips_the_deterministic_prescreen(demo_batch) -> None:
    lines = answer_lines(demo_batch)
    plain = next(line for line in lines if line.startswith("IGNORE THE RUBRIC"))
    note = next(line for line in lines if line.startswith("SYSTEM NOTE"))
    assert scan_text(plain).technique == "plain"
    assert scan_text(note).technique == "plain"


def test_the_leetspeak_case_stays_available_but_out_of_the_demo_class(demo_batch) -> None:
    import sys

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from sample_batch.roster_demo_holds import LEETSPEAK_HOLD_PROFILE

    assert LEETSPEAK_HOLD_PROFILE.student_id == "lautaro-ferreyra"
    leet = LEETSPEAK_HOLD_PROFILE.answers["factoring"][1]
    assert scan_text(leet).technique == "leetspeak"
    assert LEETSPEAK_HOLD_PROFILE.student_id not in {
        profile.student_id for profile in demo_batch["profiles"]
    }


def test_the_fake_authority_note_is_left_to_the_model_screener(demo_batch) -> None:
    lines = answer_lines(demo_batch)
    note = next(line for line in lines if line.startswith("Note from Dept. Head"))
    assert scan_text(note) is None


def test_demo_notes_carry_the_headline_numbers_and_every_student(demo_batch) -> None:
    notes = demo_batch["notes"].read_text(encoding="utf-8")
    assert "**36 exams scanned**" in notes
    assert "**32 auto-synced**" in notes
    assert "**4 held for review**: 2 illegible, 2 flagged by armor" in notes
    for profile in demo_batch["profiles"]:
        assert profile.student_id in notes


def test_contact_sheet_covers_the_whole_class(demo_batch) -> None:
    from PIL import Image

    with Image.open(demo_batch["contact_sheet"]) as sheet:
        assert sheet.format == "PNG"
        assert sheet.width > 1000
        assert sheet.height > 1000


def test_demo_pages_are_reproducible_from_the_seed(demo_batch, generator, tmp_path) -> None:
    from random import Random

    from sample_batch.pages import compose_page

    lot = demo_batch["lot"]
    for profile in demo_batch["profiles"][:3]:
        page = compose_page(profile, Random(f"{DEMO_SEED}:{profile.student_id}"), lot)
        destination = tmp_path / f"{profile.student_id}.jpg"
        page.save(destination, format="JPEG", quality=84, optimize=True)
        original = next(
            item for item in pages_of(demo_batch) if item.stem == profile.student_id
        )
        assert destination.read_bytes() == original.read_bytes()
