from sample_batch.lots import (
    DEMO_LOT,
    LOTS,
    REFERENCE_LOT,
    ROSTER_DEMO,
    ROSTER_REFERENCE,
    SECTION_LOTS,
    SECTION_ROSTERS,
    LotSpec,
)
from sample_batch.profiles import StudentProfile
from sample_batch.roster import PROFILES as REFERENCE_PROFILES
from sample_batch.roster_demo import DEMO_PROFILES
from sample_batch.roster_sections import section_profiles

ROSTERS: dict[str, tuple[StudentProfile, ...]] = {
    ROSTER_REFERENCE: REFERENCE_PROFILES,
    ROSTER_DEMO: DEMO_PROFILES,
    **{name: section_profiles(SECTION_LOTS[name].class_id) for name in SECTION_ROSTERS},
}
ROSTER_NAMES: tuple[str, ...] = (ROSTER_REFERENCE, ROSTER_DEMO, *SECTION_ROSTERS)

__all__ = [
    "DEMO_LOT",
    "LOTS",
    "REFERENCE_LOT",
    "SECTION_LOTS",
    "SECTION_ROSTERS",
    "ROSTERS",
    "ROSTER_DEMO",
    "ROSTER_NAMES",
    "ROSTER_REFERENCE",
    "LotSpec",
    "profiles_for",
    "lot_for",
    "ground_truth_for",
]


def profiles_for(roster: str) -> tuple[StudentProfile, ...]:
    try:
        return ROSTERS[roster]
    except KeyError:
        raise ValueError(f"unknown roster {roster!r}") from None


def lot_for(roster: str) -> LotSpec:
    try:
        return LOTS[roster]
    except KeyError:
        raise ValueError(f"unknown roster {roster!r}") from None


def ground_truth_for(roster: str) -> list[dict[str, object]]:
    return [
        {
            "student_id": profile.student_id,
            "scores": dict(profile.ground_truth),
            "notes": profile.notes,
        }
        for profile in profiles_for(roster)
        if profile.ground_truth is not None
    ]
