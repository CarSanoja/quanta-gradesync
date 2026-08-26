import httpx

from autocurricula.api.dependencies import AppContainer


async def test_fleet_registry_requires_the_push_token(client: httpx.AsyncClient) -> None:
    missing = await client.get("/fleet/registry")
    assert missing.status_code == 401
    wrong = await client.get(
        "/fleet/registry", headers={"Authorization": "Bearer nope"}
    )
    assert wrong.status_code == 403


async def test_fleet_registry_enumerates_the_fleet(
    client: httpx.AsyncClient, auth_headers
) -> None:
    response = await client.get("/fleet/registry", headers=auth_headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["agent_count"] == 12
    assert payload["summary"]["mode"] == "local"
    assert len(payload["agents"]) == 12
    assert sum(payload["summary"]["by_lifecycle"].values()) == 12
    assert sum(payload["summary"]["by_model"].values()) == 12


async def test_fleet_registry_reflects_the_wired_container(
    client: httpx.AsyncClient, container: AppContainer, auth_headers
) -> None:
    payload = (await client.get("/fleet/registry", headers=auth_headers)).json()
    grading = next(
        agent for agent in payload["agents"] if agent["agent_id"] == "grading-agent"
    )

    assert grading["model_id"] == container.grading_evaluator.model
    assert grading["model_source"] == "container"
    assert grading["principal"]["principal_id"] == "agent://grading-agent"
    assert "llm.invoke" in grading["principal"]["capabilities"]
    assert len(grading["definition_sha"]) == 64


async def test_fleet_registry_lists_the_writer_principal(
    client: httpx.AsyncClient, auth_headers
) -> None:
    payload = (await client.get("/fleet/registry", headers=auth_headers)).json()
    principals = {item["principal_id"]: item for item in payload["principals"]}

    assert "sis-writer" in principals
    assert "sis.write" in principals["sis-writer"]["capabilities"]
    assert all(
        "sis.write" not in agent["principal"]["capabilities"]
        for agent in payload["agents"]
    )


async def test_console_ships_the_fleet_panel(client: httpx.AsyncClient) -> None:
    page = await client.get("/console")
    assert page.status_code == 200
    assert "Fleet registry" in page.text

    asset = await client.get("/console/assets/fleet.js")
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("text/javascript")
