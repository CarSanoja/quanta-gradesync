import pytest
from pydantic import ValidationError

from autocurricula.core.evolution.prompt_mutator import PromptRegistry, PromptVariant

pytestmark = pytest.mark.calibration


def _variant(
    version: int,
    variant_id: str = "grading_default",
    instruction: str | None = None,
    few_shots: tuple[str, ...] = ("Q1: full marks with cited page evidence.",),
    provenance: str = "seed",
) -> PromptVariant:
    return PromptVariant(
        variant_id=variant_id,
        version=version,
        system_instruction=instruction or f"Assess strictly against the rubric, rev {version}.",
        few_shots=list(few_shots),
        provenance=provenance,
    )


def test_registry_enforces_monotonic_versioning():
    registry = PromptRegistry()
    first = _variant(1)
    second = _variant(2)

    registry.register(first)
    assert registry.get("grading_default") == first
    registry.register(second)
    assert registry.get("grading_default") == second
    assert registry.get_latest("grading_default").version == 2
    assert [variant.version for variant in registry.history("grading_default")] == [1, 2]
    assert "grading_default" in registry
    assert len(registry) == 1

    with pytest.raises(ValueError, match="must exceed active version"):
        registry.register(_variant(1))
    with pytest.raises(ValueError, match="must exceed active version"):
        registry.register(_variant(2))


def test_registry_tracks_multiple_lineages():
    registry = PromptRegistry()
    registry.register(_variant(1, variant_id="alpha"))
    registry.register(_variant(3, variant_id="beta"))

    assert registry.variant_ids == ("alpha", "beta")
    assert len(registry) == 2
    assert registry.get("alpha").version == 1
    assert registry.get("beta").version == 3


def test_unknown_variant_access_raises():
    registry = PromptRegistry()

    with pytest.raises(ValueError, match="unknown prompt variant"):
        registry.get("ghost")
    with pytest.raises(ValueError, match="unknown prompt variant"):
        registry.history("ghost")
    with pytest.raises(ValueError, match="unknown prompt variant"):
        registry.rollback("ghost")
    with pytest.raises(ValueError, match="unknown prompt variant"):
        registry.get_version("ghost", 1)


def test_get_version_returns_registered_entries():
    registry = PromptRegistry()
    first = _variant(1)
    second = _variant(2)
    registry.register(first)
    registry.register(second)

    assert registry.get_version("grading_default", 1) == first
    assert registry.get_version("grading_default", 2) == second
    with pytest.raises(ValueError, match="has no version"):
        registry.get_version("grading_default", 7)


def test_rollback_moves_active_pointer_and_truncates_on_register():
    registry = PromptRegistry()
    registry.register(_variant(1))
    registry.register(_variant(2))
    registry.register(_variant(3))

    assert registry.rollback().version == 2
    assert registry.rollback().version == 1
    with pytest.raises(ValueError, match="cannot rollback"):
        registry.rollback()

    replacement = _variant(2, instruction="Assess with mastery language.", provenance="meta")
    registry.register(replacement)

    assert registry.get("grading_default") == replacement
    assert [v.version for v in registry.history("grading_default")] == [1, 2]
    with pytest.raises(ValueError, match="has no version"):
        registry.get_version("grading_default", 3)


def test_serialize_round_trip_preserves_lineages():
    registry = PromptRegistry()
    registry.register(_variant(1, variant_id="alpha"))
    registry.register(_variant(2, variant_id="alpha"))
    registry.register(_variant(1, variant_id="beta"))

    payload = registry.serialize()
    restored = PromptRegistry.from_payload(payload)

    assert restored.variant_ids == ("alpha", "beta")
    assert restored.get("alpha").version == 2
    assert restored.get("beta").version == 1
    assert restored.get_version("alpha", 1) == registry.get_version("alpha", 1)
    assert restored.serialize() == payload


def test_serialize_respects_rolled_back_active_version():
    registry = PromptRegistry()
    registry.register(_variant(1))
    registry.register(_variant(2))
    registry.rollback()

    payload = registry.serialize()
    restored = PromptRegistry.from_payload(payload)

    assert restored.get("grading_default").version == 1
    assert payload[0]["active_version"] == 1


def test_from_payload_rejects_missing_active_version():
    payload = [
        {
            "variant_id": "grading_default",
            "entries": [_variant(1).to_dict()],
            "active_version": 5,
        }
    ]

    with pytest.raises(ValueError, match="no active version"):
        PromptRegistry.from_payload(payload)


def test_variant_validation_and_immutability():
    with pytest.raises(ValidationError):
        PromptVariant(
            variant_id="grading_default",
            version=0,
            system_instruction="Assess strictly.",
            provenance="seed",
        )
    with pytest.raises(ValidationError):
        PromptVariant(
            variant_id="grading_default",
            version=1,
            system_instruction="   ",
            provenance="seed",
        )
    with pytest.raises(ValidationError):
        PromptVariant(
            variant_id="grading_default",
            version=1,
            system_instruction="Assess strictly.",
            few_shots=["Q1: full marks.", "  "],
            provenance="seed",
        )

    variant = _variant(1)
    with pytest.raises(ValidationError):
        variant.version = 5

    assert PromptVariant.from_dict(variant.to_dict()) == variant
    with pytest.raises(ValidationError):
        PromptVariant.from_dict({**variant.to_dict(), "extra": "field"})
