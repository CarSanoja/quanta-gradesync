from random import Random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

PAPER_COLOR = (250, 249, 244)
RULE_COLOR = (198, 210, 226)
MARGIN_COLOR = (216, 158, 158)
HOLE_COLOR = (232, 231, 226)

RULE_SPACING = 46
FIRST_RULE_Y = 232
MARGIN_X = 118


def ruled_paper(width: int, height: int, rng: Random) -> Image.Image:
    canvas = Image.new("RGB", (width, height), PAPER_COLOR)
    draw = ImageDraw.Draw(canvas)
    for y in range(FIRST_RULE_Y, height - 60, RULE_SPACING):
        wobble = rng.uniform(-0.8, 0.8)
        draw.line(
            [(MARGIN_X - 58, y + wobble), (width - 70, y - wobble)],
            fill=RULE_COLOR,
            width=1,
        )
    draw.line([(MARGIN_X, 96), (MARGIN_X, height - 60)], fill=MARGIN_COLOR, width=2)
    for index in range(3):
        center_y = 300 + index * 460
        draw.ellipse(
            [(38, center_y - 18), (74, center_y + 18)], fill=HOLE_COLOR, outline=(224, 223, 218)
        )
    return canvas


def grain(image: Image.Image, rng: Random, strength: float = 0.055) -> Image.Image:
    noise = Image.frombytes("L", image.size, rng.randbytes(image.size[0] * image.size[1]))
    return Image.blend(image, noise.convert("RGB"), strength)


def scanner_shading(image: Image.Image, rng: Random) -> Image.Image:
    width, height = image.size
    shade = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(shade)
    edge = rng.randint(40, 90)
    for offset in range(edge):
        value = 255 - int((edge - offset) * 1.6)
        draw.line([(offset, 0), (offset, height)], fill=max(value, 150))
    darkened = Image.composite(image, Image.new("RGB", image.size, (218, 216, 210)), shade)
    return darkened


def scan_tilt(image: Image.Image, rng: Random, limit: float = 0.7) -> Image.Image:
    angle = rng.uniform(-limit, limit)
    return image.rotate(
        angle, resample=Image.BICUBIC, expand=False, fillcolor=PAPER_COLOR
    )


def degrade(
    image: Image.Image, blur_radius: float = 0.0, contrast: float = 1.0, brightness: float = 1.0
) -> Image.Image:
    result = image
    if blur_radius > 0:
        result = result.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    if contrast != 1.0:
        result = ImageEnhance.Contrast(result).enhance(contrast)
    if brightness != 1.0:
        result = ImageEnhance.Brightness(result).enhance(brightness)
    return result
