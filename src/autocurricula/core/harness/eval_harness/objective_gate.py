from pydantic import Field

from autocurricula.schemas.common import StrictBaseModel
from autocurricula.schemas.metrics import CalibrationMetrics

DEFAULT_QWK_MIN = 0.85
DEFAULT_MAE_MAX = 0.4
DEFAULT_BIAS_ABS_MAX = 0.1


class ObjectiveThresholds(StrictBaseModel):
    qwk_min: float | None = DEFAULT_QWK_MIN
    mae_max: float | None = DEFAULT_MAE_MAX
    bias_abs_max: float | None = DEFAULT_BIAS_ABS_MAX

    @staticmethod
    def grading() -> "ObjectiveThresholds":
        return ObjectiveThresholds()

    @staticmethod
    def auditor() -> "ObjectiveThresholds":
        return ObjectiveThresholds(qwk_min=None, bias_abs_max=0.3)


class GateOutcome(StrictBaseModel):
    passed: bool
    reasons: list[str] = Field(default_factory=list)


class ObjectiveGate:
    def __init__(self, thresholds: ObjectiveThresholds | None = None) -> None:
        self._thresholds = thresholds if thresholds is not None else ObjectiveThresholds()

    @property
    def thresholds(self) -> ObjectiveThresholds:
        return self._thresholds

    def evaluate(self, metrics: CalibrationMetrics) -> GateOutcome:
        reasons: list[str] = []
        thresholds = self._thresholds
        if thresholds.qwk_min is not None and metrics.quadratic_weighted_kappa < thresholds.qwk_min:
            reasons.append(
                f"qwk {metrics.quadratic_weighted_kappa:.3f} < {thresholds.qwk_min:.2f}"
            )
        if thresholds.mae_max is not None and metrics.mae > thresholds.mae_max:
            reasons.append(f"mae {metrics.mae:.3f} > {thresholds.mae_max:.2f}")
        if thresholds.bias_abs_max is not None and abs(metrics.bias) >= thresholds.bias_abs_max:
            reasons.append(
                f"|bias| {abs(metrics.bias):.3f} >= {thresholds.bias_abs_max:.2f}"
            )
        return GateOutcome(passed=not reasons, reasons=reasons)
