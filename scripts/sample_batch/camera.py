from random import Random

from PIL import Image

WARM_TINT = (255, 246, 232)
TINT_STRENGTH = 0.085
SHADOW_FLOOR = 176
WARP_RATIO = 0.014
SHADOW_CELLS_X = 12
SHADOW_CELLS_Y = 16


def _perspective_coefficients(
    source: list[tuple[float, float]], target: list[tuple[float, float]]
) -> tuple[float, ...]:
    rows: list[list[float]] = []
    values: list[float] = []
    for (sx, sy), (tx, ty) in zip(source, target, strict=True):
        rows.append([tx, ty, 1, 0, 0, 0, -sx * tx, -sx * ty])
        values.append(sx)
        rows.append([0, 0, 0, tx, ty, 1, -sy * tx, -sy * ty])
        values.append(sy)
    size = len(values)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(rows[row][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        values[column], values[pivot] = values[pivot], values[column]
        divisor = rows[column][column]
        rows[column] = [item / divisor for item in rows[column]]
        values[column] /= divisor
        for row in range(size):
            if row == column:
                continue
            factor = rows[row][column]
            pivot_row = rows[column]
            rows[row] = [
                item - factor * other
                for item, other in zip(rows[row], pivot_row, strict=True)
            ]
            values[row] -= factor * values[column]
    return tuple(values)


def perspective_warp(image: Image.Image, rng: Random) -> Image.Image:
    width, height = image.size
    span = width * WARP_RATIO
    corners = [
        (rng.uniform(0, span), rng.uniform(0, span)),
        (width - rng.uniform(0, span), rng.uniform(0, span)),
        (width - rng.uniform(0, span), height - rng.uniform(0, span)),
        (rng.uniform(0, span), height - rng.uniform(0, span)),
    ]
    box = [(0.0, 0.0), (float(width), 0.0), (float(width), float(height)), (0.0, float(height))]
    coefficients = _perspective_coefficients(corners, box)
    return image.transform(
        image.size,
        Image.PERSPECTIVE,
        coefficients,
        resample=Image.BICUBIC,
        fillcolor=(246, 244, 238),
    )


def soft_shadow(image: Image.Image, rng: Random) -> Image.Image:
    width, height = image.size
    depth = rng.randint(26, 46)
    from_left = rng.random() < 0.5
    corner = rng.uniform(0.5, 0.85)
    cells = []
    for row in range(SHADOW_CELLS_Y):
        vertical_ratio = row / (SHADOW_CELLS_Y - 1)
        below = max(0.0, (vertical_ratio - corner) / (1.0 - corner))
        for column in range(SHADOW_CELLS_X):
            lateral_ratio = column / (SHADOW_CELLS_X - 1)
            lateral = lateral_ratio if from_left else 1.0 - lateral_ratio
            fade = min(1.0, lateral * 0.85 + below * 0.6)
            cells.append(255 - int(depth * fade))
    low = Image.new("L", (SHADOW_CELLS_X, SHADOW_CELLS_Y))
    low.putdata(cells)
    mask = low.resize((width, height), Image.BICUBIC)
    floor = Image.new("RGB", (width, height), (SHADOW_FLOOR, SHADOW_FLOOR, SHADOW_FLOOR))
    return Image.composite(image, floor, mask)


def warm_tint(image: Image.Image) -> Image.Image:
    return Image.blend(image, Image.new("RGB", image.size, WARM_TINT), TINT_STRENGTH)


def phone_photo(image: Image.Image, rng: Random) -> Image.Image:
    return warm_tint(soft_shadow(perspective_warp(image, rng), rng))
