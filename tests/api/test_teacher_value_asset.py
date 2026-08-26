import httpx
import pytest

from autocurricula.api.main import create_app

VALUE_ASSET = "teacher-value.js"


@pytest.fixture
def app():
    return create_app()


async def test_the_value_module_is_served(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/teacher/assets/{VALUE_ASSET}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/javascript")
    assert "markingTime" in response.text
    assert "five minutes an exam" in response.text
