from dataclasses import replace
from pathlib import Path

from sample_batch.handwriting import HANDWRITING_FONT_CANDIDATES
from sample_batch.profiles import EXPECT_AUTO_SYNC, StudentProfile
from sample_batch.roster_demo_decimals import DECIMAL_PROFILES
from sample_batch.roster_demo_fractions import FRACTION_PROFILES
from sample_batch.roster_demo_holds import HOLD_PROFILES
from sample_batch.roster_demo_minutes import MINUTE_PROFILES
from sample_batch.roster_demo_partial import PARTIAL_PROFILES
from sample_batch.roster_demo_poor import POOR_PROFILES

GENERIC_FALLBACK_FONT = "/Library/Fonts/Arial Unicode.ttf"
PHOTO_LOOK_EVERY = 3
TILT_STEPS = (0.7, 1.05, 0.85, 1.3)
JITTER_STEPS = (2.2, 2.9, 2.5, 3.1, 2.7)

RAW_PROFILES: tuple[StudentProfile, ...] = (
    FRACTION_PROFILES + DECIMAL_PROFILES + MINUTE_PROFILES + PARTIAL_PROFILES + POOR_PROFILES
) + HOLD_PROFILES


def demo_fonts() -> tuple[str, ...]:
    present = tuple(
        candidate
        for candidate in HANDWRITING_FONT_CANDIDATES
        if candidate != GENERIC_FALLBACK_FONT and Path(candidate).is_file()
    )
    return present or (GENERIC_FALLBACK_FONT,)


def style(profiles: tuple[StudentProfile, ...]) -> tuple[StudentProfile, ...]:
    fonts = demo_fonts()
    styled: list[StudentProfile] = []
    for index, profile in enumerate(profiles):
        auto_sync = profile.expected == EXPECT_AUTO_SYNC
        styled.append(
            replace(
                profile,
                font_path=fonts[index % len(fonts)],
                photo_look=profile.photo_look
                or (auto_sync and index % PHOTO_LOOK_EVERY == 1),
                tilt=TILT_STEPS[index % len(TILT_STEPS)],
                jitter=JITTER_STEPS[index % len(JITTER_STEPS)],
            )
        )
    return tuple(styled)


DEMO_PROFILES: tuple[StudentProfile, ...] = style(RAW_PROFILES)
