from typing import Annotated

from pydantic import Field

from autocurricula.schemas.common import FrozenStrictModel

SHA256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Provenance(FrozenStrictModel):
    prompt_variant_id: str = Field(min_length=1)
    prompt_version_sha: SHA256Hex
    evidence_hashes: list[str] = Field(default_factory=list)
    model_sha: SHA256Hex | None = None
    faithfulness_checked: bool | None = None
    agent_id: str | None = None
    writer_principal: str | None = None
