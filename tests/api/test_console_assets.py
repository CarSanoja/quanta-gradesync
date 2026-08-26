import re

import httpx
import pytest

from autocurricula.api.console import ASSET_MEDIA_TYPES, asset_path

RELATIVE_IMPORT = re.compile(r"from\s+\"\./([A-Za-z0-9_.-]+)\"")

LIVE_SCRIPTS = (
    "live.js",
    "live-board.js",
    "live-header.js",
    "live-ticker.js",
    "live-detail.js",
    "live-chain.js",
    "live-chain-groups.js",
    "live-kinds.js",
)
LIVE_STYLES = ("live.css",)
LIVE_ASSETS = LIVE_SCRIPTS + LIVE_STYLES


@pytest.mark.parametrize("asset", LIVE_ASSETS)
def test_mission_control_assets_are_whitelisted(asset: str) -> None:
    assert asset in ASSET_MEDIA_TYPES


@pytest.mark.parametrize("asset", LIVE_ASSETS)
def test_mission_control_assets_are_bundled(asset: str) -> None:
    assert asset_path(asset).is_file()


@pytest.mark.parametrize("asset", LIVE_SCRIPTS)
async def test_live_scripts_are_served_as_javascript(
    client: httpx.AsyncClient, asset: str
) -> None:
    response = await client.get(f"/console/assets/{asset}")
    assert response.status_code == 200, asset
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.text


@pytest.mark.parametrize("asset", LIVE_STYLES)
async def test_live_styles_are_served_as_css(client: httpx.AsyncClient, asset: str) -> None:
    response = await client.get(f"/console/assets/{asset}")
    assert response.status_code == 200, asset
    assert response.headers["content-type"].startswith("text/css")
    assert response.text


def test_every_module_import_is_whitelisted() -> None:
    missing = set()
    for name in ASSET_MEDIA_TYPES:
        source = asset_path(name)
        if not name.endswith(".js") or not source.is_file():
            continue
        for target in RELATIVE_IMPORT.findall(source.read_text(encoding="utf-8")):
            if target not in ASSET_MEDIA_TYPES:
                missing.add(f"{name} imports {target}")
    assert not missing


async def test_live_assets_do_not_need_the_push_token(client: httpx.AsyncClient) -> None:
    response = await client.get("/console/assets/live-ticker.js")
    assert response.status_code == 200
    assert "renderTicker" in response.text


@pytest.mark.parametrize(
    "asset",
    ["live-secrets.js", "live.js.map", "live-chain.ts", "%2e%2e%2flive.js", "live"],
)
async def test_unknown_live_assets_stay_404(client: httpx.AsyncClient, asset: str) -> None:
    response = await client.get(f"/console/assets/{asset}")
    assert response.status_code == 404, asset
