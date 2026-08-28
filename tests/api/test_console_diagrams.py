from pathlib import Path

import httpx
import pytest

from autocurricula.api.console import DIAGRAMS
from autocurricula.api.main import create_app

STATIC = Path("src/autocurricula/api/static")
MEDIA = Path("docs/media")

# Each diagram is reached from the screen it explains. Two surfaces earn a
# second one; none earns a gallery.
PLACEMENT = {
    "jobs": ["pipeline", "resilience"],
    "review": ["governance"],
    "optimizer": ["self-improvement"],
    "fleet": ["fleet"],
    "ingest": ["exam-lifecycle"],
    "sis": ["containers"],
    "trace": ["architecture"],
}

# Neither describes an operator surface, so neither belongs in the console.
NOT_IN_THE_CONSOLE = ("context", "teacher-journey")


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


@pytest.fixture
def app():
    return create_app()


def test_the_served_copies_are_the_diagrams_in_docs() -> None:
    """docs/media is the source of truth, but docs/ does not ship in the image.

    The copies under static/ are what production serves, so they have to be the
    same bytes. Editing one and not the other is a drift this test turns into a
    failure instead of a diagram that disagrees with the repository.
    """
    for name in DIAGRAMS:
        served = STATIC / "diagrams" / f"{name}.svg"
        original = MEDIA / f"{name}.svg"
        assert served.is_file(), name
        assert served.read_bytes() == original.read_bytes(), name


def test_the_package_ships_the_svgs() -> None:
    """Without this the route 404s in the deployed image and works locally."""
    assert "*.svg" in Path("MANIFEST.in").read_text(encoding="utf-8")


async def test_every_placed_diagram_is_served_and_nothing_else_is(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for names in PLACEMENT.values():
            for name in names:
                response = await client.get(f"/console/diagrams/{name}.svg")
                assert response.status_code == 200, name
                assert response.headers["content-type"].startswith("image/svg+xml")
                assert response.headers["cache-control"] == "no-cache, must-revalidate"
        # a diagram that exists in docs/media but was never whitelisted
        assert (await client.get("/console/diagrams/slide-gcp.svg")).status_code == 404
        assert (await client.get("/console/diagrams/%2e%2e%2fconsole.py")).status_code == 404


def test_each_diagram_hangs_off_the_screen_it_explains() -> None:
    diagrams = source("console-diagrams.js")

    for view, names in PLACEMENT.items():
        assert f"  {view}: [" in diagrams, view
        for name in names:
            assert f'name: "{name}"' in diagrams, name
    for name in NOT_IN_THE_CONSOLE:
        assert f'name: "{name}"' not in diagrams, name


def test_there_is_no_eighth_rail_item_and_no_gallery() -> None:
    """The rail means operational surfaces; a wall of cards is not one click."""
    page = source("console.html")
    diagrams = source("console-diagrams.js")

    assert 'data-view="diagrams"' not in page
    assert 'id="view-diagrams"' not in page
    assert "diagram-grid" not in source("console-views.css")
    assert "diagram-card" not in diagrams


def test_the_trigger_sits_beside_the_section_heading() -> None:
    """Same pixel on every view, so it is safe to hit on camera."""
    page = source("console.html")
    console = source("console.js")

    assert '<span class="section-diagrams" id="section-diagrams"></span>' in page
    assert 'renderTriggers(document.getElementById("section-diagrams"),' in console
    assert "view, openDiagram);" in console


def test_closing_returns_the_keyboard_to_the_trigger() -> None:
    diagrams = source("console-diagrams.js")
    console = source("console.js")

    assert "trigger.addEventListener(\"click\", () => onOpen(entry, trigger));" in diagrams
    assert "diagramOpener = trigger || document.activeElement;" in console
    assert "diagramOpener.focus();" in console


def test_the_modal_closes_three_ways() -> None:
    console = source("console.js")

    assert 'getElementById("diagram-close").addEventListener("click", closeDiagram)' in console
    assert 'if (event.target.id === "diagram-gate") {' in console
    assert 'event.key === "Escape"' in console


def test_the_first_view_is_set_up_like_any_other() -> None:
    """The initial view was only marked in HTML, so nothing ran setView for it."""
    console = source("console.js")

    assert "  setView(state.view);\n  await loadMode();" in console


def test_the_diagram_plate_is_not_pure_white() -> None:
    """The system forbids pure white; the diagrams still need a light ground."""
    assert "--plate: #f3f5fe;" in source("console.css")
    assert "background: var(--plate);" in source("console-views.css")
