from pathlib import Path

from autocurricula.agents.audit_calibration import build_audit_evaluator
from autocurricula.agents.calibration_evaluator import build_calibration_evaluator
from autocurricula.agents.curriculum_auditor import build_curriculum_auditor
from autocurricula.agents.optimizer_factory import build_proposer
from autocurricula.agents.prompts import build_grading_prompt_variant
from autocurricula.api.dependencies import build_container
from autocurricula.config.settings import Settings
from autocurricula.core.fleet import build_fleet_registry
from autocurricula.core.fleet.bindings import SETTINGS_BINDINGS
from autocurricula.core.fleet.roster import (
    AGENT_DECLARATIONS,
    CALIBRATION_EVALUATOR_ID,
    CURRICULUM_AUDITOR_ID,
    GRADING_AGENT_ID,
    PROMPT_PROPOSER_ID,
)
from autocurricula.core.orchestration.context import PIPELINE_STAGE_ORDER


def local_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "local_mode": True,
        "gcp_project_id": "",
        "local_data_dir": tmp_path / "local_data",
        "gcs_local_staging_dir": tmp_path / "staging",
    }
    values.update(overrides)
    return Settings(**values)


def agent(report, agent_id: str):
    return next(item for item in report.agents if item.agent_id == agent_id)


def test_registry_enumerates_the_declared_fleet(tmp_path: Path) -> None:
    report = build_fleet_registry(local_settings(tmp_path))

    assert report.summary.agent_count == 12
    assert [item.fleet_index for item in report.agents] == list(range(1, 13))
    assert len({item.agent_id for item in report.agents}) == 12
    assert all(item.role.strip() for item in report.agents)


def test_every_declared_stage_is_a_real_pipeline_stage() -> None:
    declared = {stage for item in AGENT_DECLARATIONS for stage in item.stages}

    assert declared <= set(PIPELINE_STAGE_ORDER)


def test_model_is_derived_from_the_wired_container(tmp_path: Path) -> None:
    settings = local_settings(tmp_path)
    container = build_container(settings)
    report = build_fleet_registry(settings, container)
    grading = agent(report, GRADING_AGENT_ID)

    assert grading.model_id == container.grading_evaluator.model
    assert grading.model_source.value == "container"
    assert grading.runtime_binding == type(container.grading_evaluator).__name__


def test_model_follows_settings_for_agents_the_container_cannot_expose(
    tmp_path: Path,
) -> None:
    settings = local_settings(
        tmp_path, local_mode=False, gcp_project_id="fleet-test", armor_enabled=True
    )
    report = build_fleet_registry(settings)

    assert agent(report, CURRICULUM_AUDITOR_ID).model_id == settings.gemini_flash_model
    assert agent(report, CALIBRATION_EVALUATOR_ID).model_id == settings.gemini_pro_model
    assert agent(report, CALIBRATION_EVALUATOR_ID).model_source.value == "settings"


def test_definition_hash_tracks_the_effective_definition(tmp_path: Path) -> None:
    baseline = build_fleet_registry(local_settings(tmp_path))
    moved = build_fleet_registry(
        local_settings(tmp_path, gemini_pro_model="gemini-3.5-pro")
    )

    assert agent(baseline, GRADING_AGENT_ID).definition_sha != agent(
        moved, GRADING_AGENT_ID
    ).definition_sha
    assert baseline.summary.registry_sha != moved.summary.registry_sha
    assert (
        build_fleet_registry(local_settings(tmp_path)).summary.registry_sha
        == baseline.summary.registry_sha
    )


def test_prompt_binding_is_read_from_the_live_optimizer_registry(
    tmp_path: Path,
) -> None:
    settings = local_settings(tmp_path)
    container = build_container(settings)
    seed = build_grading_prompt_variant()
    promoted = seed.model_copy(update={"version": seed.version + 1})
    for optimizer in container.optimizers:
        if optimizer.variant_id == promoted.variant_id:
            optimizer.registry.register(promoted)
    report = build_fleet_registry(settings, container)
    binding = agent(report, GRADING_AGENT_ID).prompt

    assert binding is not None
    assert binding.version == promoted.version
    assert binding.source == "registry"


def test_declared_bindings_match_what_the_builders_actually_return(
    tmp_path: Path,
) -> None:
    settings = local_settings(tmp_path)
    actual = {
        CURRICULUM_AUDITOR_ID: type(build_curriculum_auditor(settings)).__name__,
        PROMPT_PROPOSER_ID: type(build_proposer(settings)).__name__,
        CALIBRATION_EVALUATOR_ID: type(build_calibration_evaluator(settings)).__name__,
    }
    for agent_id, binding in actual.items():
        assert SETTINGS_BINDINGS[agent_id][1] == binding, agent_id
    assert type(build_audit_evaluator(settings)).__name__ == "LocalAuditEvaluator"
