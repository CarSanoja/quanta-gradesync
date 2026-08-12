from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import Field, field_validator

from autocurricula.schemas.common import FrozenStrictModel


class PromptVariant(FrozenStrictModel):
    variant_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    system_instruction: str = Field(min_length=1)
    few_shots: list[str] = Field(default_factory=list)
    provenance: str = Field(min_length=1)

    @field_validator("system_instruction")
    @classmethod
    def _non_blank_instruction(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("system_instruction must not be blank")
        return value

    @field_validator("few_shots")
    @classmethod
    def _non_empty_shots(cls, value: list[str]) -> list[str]:
        if any(not shot.strip() for shot in value):
            raise ValueError("few_shots must be non-empty strings")
        return value

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PromptVariant":
        return cls.model_validate(dict(data))


class _VariantLineage:
    def __init__(self, entries: list[PromptVariant], active_index: int) -> None:
        self.entries = entries
        self.active_index = active_index

    @property
    def active(self) -> PromptVariant:
        return self.entries[self.active_index]

    def retained_entries(self) -> list[PromptVariant]:
        return self.entries[: self.active_index + 1]


class PromptRegistry:
    def __init__(self) -> None:
        self._lineages: dict[str, _VariantLineage] = {}

    def register(self, variant: PromptVariant) -> None:
        lineage = self._lineages.get(variant.variant_id)
        if lineage is None:
            self._lineages[variant.variant_id] = _VariantLineage([variant], 0)
            return
        if variant.version <= lineage.active.version:
            raise ValueError(
                f"variant {variant.variant_id!r} version {variant.version} must exceed active version {lineage.active.version}"
            )
        retained = lineage.retained_entries()
        retained.append(variant)
        lineage.entries = retained
        lineage.active_index = len(retained) - 1

    def get(self, variant_id: str) -> PromptVariant:
        return self._require(variant_id).active

    def get_latest(self, variant_id: str) -> PromptVariant:
        return self.get(variant_id)

    def get_version(self, variant_id: str, version: int) -> PromptVariant:
        for variant in self._require(variant_id).entries:
            if variant.version == version:
                return variant
        raise ValueError(f"variant {variant_id!r} has no version {version}")

    def rollback(self, variant_id: str | None = None) -> PromptVariant:
        resolved_id = variant_id if variant_id is not None else self._sole_variant_id()
        lineage = self._require(resolved_id)
        if lineage.active_index == 0:
            raise ValueError(
                f"cannot rollback variant {resolved_id!r} at its initial version"
            )
        lineage.active_index -= 1
        return lineage.active

    def history(self, variant_id: str) -> list[PromptVariant]:
        return list(self._require(variant_id).entries)

    @property
    def variant_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._lineages))

    def __len__(self) -> int:
        return len(self._lineages)

    def __contains__(self, variant_id: object) -> bool:
        return variant_id in self._lineages

    def serialize(self) -> list[dict[str, Any]]:
        return [
            {
                "variant_id": variant_id,
                "entries": [variant.to_dict() for variant in lineage.retained_entries()],
                "active_version": lineage.active.version,
            }
            for variant_id, lineage in sorted(self._lineages.items())
        ]

    @classmethod
    def from_payload(cls, payload: Sequence[Mapping[str, Any]]) -> "PromptRegistry":
        registry = cls()
        for lineage_data in payload:
            entries = [PromptVariant.from_dict(entry) for entry in lineage_data["entries"]]
            if not entries:
                raise ValueError("serialized prompt lineage must contain at least one entry")
            active_version = int(lineage_data["active_version"])
            active_index = next(
                (index for index, variant in enumerate(entries) if variant.version == active_version),
                -1,
            )
            if active_index < 0:
                raise ValueError(f"serialized lineage has no active version {active_version}")
            variant_id = entries[0].variant_id
            if any(variant.variant_id != variant_id for variant in entries):
                raise ValueError("serialized lineage entries must share a single variant_id")
            registry._lineages[variant_id] = _VariantLineage(entries, active_index)
        return registry

    def _require(self, variant_id: str) -> _VariantLineage:
        lineage = self._lineages.get(variant_id)
        if lineage is None:
            raise ValueError(f"unknown prompt variant {variant_id!r}")
        return lineage

    def _sole_variant_id(self) -> str:
        if len(self._lineages) == 1:
            return next(iter(self._lineages))
        raise ValueError("rollback requires variant_id when multiple lineages exist")
