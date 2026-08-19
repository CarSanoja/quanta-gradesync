from pathlib import Path

ANSWER_LINES = (
    "Name: Ana Torres",
    "1) Factor completely:",
    "x^2 + x - 6 = (x+3)(x-2)",
    "Check: (x+3)(x-2) = x^2 + x - 6",
)
IMAGE_WIDTH = 1200
IMAGE_HEIGHT = 1600


def render_answer_sheet(target: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    canvas = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New.ttf", 56)
    except OSError:
        font = ImageFont.load_default(size=56)
    for index, line in enumerate(ANSWER_LINES):
        draw.text((120, 200 + index * 160), line, fill=(15, 15, 40), font=font)
    rotated = canvas.rotate(0.6, fillcolor="white", resample=Image.BICUBIC)
    target.parent.mkdir(parents=True, exist_ok=True)
    rotated.save(target, format="JPEG", quality=92)
    return target
