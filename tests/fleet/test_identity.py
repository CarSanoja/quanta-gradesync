from pathlib import Path

from autocurricula.config.settings import Settings
from autocurricula.core.fleet import (
    EXAM_FETCHER_PRINCIPAL,
    ORCHESTRATOR_PRINCIPAL,
    SIS_WRITER_PRINCIPAL,
    agent_principals,
    all_principals,
    build_fleet_registry,
)
from autocurricula.core.fleet.credentials import (
    impersonation_enabled,
    principal_service_account,
    sis_writer_authorization,
    sis_writer_firestore_client,
)
from autocurricula.core.fleet.roster import AGENT_DECLARATIONS
from autocurricula.schemas.fleet import Capability

WRITER_SA = "gradesync-sis-writer@quanta-gradesync.iam.gserviceaccount.com"
RUNNER_SA = "autocurricula-runner@quanta-gradesync.iam.gserviceaccount.com"


def gcp_settings(**overrides) -> Settings:
    values = {
        "local_mode": False,
        "gcp_project_id": "quanta-gradesync",
        "runtime_service_account": RUNNER_SA,
        "sis_base_url": "https://sis.example.edu/api/v1",
        "sis_api_token": "static-sis-token",
    }
    values.update(overrides)
    return Settings(**values)


def local_settings(tmp_path: Path) -> Settings:
    return Settings(
        local_mode=True,
        gcp_project_id="",
        local_data_dir=tmp_path / "local_data",
        gcs_local_staging_dir=tmp_path / "staging",
    )


def test_every_agent_maps_to_its_own_principal(tmp_path: Path) -> None:
    principals = agent_principals(local_settings(tmp_path))

    assert set(principals) == {item.agent_id for item in AGENT_DECLARATIONS}
    assert len({item.principal_id for item in principals.values()}) == len(principals)


def test_no_agent_principal_can_write_to_the_sis(tmp_path: Path) -> None:
    principals = agent_principals(local_settings(tmp_path))

    assert all(
        Capability.SIS_WRITE not in principal.capabilities
        for principal in principals.values()
    )
    writer = next(
        principal
        for principal in all_principals(local_settings(tmp_path))
        if principal.principal_id == SIS_WRITER_PRINCIPAL
    )
    assert Capability.SIS_WRITE in writer.capabilities


def test_infrastructure_principals_are_least_privilege(tmp_path: Path) -> None:
    by_id = {
        principal.principal_id: principal
        for principal in all_principals(local_settings(tmp_path))
    }

    assert by_id[EXAM_FETCHER_PRINCIPAL].capabilities == [Capability.GCS_READ]
    assert Capability.SIS_WRITE not in by_id[ORCHESTRATOR_PRINCIPAL].capabilities


def test_local_mode_reports_no_dedicated_service_account(tmp_path: Path) -> None:
    report = build_fleet_registry(local_settings(tmp_path))

    assert report.summary.dedicated_service_accounts == 0
    assert all(
        principal.service_account == "local:in-process"
        for principal in report.principals
    )


def test_dedicated_service_account_is_derived_from_settings() -> None:
    settings = gcp_settings(
        sis_writer_service_account=WRITER_SA, agent_impersonation_enabled=True
    )
    report = build_fleet_registry(settings)
    writer = next(
        principal
        for principal in report.principals
        if principal.principal_id == SIS_WRITER_PRINCIPAL
    )

    assert report.summary.dedicated_service_accounts == 1
    assert writer.service_account == WRITER_SA
    assert writer.dedicated_service_account is True
    assert writer.impersonated is True
    assert all(
        agent.principal.service_account == RUNNER_SA for agent in report.agents
    )


def test_impersonation_stays_off_without_a_configured_service_account() -> None:
    settings = gcp_settings(agent_impersonation_enabled=True)

    assert principal_service_account(settings, SIS_WRITER_PRINCIPAL) == ""
    assert impersonation_enabled(settings, SIS_WRITER_PRINCIPAL) is False
    assert sis_writer_firestore_client(settings) is None


def test_sis_authorization_falls_back_to_the_ambient_token() -> None:
    settings = gcp_settings(sis_writer_service_account=WRITER_SA)

    assert sis_writer_authorization(settings, "static-sis-token") == (
        "Bearer static-sis-token"
    )


def test_failed_impersonation_never_blocks_the_write(monkeypatch) -> None:
    settings = gcp_settings(
        sis_writer_service_account=WRITER_SA, agent_impersonation_enabled=True
    )

    def explode(*args, **kwargs):
        raise RuntimeError("IAM Service Account Credentials unreachable")

    monkeypatch.setattr(
        "autocurricula.core.fleet.credentials.impersonated_id_token", explode
    )

    assert sis_writer_authorization(settings, "static-sis-token") == (
        "Bearer static-sis-token"
    )
