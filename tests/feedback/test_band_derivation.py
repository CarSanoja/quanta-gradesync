import pytest

from autocurricula.schemas.feedback import (
    FeedbackBand,
    band_for_grade_level,
    band_for_grade_number,
)


@pytest.mark.parametrize(
    ("grade_level", "expected"),
    [
        ("K", FeedbackBand.EARLY_PRIMARY),
        ("kindergarten", FeedbackBand.EARLY_PRIMARY),
        ("pre-k", FeedbackBand.EARLY_PRIMARY),
        ("1", FeedbackBand.EARLY_PRIMARY),
        ("grade 3", FeedbackBand.EARLY_PRIMARY),
        ("4", FeedbackBand.UPPER_PRIMARY),
        ("5th grade", FeedbackBand.UPPER_PRIMARY),
        ("6", FeedbackBand.UPPER_PRIMARY),
        ("7", FeedbackBand.LOWER_SECONDARY),
        ("Grade 8", FeedbackBand.LOWER_SECONDARY),
        ("9", FeedbackBand.LOWER_SECONDARY),
        ("10", FeedbackBand.UPPER_SECONDARY),
        ("10A", FeedbackBand.UPPER_SECONDARY),
        ("11th", FeedbackBand.UPPER_SECONDARY),
        ("12", FeedbackBand.UPPER_SECONDARY),
    ],
)
def test_every_k12_grade_level_maps_to_one_band(
    grade_level: str, expected: FeedbackBand
) -> None:
    assert band_for_grade_level(grade_level) is expected


@pytest.mark.parametrize("grade_level", [None, "", "   ", "unknown", "adult", "13", "99"])
def test_an_ungraded_level_yields_no_band_instead_of_a_guess(grade_level) -> None:
    assert band_for_grade_level(grade_level) is None


def test_band_boundaries_are_contiguous_and_cover_kindergarten_to_twelve() -> None:
    bands = [band_for_grade_number(grade) for grade in range(0, 13)]
    assert None not in bands
    assert bands[0] is FeedbackBand.EARLY_PRIMARY
    assert bands[12] is FeedbackBand.UPPER_SECONDARY
    ordered = list(dict.fromkeys(bands))
    assert ordered == list(FeedbackBand)


def test_grades_outside_k12_are_refused() -> None:
    assert band_for_grade_number(13) is None
    assert band_for_grade_number(-1) is None


def test_the_derivation_is_pure_and_repeatable() -> None:
    assert band_for_grade_level("10") is band_for_grade_level("10")
