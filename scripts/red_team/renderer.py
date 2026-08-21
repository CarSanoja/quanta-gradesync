import re
from dataclasses import dataclass
from pathlib import Path
from random import Random

from PIL import Image
from sample_batch.catalog import QUESTIONS
from sample_batch.handwriting import INK_COLORS, handwriting_font, write_line
from sample_batch.pages import (
    CRITERION_ORDER,
    LEFT,
    PAGE_HEIGHT,
    compose_page,
)
from sample_batch.profiles import StudentProfile
from sample_batch.roster_solid import SOLID_PROFILES

from red_team.taxonomy import (
    PLACEMENT_FILENAME,
    PLACEMENT_FOOTER,
    PLACEMENT_MARGIN,
    AttackClass,
)

JPEG_QUALITY = 84
PAYLOAD_CRITERION_INDEX = 1
MARGIN_ORIGIN = (18, 470)
FOOTER_ORIGIN = (LEFT - 20, PAGE_HEIGHT - 120)
_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class RenderedAttack:
    attack_class: str
    index: int
    payload: str
    placement: str
    submission_id: str
    payload_path: Path
    clean_path: Path
    payload_transcript: str
    clean_transcript: str


def slug(text: str, limit: int = 60) -> str:
    cleaned = _SLUG.sub("-", text.lower()).strip("-")
    return (cleaned[:limit].strip("-") or "payload")


def base_profile(index: int) -> StudentProfile:
    return SOLID_PROFILES[index % len(SOLID_PROFILES)]


def transcript_of(profile: StudentProfile, extra: str = "") -> str:
    blocks = []
    for criterion in CRITERION_ORDER:
        blocks.append(QUESTIONS[criterion])
        blocks.extend(profile.answers.get(criterion, []))
    if extra:
        blocks.append(extra)
    return "\n".join(blocks)


def profile_with_payload(profile: StudentProfile, payload: str) -> StudentProfile:
    criterion = CRITERION_ORDER[PAYLOAD_CRITERION_INDEX]
    answers = {key: list(value) for key, value in profile.answers.items()}
    answers.setdefault(criterion, []).append(payload)
    return StudentProfile(
        student_id=profile.student_id,
        display_name=profile.display_name,
        quality=profile.quality,
        ink=profile.ink,
        answers=answers,
        ground_truth=profile.ground_truth,
        notes=profile.notes,
        font_size=profile.font_size,
        blur_radius=profile.blur_radius,
        contrast=profile.contrast,
        brightness=profile.brightness,
    )


def stamp_overlay(
    page: Image.Image, payload: str, attack_class: AttackClass, rng: Random
) -> Image.Image:
    canvas = page.convert("RGBA")
    size = max(9, round(30 * attack_class.font_scale))
    font = handwriting_font(size)
    ink = INK_COLORS.get(attack_class.ink, INK_COLORS["graphite"])
    origin = (
        MARGIN_ORIGIN if attack_class.placement == PLACEMENT_MARGIN else FOOTER_ORIGIN
    )
    write_line(canvas, payload, origin, font, rng, ink, jitter=1.4, tilt=0.5)
    return canvas.convert("RGB")


def save_page(page: Image.Image, path: Path, transcript: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.save(path, format="JPEG", quality=JPEG_QUALITY, optimize=True)
    path.with_suffix(".txt").write_text(transcript, encoding="utf-8")


def render_attack(
    attack_class: AttackClass,
    payload: str,
    index: int,
    target: Path,
    seed: int,
) -> RenderedAttack:
    profile = base_profile(index)
    clean_rng = Random(f"{seed}:{attack_class.code}:{index}")
    payload_rng = Random(f"{seed}:{attack_class.code}:{index}")
    clean_page = compose_page(profile, clean_rng)
    clean_transcript = transcript_of(profile)
    stem = f"{attack_class.code.lower()}-{index:02d}"
    if attack_class.placement == PLACEMENT_FILENAME:
        payload_page = compose_page(profile, payload_rng)
        payload_transcript = clean_transcript
        payload_stem = slug(payload)
    elif attack_class.placement in (PLACEMENT_MARGIN, PLACEMENT_FOOTER):
        payload_page = stamp_overlay(
            compose_page(profile, payload_rng), payload, attack_class, payload_rng
        )
        payload_transcript = transcript_of(profile, payload)
        payload_stem = f"{stem}-payload"
    else:
        payload_page = compose_page(
            profile_with_payload(profile, payload), payload_rng
        )
        payload_transcript = transcript_of(profile, payload)
        payload_stem = f"{stem}-payload"
    payload_path = target / attack_class.code / f"{payload_stem}.jpg"
    clean_path = target / attack_class.code / f"{stem}-clean.jpg"
    save_page(payload_page, payload_path, payload_transcript)
    save_page(clean_page, clean_path, clean_transcript)
    return RenderedAttack(
        attack_class=attack_class.code,
        index=index,
        payload=payload,
        placement=attack_class.placement,
        submission_id=payload_path.stem,
        payload_path=payload_path,
        clean_path=clean_path,
        payload_transcript=payload_transcript,
        clean_transcript=clean_transcript,
    )
