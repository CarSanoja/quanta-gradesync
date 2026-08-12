import httpx

from autocurricula.api.dependencies import AppContainer
from autocurricula.config.settings import Settings


async def test_healthz_reports_ok(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_local_mode_reports_ready(
    client: httpx.AsyncClient, api_settings: Settings
) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "mode": "local"}
    assert api_settings.local_data_dir.is_dir()


async def test_readyz_reports_incomplete_gcp_settings(
    client: httpx.AsyncClient, container: AppContainer
) -> None:
    container.settings = container.settings.model_copy(
        update={"local_mode": False, "gcp_project_id": ""}
    )
    response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["mode"] == "gcp"
    assert "gcp_project_id" in body["reason"]


async def test_readyz_gcp_mode_without_firestore_reports_unavailable(
    client: httpx.AsyncClient, container: AppContainer
) -> None:
    container.settings = Settings(
        local_mode=False,
        gcp_project_id="test-project",
        pubsub_push_token=container.settings.pubsub_push_token,
        sis_base_url="https://sis.example.test/api/v1",
        local_data_dir=container.settings.local_data_dir,
        gcs_local_staging_dir=container.settings.gcs_local_staging_dir,
    )
    response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["mode"] == "gcp"
    assert "firestore" in body["reason"]
