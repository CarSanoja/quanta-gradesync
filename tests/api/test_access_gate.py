import httpx
import pytest

pytestmark = pytest.mark.anyio


async def test_the_pages_open_so_the_code_can_be_typed(client: httpx.AsyncClient) -> None:
    """A bare 401 on /teacher would leave a judge with nowhere to enter it."""
    for path in ("/teacher", "/console", "/readyz"):
        assert (await client.get(path)).status_code == 200, path


async def test_assets_and_diagrams_stay_reachable(client: httpx.AsyncClient) -> None:
    assert (await client.get("/console/assets/console.css")).status_code == 200
    assert (await client.get("/console/diagrams/fleet.svg")).status_code == 200
    assert (await client.get("/teacher/assets/teacher.css")).status_code == 200


async def test_everything_carrying_data_needs_the_code(client: httpx.AsyncClient) -> None:
    for path in ("/jobs", "/review/pending", "/teacher/summary", "/fleet/registry",
                 "/sis/ledger", "/labels", "/optimizer/report"):
        assert (await client.get(path)).status_code in (401, 404), path


async def test_the_api_surface_is_not_public(client: httpx.AsyncClient) -> None:
    """openapi.json handed over every route and every schema to anyone."""
    assert (await client.get("/openapi.json")).status_code == 401


async def test_a_bad_body_is_refused_before_it_is_validated(client: httpx.AsyncClient) -> None:
    """The check used to sit inside the handler, so FastAPI validated first.

    An unauthenticated caller could send anything, read the 422 back, and learn
    the schema. There was no bypass, but there was no reason to answer either.
    """
    response = await client.post("/review/bulk-approve", json={})

    assert response.status_code == 401
    assert "review_ids" not in response.text


async def test_a_wrong_code_is_rejected_not_merely_unauthorised(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/jobs", headers={"Authorization": "Bearer not-the-code"})

    assert response.status_code == 403


async def test_the_code_works_as_a_header_or_a_query_parameter(
    client: httpx.AsyncClient, auth_headers: dict[str, str], push_token: str
) -> None:
    """Pub/Sub push occupies the Authorization header with its OIDC token."""
    assert (await client.get("/jobs", headers=auth_headers)).status_code == 200
    assert (await client.get(f"/jobs?token={push_token}")).status_code == 200
