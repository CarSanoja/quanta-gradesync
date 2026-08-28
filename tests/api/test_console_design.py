from pathlib import Path

import httpx
import pytest

from autocurricula.api.main import create_app

STATIC = Path("src/autocurricula/api/static")

STYLES = ("console.css", "console-views.css", "live.css")
MODULES = ("console-sections.js",)

RAIL = (
    ("01", "jobs", "Jobs timeline"),
    ("02", "review", "Review queue"),
    ("03", "optimizer", "Optimizer"),
    ("04", "fleet", "Fleet"),
    ("05", "ingest", "Ingest"),
    ("06", "sis", "SIS ledger"),
    ("07", "trace", "Mission control"),
)


def source(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


@pytest.fixture
def app():
    return create_app()


async def test_the_console_serves_every_stylesheet_and_module_of_the_design(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for name in STYLES:
            response = await client.get(f"/console/assets/{name}")
            assert response.status_code == 200, name
            assert response.headers["content-type"].startswith("text/css")
        for name in MODULES:
            response = await client.get(f"/console/assets/{name}")
            assert response.status_code == 200, name
            assert response.headers["content-type"].startswith("text/javascript")


def test_the_page_links_the_stylesheets_and_numbers_every_rail_item() -> None:
    page = source("console.html")

    for name in STYLES:
        assert f"/console/assets/{name}" in page
    for index, view, label in RAIL:
        assert f'data-view="{view}"' in page
        assert f'<span class="rail-index" aria-hidden="true">{index}</span>' in page
        assert f'<span class="rail-label">{label}</span>' in page
    assert 'id="section-title"' in page
    assert 'id="section-sub"' in page
    assert 'id="rail-badge-review"' in page
    assert 'id="rail-badge-live"' in page


def test_the_nocturne_tokens_are_the_ones_of_the_import() -> None:
    styles = source("console.css")

    assert "--bg: #161826;" in styles
    assert "--accent: #9184d9;" in styles
    assert "--ink: #e9e9ed;" in styles
    assert "--surface: #232532;" in styles
    assert "Inter" in styles and "JetBrains Mono" in styles
    assert "@keyframes noct-pulse" in styles
    assert "@keyframes noct-sweep" in styles


def test_primary_actions_are_outlined_never_flooded_with_the_accent() -> None:
    styles = source("console.css")

    assert "button.primary { border-color: var(--accent); color: var(--accent-light); }" in styles
    assert "background: var(--accent);\n  color: #fff" not in styles


def test_one_low_chroma_alert_survives_the_mono_palette() -> None:
    """An operations console has to separate a failure from a quiet state."""
    styles = source("console.css")
    views = source("console-views.css")

    assert "--alert: #dd8a83;" in styles
    assert '.pill[data-state="failed"], .pill[data-state="dismissed"]' in views
    assert "color: var(--alert)" in views


def test_the_header_names_the_section_you_are_looking_at() -> None:
    sections = source("console-sections.js")
    console = source("console.js")

    assert 'jobs: ["Jobs timeline", "every batch, stage by stage"]' in sections
    assert 'trace: ["Mission control", "watch it happen"]' in sections
    assert "paintSection(view);" in console


def test_the_rail_badges_follow_the_work_and_the_run() -> None:
    sections = source("console-sections.js")

    assert "export function paintReviewBadge(count)" in sections
    assert "export function paintLiveBadge(running)" in sections
    assert "paintReviewBadge(payload.count);" in source("console-review.js")
    assert "paintLiveBadge(running);" in source("live-header.js")


def test_mission_control_keeps_the_model_exchange_next_to_the_feed() -> None:
    live = source("live.css")

    assert "grid-template-columns: minmax(0, 1fr) var(--activity-detail);" in live
    assert "#live-detail { grid-column: 2; grid-row: 1 / span 2; }" in live
    assert ".payload-block {" in live
    assert "background: var(--sunken);" in live


def test_the_running_stage_reads_as_movement_not_as_a_label() -> None:
    live = source("live.css")

    assert 'repeating-linear-gradient(115deg, var(--accent-mid) 0 8px, #4a4278 8px 16px)' in live
    assert "animation: noct-sweep .7s linear infinite;" in live


def test_nothing_in_the_console_is_smaller_than_eleven_pixels() -> None:
    """Nocturne's density is spacing, not type — its own sheet sets a 15px body.

    The first pass shrank the text as well and the console became hard to read
    at a normal viewing distance. This holds the floor.
    """
    import re

    for name in ("console.css", "console-views.css", "live.css"):
        for size in re.findall(r"font-size: (\d+(?:\.\d+)?)px", source(name)):
            if float(size) == 0:  # the icon-only brand mark
                continue
            assert float(size) >= 11, f"{name} has {size}px text"


def test_the_body_matches_the_design_system_it_came_from() -> None:
    assert "font-size: 15px;" in source("console.css")
