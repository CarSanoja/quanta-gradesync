"""One paper, three sections — the load a real teacher carries in a single week.

The pedagogical mix is deliberately the same in all three: every section has its
own partial credit, its own faded pencil, its own illegible page and its own
handwritten prompt injection. A teacher does not get an easy section, and a demo
that grades one clean batch proves less than one that survives the same trouble
three times.

Answers repeat across sections because the sections sat the same exam. What does
not repeat is who wrote them, or how the page looks: ink, handwriting font, tilt
and scan noise are offset per section so no two batches render alike.
"""

from dataclasses import replace

from sample_batch.profiles import EXPECT_AUTO_SYNC, StudentProfile
from sample_batch.roster_demo import PHOTO_LOOK_EVERY, RAW_PROFILES, demo_fonts
from sample_batch.section_names import SECTION_NAMES

TILT_STEPS = (0.7, 1.05, 0.85, 1.3, 0.95)
JITTER_STEPS = (2.2, 2.9, 2.5, 3.1, 2.7, 2.4)
INKS = ("blue", "black", "blue", "dark_blue", "black")

# Each section starts the style cycles at a different point, so section B is not
# section A with the names swapped.
SECTION_OFFSETS = {"10A": 0, "10B": 2, "10C": 4}


def slug(name: str) -> str:
    return name.lower().replace(" ", "-")


def section_profiles(class_id: str) -> tuple[StudentProfile, ...]:
    names = SECTION_NAMES[class_id]
    if len(names) != len(RAW_PROFILES):
        raise ValueError(
            f"section {class_id} has {len(names)} names for {len(RAW_PROFILES)} papers"
        )
    fonts = demo_fonts()
    offset = SECTION_OFFSETS[class_id]
    built: list[StudentProfile] = []
    for index, (profile, name) in enumerate(zip(RAW_PROFILES, names, strict=True)):
        step = index + offset
        auto_sync = profile.expected == EXPECT_AUTO_SYNC
        built.append(
            replace(
                profile,
                student_id=slug(name),
                display_name=name,
                ink=INKS[step % len(INKS)],
                font_path=fonts[step % len(fonts)],
                photo_look=profile.photo_look or (auto_sync and step % PHOTO_LOOK_EVERY == 1),
                tilt=TILT_STEPS[step % len(TILT_STEPS)],
                jitter=JITTER_STEPS[step % len(JITTER_STEPS)],
            )
        )
    return tuple(built)
