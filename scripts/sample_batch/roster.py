from sample_batch.profiles import StudentProfile
from sample_batch.roster_cases import CASE_PROFILES
from sample_batch.roster_solid import SOLID_PROFILES

PROFILES: tuple[StudentProfile, ...] = SOLID_PROFILES + CASE_PROFILES


def ground_truth_entries() -> list[dict[str, object]]:
    return [
        {
            "student_id": profile.student_id,
            "scores": dict(profile.ground_truth),
            "notes": profile.notes,
        }
        for profile in PROFILES
        if profile.ground_truth is not None
    ]
