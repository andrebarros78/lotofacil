from __future__ import annotations

import unicodedata
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


def _fold_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).lower()


def enforce_confirmatory_stopping_rule(rule: str) -> str:
    """Aceita regras fixas/predefinidas e bloqueia parada dependente do resultado.

    O campo permanece humano/auditável, inclusive em português. A validação não
    exige uma frase única, mas requer evidência textual de desenho fixo e rejeita
    marcadores típicos de optional stopping orientado por p-valor/significância.
    """
    normalized = str(rule).strip()
    if normalized in ALLOWED_CONFIRMATORY_STOPPING_RULES:
        return normalized
    folded = _fold_text(normalized)
    fixed_markers = ("fixed", "fixo", "fixa", "predefin", "pre-registr", "preregister")
    opportunistic_markers = (
        "p<",
        "p <",
        "pvalue",
        "p_value",
        "p-valor",
        "p valor",
        "signific",
        "until_p",
        "until p",
        "ate p",
        "favoravel",
        "favorable",
        "parada por conveniencia",
        "stop when",
        "stop_when",
    )
    explicitly_no_opportunistic = "sem parada oportunista" in folded or "no optional stopping" in folded
    has_fixed_design = any(marker in folded for marker in fixed_markers)
    has_opportunistic_marker = any(marker in folded for marker in opportunistic_markers)
    if not has_fixed_design or (has_opportunistic_marker and not explicitly_no_opportunistic):
        raise OptionalStoppingViolation(normalized)
    return normalized
