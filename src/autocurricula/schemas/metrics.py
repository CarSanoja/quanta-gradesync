from typing import Annotated, Self

from pydantic import Field, model_validator

from autocurricula.schemas.common import FrozenStrictModel


class CalibrationMetrics(FrozenStrictModel):
    mae: float = Field(ge=0)
    quadratic_weighted_kappa: float = Field(ge=-1, le=1)
    bias: float
    per_criterion: dict[str, Annotated[float, Field(ge=0)]] = Field(default_factory=dict)


class OptimizerReport(FrozenStrictModel):
    iteration: int = Field(ge=0)
    previous_metrics: CalibrationMetrics
    candidate_metrics: CalibrationMetrics
    delta_mae: float
    accepted: bool
    rejected_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rejection_reasons_required(self) -> Self:
        if not self.accepted and not self.rejected_reasons:
            raise ValueError("rejected optimization reports must list at least one reason")
        return self


class TournamentReport(FrozenStrictModel):
    candidates: list[OptimizerReport] = Field(min_length=1)
    winner: OptimizerReport | None = None

    @model_validator(mode="after")
    def _winner_consistency(self) -> Self:
        if self.winner is not None:
            if self.winner not in self.candidates:
                raise ValueError("tournament winner must be one of the candidate reports")
            if not self.winner.accepted:
                raise ValueError("tournament winner must be an accepted report")
        return self
