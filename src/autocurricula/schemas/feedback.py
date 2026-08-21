import re
from enum import StrEnum

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel


class EvidenceSpan(FrozenStrictModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class FeedbackBand(StrEnum):
    EARLY_PRIMARY = "early_primary"
    UPPER_PRIMARY = "upper_primary"
    LOWER_SECONDARY = "lower_secondary"
    UPPER_SECONDARY = "upper_secondary"


class FeedbackPoint(FrozenStrictModel):
    text: str = Field(min_length=1)
    evidence: EvidenceSpan | None = None


class StudentFeedback(FrozenStrictModel):
    band: FeedbackBand
    headline: str = Field(min_length=1)
    strengths: list[FeedbackPoint] = Field(default_factory=list)
    growth: list[FeedbackPoint] = Field(default_factory=list)
    next_step: str = Field(min_length=1)
    teacher_note: str | None = None


KINDERGARTEN_TOKENS = frozenset(
    {"k", "kg", "kinder", "kindergarten", "pk", "prek", "tk", "reception"}
)
BAND_CEILINGS: tuple[tuple[int, FeedbackBand], ...] = (
    (3, FeedbackBand.EARLY_PRIMARY),
    (6, FeedbackBand.UPPER_PRIMARY),
    (9, FeedbackBand.LOWER_SECONDARY),
    (12, FeedbackBand.UPPER_SECONDARY),
)
KINDERGARTEN_GRADE = 0
_GRADE_NUMBER = re.compile(r"(?<!\d)(\d{1,2})(?!\d)")
_WORD_SEPARATORS = re.compile(r"[^a-z0-9]+")


def band_for_grade_number(grade: int) -> FeedbackBand | None:
    if grade < KINDERGARTEN_GRADE:
        return None
    for ceiling, band in BAND_CEILINGS:
        if grade <= ceiling:
            return band
    return None


def band_for_grade_level(grade_level: str | None) -> FeedbackBand | None:
    if grade_level is None:
        return None
    normalized = grade_level.strip().lower()
    if not normalized:
        return None
    tokens = {token for token in _WORD_SEPARATORS.split(normalized) if token}
    if tokens & KINDERGARTEN_TOKENS:
        return band_for_grade_number(KINDERGARTEN_GRADE)
    match = _GRADE_NUMBER.search(normalized)
    if match is None:
        return None
    return band_for_grade_number(int(match.group(1)))
