from random import Random

from PIL import Image, ImageDraw

from sample_batch.catalog import (
    CRITERION_FACTORING,
    CRITERION_GRAPH,
    CRITERION_WORD_PROBLEM,
    LOT_CODE,
    QUESTIONS,
)
from sample_batch.handwriting import (
    INK_COLORS,
    handwriting_font,
    print_font,
    wrap_text,
    write_line,
    write_paragraph,
)
from sample_batch.paper import (
    degrade,
    grain,
    ruled_paper,
    scan_tilt,
    scanner_shading,
)
from sample_batch.profiles import StudentProfile

PAGE_WIDTH = 1200
PAGE_HEIGHT = 1600
LEFT = 172
RIGHT_MARGIN = 86
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT_MARGIN

SCHOOL_NAME = "Northside Secondary School"
HEADER_LINE = "Mathematics  |  Grade 10A  |  Parcial 1  |  19 August 2026"
PRINT_INK = (74, 82, 98)
FAINT_INK = (128, 136, 150)
RULE_INK = (188, 196, 210)

CRITERION_ORDER = (CRITERION_FACTORING, CRITERION_GRAPH, CRITERION_WORD_PROBLEM)
BLOCK_TOP = 300
BLOCK_HEIGHT = 400
ANSWER_LINE_HEIGHT = 52


def draw_header(canvas: Image.Image, profile: StudentProfile, rng: Random) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.text((LEFT - 26, 62), SCHOOL_NAME, font=print_font(31), fill=(*PRINT_INK, 255))
    draw.text((LEFT - 26, 104), HEADER_LINE, font=print_font(19), fill=(*FAINT_INK, 255))
    draw.line(
        [(LEFT - 26, 142), (PAGE_WIDTH - RIGHT_MARGIN, 142)], fill=(*RULE_INK, 255), width=2
    )
    draw.text((LEFT - 26, 166), "Student name:", font=print_font(19), fill=(*FAINT_INK, 255))
    draw.text(
        (PAGE_WIDTH - RIGHT_MARGIN - 330, 166),
        f"Lot: {LOT_CODE}",
        font=print_font(17),
        fill=(*FAINT_INK, 255),
    )
    draw.line(
        [(LEFT + 110, 196), (PAGE_WIDTH - RIGHT_MARGIN - 350, 196)],
        fill=(*RULE_INK, 255),
        width=1,
    )
    write_line(
        canvas,
        profile.display_name,
        (LEFT + 118, 146),
        handwriting_font(profile.font_size + 3),
        rng,
        INK_COLORS[profile.ink],
        jitter=1.9,
    )


def draw_question(canvas: Image.Image, text: str, top: int) -> int:
    draw = ImageDraw.Draw(canvas)
    font = print_font(21)
    cursor = top
    for line in wrap_text(text, font, CONTENT_WIDTH):
        draw.text((LEFT - 26, cursor), line, font=font, fill=(*PRINT_INK, 255))
        cursor += 28
    return cursor + 12


def draw_answer(
    canvas: Image.Image, profile: StudentProfile, lines: list[str], top: int, rng: Random
) -> int:
    font = handwriting_font(profile.font_size)
    ink = INK_COLORS[profile.ink]
    cursor = top
    for line in lines:
        cursor = write_paragraph(
            canvas,
            line,
            (LEFT + rng.randint(0, 18), cursor),
            font,
            rng,
            CONTENT_WIDTH - 40,
            ANSWER_LINE_HEIGHT,
            ink,
            jitter=2.6,
        )
    return cursor


def draw_footer(canvas: Image.Image) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.text(
        (LEFT - 26, PAGE_HEIGHT - 78),
        "Scanned by the front office  |  page 1 of 1  |  do not write below this line",
        font=print_font(16),
        fill=(*FAINT_INK, 255),
    )


def compose_page(profile: StudentProfile, rng: Random) -> Image.Image:
    canvas = ruled_paper(PAGE_WIDTH, PAGE_HEIGHT, rng).convert("RGBA")
    draw_header(canvas, profile, rng)
    for index, criterion in enumerate(CRITERION_ORDER):
        top = BLOCK_TOP + index * BLOCK_HEIGHT
        answer_top = draw_question(canvas, QUESTIONS[criterion], top)
        draw_answer(canvas, profile, profile.answers.get(criterion, []), answer_top, rng)
    draw_footer(canvas)
    page = canvas.convert("RGB")
    page = scanner_shading(page, rng)
    page = grain(page, rng)
    page = scan_tilt(page, rng)
    return degrade(
        page,
        blur_radius=profile.blur_radius,
        contrast=profile.contrast,
        brightness=profile.brightness,
    )
