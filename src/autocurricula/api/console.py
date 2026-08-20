from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

console_router = APIRouter(tags=["console"])

STATIC_DIR = Path(__file__).parent / "static"
CONSOLE_PAGE = "console.html"

ASSET_MEDIA_TYPES = {
    "console.css": "text/css; charset=utf-8",
    "console.js": "text/javascript; charset=utf-8",
    "api.js": "text/javascript; charset=utf-8",
    "views.js": "text/javascript; charset=utf-8",
    "render.js": "text/javascript; charset=utf-8",
    "sis.js": "text/javascript; charset=utf-8",
    "ingest.js": "text/javascript; charset=utf-8",
    "trace.js": "text/javascript; charset=utf-8",
}


def asset_path(name: str) -> Path:
    return STATIC_DIR / name


@console_router.get("/console", response_class=FileResponse)
async def console_page() -> FileResponse:
    page = asset_path(CONSOLE_PAGE)
    if not page.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="console page is not bundled"
        )
    return FileResponse(page, media_type="text/html; charset=utf-8")


@console_router.get("/console/assets/{asset_name}", response_class=FileResponse)
async def console_asset(asset_name: str) -> FileResponse:
    media_type = ASSET_MEDIA_TYPES.get(asset_name)
    if media_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown console asset {asset_name!r}",
        )
    path = asset_path(asset_name)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"console asset {asset_name!r} is not bundled",
        )
    return FileResponse(path, media_type=media_type)
