from __future__ import annotations

from dataclasses import dataclass

from sare_lotofacil.experiments.backtest import BacktestWindow, validate_backtest_window


ALLOWED_CONFIRMATORY_STOPPING_RULES = frozenset(
    {
        "fixed_snapshot_no_optional_stopping",
        "fixed_sample_no_optional_stopping",
        "fixed_horizon_no_optional_stopping",
    }
)


class OptionalStoppingViolation(ValueError):
    def __init__(self, rule: str) -> None:
        self.code = "OPTIONAL_STOPPING_FORBIDDEN"
        self.rule = rule
        super().__init__(f"{self.code}: {rule}")


@dataclass(frozen=True, slots=True)
class PerformanceGapLeakageAssessment:
    status: str
    train_metric: float
    test_metric: float
    test_minus_train: float
    leakage_detected: bool
    basis: str


def assess_performance_gap_for_leakage(
    window: BacktestWindow,
    *,
    train_metric: float,
    test_metric: float,
) -> PerformanceGapLeakageAssessment:
    """T26: diferença de desempenho não é evidência de leakage por si só.

    Leakage é decidido pela proveniência temporal do ``BacktestWindow``. Se a
    janela passa no validador canônico, um teste numericamente melhor que treino
    permanece apenas uma diferença observada, nunca um diagnóstico de vazamento.
    """
    validate_backtest_window(window)
    return PerformanceGapLeakageAssessment(
        status="NO_LEAKAGE_EVIDENCE_FROM_PERFORMANCE_GAP",
        train_metric=float(train_metric),
        test_metric=float(test_metric),
        test_minus_train=float(test_metric) - float(train_metric),
        leakage_detected=False,
        basis="TEMPORAL_PROVENANCE_ONLY",
    )


def enforce_confirmatory_stopping_rule(rule: str) -> str:
    normalized = str(rule).strip()
    if normalized not in ALLOWED_CONFIRMATORY_STOPPING_RULES:
        raise OptionalStoppingViolation(normalized)
    return normalized
