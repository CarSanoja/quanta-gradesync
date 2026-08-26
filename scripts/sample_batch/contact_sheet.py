from pathlib import Path

from PIL import Image, ImageDraw

from sample_batch.handwriting import print_font

COLUMNS = 8
THUMB_WIDTH = 220
GUTTER = 14
CAPTION_HEIGHT = 22
SHEET_BACKGROUND = (24, 26, 32)
CAPTION_INK = (206, 210, 220)
FRAME_INK = (58, 62, 72)


def build_contact_sheet(pages: list[Path], columns: int = COLUMNS) -> Image.Image:
    if not pages:
        raise ValueError("contact sheet needs at least one page")
    with Image.open(pages[0]) as first:
        ratio = first.height / first.width
    thumb_height = round(THUMB_WIDTH * ratio)
    rows = -(-len(pages) // columns)
    cell_height = thumb_height + CAPTION_HEIGHT + GUTTER
    width = columns * (THUMB_WIDTH + GUTTER) + GUTTER
    height = rows * cell_height + GUTTER
    sheet = Image.new("RGB", (width, height), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    font = print_font(13)
    for index, page in enumerate(pages):
        column = index % columns
        row = index // columns
        left = GUTTER + column * (THUMB_WIDTH + GUTTER)
        top = GUTTER + row * cell_height
        with Image.open(page) as source:
            thumb = source.convert("RGB").resize((THUMB_WIDTH, thumb_height), Image.LANCZOS)
        sheet.paste(thumb, (left, top))
        draw.rectangle(
            [(left, top), (left + THUMB_WIDTH - 1, top + thumb_height - 1)],
            outline=FRAME_INK,
        )
        draw.text((left, top + thumb_height + 5), page.stem, font=font, fill=CAPTION_INK)
    return sheet
