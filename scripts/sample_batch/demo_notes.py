from sample_batch.lots import LotSpec
from sample_batch.profiles import (
    EXPECT_AUTO_SYNC,
    EXPECT_HOLD_ARMOR,
    EXPECT_HOLD_ILLEGIBLE,
    QUALITY_AUTHORITY_NOTE,
    QUALITY_CORRECT,
    QUALITY_FADED,
    QUALITY_ILLEGIBLE,
    QUALITY_INJECTION,
    QUALITY_INJECTION_LEET,
    QUALITY_PARTIAL,
    QUALITY_POOR,
    StudentProfile,
)

BAND_LABELS = {
    QUALITY_CORRECT: "Correct",
    QUALITY_PARTIAL: "Partial",
    QUALITY_POOR: "Poor",
    QUALITY_ILLEGIBLE: "Hold: blurry scan",
    QUALITY_FADED: "Hold: faded pencil photo",
    QUALITY_INJECTION: "Hold: prompt injection",
    QUALITY_INJECTION_LEET: "Hold: obfuscated injection",
    QUALITY_AUTHORITY_NOTE: "Hold: fake authority note",
}

HOLD_REASONS = {
    QUALITY_ILLEGIBLE: "hold - legibility below the confidence floor",
    QUALITY_FADED: "hold - legibility below the confidence floor",
    QUALITY_INJECTION: "hold - armor, plain injection",
    QUALITY_INJECTION_LEET: "hold - armor, leetspeak injection",
    QUALITY_AUTHORITY_NOTE: "hold - armor, fake authority note",
}

BREAKER_THRESHOLD = 0.15


def expected_label(profile: StudentProfile) -> str:
    if profile.expected == EXPECT_AUTO_SYNC:
        return "auto-sync"
    return HOLD_REASONS.get(profile.quality, profile.expected)


def _counts(profiles: tuple[StudentProfile, ...]) -> dict[str, int]:
    return {
        "total": len(profiles),
        "auto": sum(1 for item in profiles if item.expected == EXPECT_AUTO_SYNC),
        "illegible": sum(1 for item in profiles if item.expected == EXPECT_HOLD_ILLEGIBLE),
        "armor": sum(1 for item in profiles if item.expected == EXPECT_HOLD_ARMOR),
    }


def case_matrix_rows(profiles: tuple[StudentProfile, ...]) -> list[tuple[str, str, str, str]]:
    return [
        (
            profile.student_id,
            BAND_LABELS.get(profile.quality, profile.quality),
            profile.notes,
            expected_label(profile),
        )
        for profile in profiles
    ]


def case_matrix_table(profiles: tuple[StudentProfile, ...]) -> str:
    lines = [
        "| Student | Band | What the page contains | Expected behaviour |",
        "|---|---|---|---|",
    ]
    lines.extend(f"| {a} | {b} | {c} | {d} |" for a, b, c, d in case_matrix_rows(profiles))
    return "\n".join(lines)


def held_ids(profiles: tuple[StudentProfile, ...]) -> set[str]:
    return {item.student_id for item in profiles if item.expected != EXPECT_AUTO_SYNC}


def illegible_line(profiles: tuple[StudentProfile, ...], scores: dict[str, float]) -> str:
    entries = [
        f"{item.student_id} {scores[item.student_id]:.3f}"
        for item in profiles
        if item.expected == EXPECT_HOLD_ILLEGIBLE and item.student_id in scores
    ]
    return "- both illegible holds score below the 0.50 confidence floor: " + ", ".join(entries)


def build_demo_notes(
    profiles: tuple[StudentProfile, ...], lot: LotSpec, scores: dict[str, float]
) -> str:
    counts = _counts(profiles)
    held = counts["illegible"] + counts["armor"]
    ratio = held / counts["total"]
    quarantined = held_ids(profiles)
    solid = [score for student, score in scores.items() if student not in quarantined]
    return "\n".join(
        (
            f"# Demo batch - {lot.class_id} - {lot.lot_code}",
            "",
            f"Exam date on the page header: {lot.header_date}. "
            f"Job id `{lot.job_id}`, prefix `{lot.batch_prefix}`.",
            "",
            "## Headline numbers for the video",
            "",
            f"- **{counts['total']} exams scanned** from one dropped folder",
            f"- **{counts['auto']} auto-synced** without a human touching them",
            f"- **{held} held for review**: {counts['illegible']} illegible, "
            f"{counts['armor']} flagged by armor",
            f"- hold ratio {ratio:.1%}, under the {BREAKER_THRESHOLD:.0%} batch circuit "
            "breaker that would otherwise hold the whole lot",
            "",
            "## Legibility",
            "",
            f"- lowest score among the {counts['auto']} auto-synced pages: "
            f"{min(solid):.3f} (full-trust gate is 0.70)",
            illegible_line(profiles, scores),
            "",
            "## Case matrix",
            "",
            case_matrix_table(profiles),
            "",
        )
    )
