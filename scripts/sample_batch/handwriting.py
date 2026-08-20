from pathlib import Path
from random import Random

from PIL import Image, ImageDraw, ImageFont

HANDWRITING_FONT_CANDIDATES = (
    "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
    "/System/Library/Fonts/Noteworthy.ttc",
    "/System/Library/Fonts/MarkerFelt.ttc",
    "/System/Library/Fonts/Supplemental/Chalkduster.ttf",
    "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)

PRINT_FONT_CANDIDATES = (
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
)

INK_COLORS = {
    "blue": (32, 46, 96),
    "dark_blue": (22, 33, 78),
    "graphite": (58, 58, 62),
    "black": (30, 32, 38),
}


def load_font(candidates: tuple[str, ...], size: int) -> ImageFont.FreeTypeFont:
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def handwriting_font(size: int) -> ImageFont.FreeTypeFont:
    return load_font(HANDWRITING_FONT_CANDIDATES, size)


def print_font(size: int) -> ImageFont.FreeTypeFont:
    return load_font(PRINT_FONT_CANDIDATES, size)


def text_width(font: ImageFont.FreeTypeFont, text: str) -> float:
    return font.getlength(text)


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and text_width(font, candidate) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def render_line(
    text: str,
    font: ImageFont.FreeTypeFont,
    rng: Random,
    color: tuple[int, int, int],
    jitter: float = 2.4,
) -> Image.Image:
    padding = 14
    width = int(text_width(font, text) + padding * 2 + len(text) * 1.6)
    height = int(font.size * 2.6 + padding)
    layer = Image.new("RGBA", (max(width, 1), max(height, 1)), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    cursor = float(padding)
    baseline = font.size * 0.9
    for character in text:
        offset_y = rng.uniform(-jitter, jitter)
        shade = rng.randint(-14, 14)
        ink = tuple(max(0, min(255, channel + shade)) for channel in color)
        draw.text((cursor, baseline + offset_y), character, font=font, fill=(*ink, 255))
        cursor += text_width(font, character) + rng.uniform(-0.6, 1.7)
    return layer


def write_line(
    canvas: Image.Image,
    text: str,
    origin: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    rng: Random,
    color: tuple[int, int, int] = INK_COLORS["blue"],
    jitter: float = 2.4,
    tilt: float = 0.9,
) -> None:
    if not text:
        return
    line = render_line(text, font, rng, color, jitter=jitter)
    angle = rng.uniform(-tilt, tilt)
    rotated = line.rotate(angle, resample=Image.BICUBIC, expand=True)
    canvas.alpha_composite(rotated, dest=(origin[0], origin[1]))


def write_paragraph(
    canvas: Image.Image,
    text: str,
    origin: tuple[int, int],
    font: ImageFont.FreeTypeFont,
    rng: Random,
    max_width: int,
    line_height: int,
    color: tuple[int, int, int] = INK_COLORS["blue"],
    jitter: float = 2.4,
) -> int:
    cursor_y = origin[1]
    for index, line in enumerate(wrap_text(text, font, max_width)):
        drift = rng.randint(-4, 4) if index else 0
        write_line(canvas, line, (origin[0] + drift, cursor_y), font, rng, color, jitter)
        cursor_y += line_height + rng.randint(-2, 3)
    return cursor_y
