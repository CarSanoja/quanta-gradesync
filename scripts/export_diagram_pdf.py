"""Export the reference diagram set to a single landscape PDF, one diagram per page.

Renders each SVG with macOS Quick Look, trims the square letterboxing Quick Look
adds, and lays the result out on A4 landscape pages in reading order: overview
first, then the C4 levels, then the flows, then the human path.

    python3 scripts/export_diagram_pdf.py
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

MEDIA = Path(__file__).resolve().parent.parent / "docs" / "media"
OUT = MEDIA / "architecture-diagrams.pdf"
RENDER_SIZE = 3200

ORDER = [
    ("architecture", "Overview", "The whole engine on one page"),
    ("context", "Level 1 · Context", "The school world around the engine"),
    ("containers", "Level 2 · Containers", "Deployable units and the data each owns"),
    ("pipeline", "Level 3 · Stages", "One job stage by stage, and where each stage refuses"),
    ("fleet", "Level 3 · Agents", "Eleven components, model, scope and principal"),
    ("governance", "Level 3 · Controls", "The gates a grade must survive"),
    ("self-improvement", "Level 3 · Cold loop", "How prompts improve against human ground truth"),
    ("exam-lifecycle", "Flow", "One exam end to end, on a real clock"),
    ("resilience", "Flow", "Failure modes that were actually executed"),
    ("teacher-journey", "People", "The teacher's screens, and what she never sees"),
]

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 20
FOOTER_H = 16


def render(svg: Path, workdir: Path) -> Path:
    subprocess.run(
        ["qlmanage", "-t", "-s", str(RENDER_SIZE), "-o", str(workdir), str(svg)],
        check=True,
        capture_output=True,
    )
    produced = workdir / f"{svg.name}.png"
    if not produced.exists():
        raise RuntimeError(f"Quick Look did not render {svg.name}")
    return produced


def trim(png: Path, aspect: float) -> Path:
    """Quick Look fits the render inside a square and pads it with white.

    The padding is not distinguishable by colour from the diagram's own white
    background, so the crop is computed from the viewBox aspect instead of
    detected: Quick Look centres the render, so the bands are symmetric.
    """
    image = Image.open(png).convert("RGB")
    side = image.width
    if aspect >= 1:
        height = round(side / aspect)
        offset = (side - height) // 2
        box = (0, offset, side, offset + height)
    else:
        width = round(side * aspect)
        offset = (side - width) // 2
        box = (offset, 0, offset + width, side)
    trimmed = png.with_name(f"trimmed-{png.name}")
    image.crop(box).save(trimmed)
    return trimmed


def expected_aspect(svg: Path) -> float:
    match = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg.read_text())
    if not match:
        raise RuntimeError(f"{svg.name} has no viewBox")
    return float(match.group(1)) / float(match.group(2))


def place(pdf: canvas.Canvas, image_path: Path, label: str, caption: str, page: int, total: int) -> None:
    reader = ImageReader(str(image_path))
    width, height = reader.getSize()
    available_w = PAGE_W - 2 * MARGIN
    available_h = PAGE_H - 2 * MARGIN - FOOTER_H
    scale = min(available_w / width, available_h / height)
    draw_w, draw_h = width * scale, height * scale
    x = (PAGE_W - draw_w) / 2
    y = MARGIN + FOOTER_H + (available_h - draw_h) / 2
    pdf.drawImage(reader, x, y, draw_w, draw_h, preserveAspectRatio=True, anchor="c")

    pdf.setFont("Helvetica", 7.5)
    pdf.setFillColorRGB(0.50, 0.53, 0.55)
    pdf.drawString(MARGIN + 4, MARGIN + 5, f"{label}  ·  {caption}")
    pdf.drawRightString(PAGE_W - MARGIN - 4, MARGIN + 5, f"{page} / {total}")
    pdf.showPage()


def main() -> int:
    if not shutil.which("qlmanage"):
        print("qlmanage is required (macOS Quick Look)", file=sys.stderr)
        return 1

    pdf = canvas.Canvas(str(OUT), pagesize=(PAGE_W, PAGE_H))
    pdf.setTitle("AutoCurricula & GradeSync Engine - architecture diagrams")
    pdf.setAuthor("Quanta")

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for index, (name, label, caption) in enumerate(ORDER, start=1):
            svg = MEDIA / f"{name}.svg"
            aspect = expected_aspect(svg)
            trimmed = trim(render(svg, workdir), aspect)
            width, height = Image.open(trimmed).size
            drift = abs(width / height - aspect)
            if drift > 0.01:
                raise RuntimeError(f"{name}: trimmed aspect drifted by {drift:.4f}")
            place(pdf, trimmed, label, caption, index, len(ORDER))
            print(f"{index:>2}. {name:<17} {width} x {height}")

    pdf.save()
    print(f"\n{OUT.relative_to(Path.cwd())}  ({OUT.stat().st_size / 1_048_576:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
