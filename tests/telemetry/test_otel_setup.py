import os
from collections.abc import Iterator
from typing import Any

import pytest
from google.adk.telemetry import google_cloud
from google.adk.telemetry import setup as adk_setup

from autocurricula.config.settings import Settings
from autocurricula.core.telemetry.llm_capture import LlmSpanCapture
from autocurricula.core.telemetry.otel_setup import (
    CAPTURE_CONTENT_ENV,
    SERVICE_NAME,
    SERVICE_NAME_ENV,
    gcp_hooks,
    install_telemetry,
    reset_telemetry_install,
)


@pytest.fixture(autouse=True)
def fresh_install() -> Iterator[None]:
    reset_telemetry_install()
    try:
        yield
    finally:
        reset_telemetry_install()


@pytest.fixture
def installed_hooks(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    recorded: list[Any] = []

    def fake_setup(hooks: list[Any]) -> None:
        recorded.extend(hooks)

    monkeypatch.setattr(adk_setup, "maybe_set_otel_providers", fake_setup)
    monkeypatch.delenv(CAPTURE_CONTENT_ENV, raising=False)
    monkeypatch.delenv(SERVICE_NAME_ENV, raising=False)
    return recorded


def local_settings(**overrides: Any) -> Settings:
    return Settings(local_mode=True, gcp_project_id="", **overrides)


def gcp_settings(**overrides: Any) -> Settings:
    return Settings(local_mode=False, gcp_project_id="quanta-gradesync", **overrides)


def test_local_install_registers_only_the_capture_processor(
    installed_hooks: list[Any],
) -> None:
    settings = local_settings()
    capture = LlmSpanCapture(settings)

    assert install_telemetry(settings, capture) is True
    assert len(installed_hooks) == 1
    assert installed_hooks[0].span_processors == [capture]


def test_install_is_idempotent_until_it_is_reset(installed_hooks: list[Any]) -> None:
    settings = local_settings()
    capture = LlmSpanCapture(settings)

    assert install_telemetry(settings, capture) is True
    assert install_telemetry(settings, capture) is False
    assert len(installed_hooks) == 1

    reset_telemetry_install()
    assert install_telemetry(settings, capture) is True
    assert len(installed_hooks) == 2


def test_install_names_the_service_and_keeps_content_capture_on(
    installed_hooks: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = local_settings(telemetry_capture_content=True)

    install_telemetry(settings, LlmSpanCapture(settings))

    assert os.environ[SERVICE_NAME_ENV] == SERVICE_NAME
    assert CAPTURE_CONTENT_ENV not in os.environ


def test_disabling_content_capture_silences_adk_payloads(
    installed_hooks: list[Any],
) -> None:
    settings = local_settings(telemetry_capture_content=False)

    install_telemetry(settings, LlmSpanCapture(settings))

    assert os.environ[CAPTURE_CONTENT_ENV] == "false"


def test_provider_failures_are_reported_not_raised(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(hooks: list[Any]) -> None:
        raise RuntimeError("no provider today")

    monkeypatch.setattr(adk_setup, "maybe_set_otel_providers", explode)
    settings = local_settings()

    assert install_telemetry(settings, LlmSpanCapture(settings)) is False


def test_gcp_hooks_are_skipped_in_local_mode() -> None:
    assert gcp_hooks(local_settings()) is None


def test_gcp_hooks_are_skipped_when_cloud_trace_is_disabled() -> None:
    assert gcp_hooks(gcp_settings(telemetry_cloud_trace_enabled=False)) is None


def test_gcp_hooks_build_cloud_exporters(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    sentinel = object()

    def fake_exporters(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return sentinel

    monkeypatch.setattr(google_cloud, "get_gcp_exporters", fake_exporters)

    assert gcp_hooks(gcp_settings(telemetry_cloud_metrics_enabled=False)) is sentinel
    assert calls == [{"enable_cloud_tracing": True, "enable_cloud_metrics": False}]


def test_missing_credentials_do_not_break_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(**kwargs: Any) -> Any:
        raise RuntimeError("no application default credentials")

    monkeypatch.setattr(google_cloud, "get_gcp_exporters", explode)

    assert gcp_hooks(gcp_settings()) is None


def test_gcp_install_appends_the_cloud_hooks(
    installed_hooks: list[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    sentinel = object()
    monkeypatch.setattr(google_cloud, "get_gcp_exporters", lambda **kwargs: sentinel)
    settings = gcp_settings()

    assert install_telemetry(settings, LlmSpanCapture(settings)) is True
    assert installed_hooks[-1] is sentinel
    assert len(installed_hooks) == 2
