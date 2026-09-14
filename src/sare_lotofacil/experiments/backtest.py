from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Callable, Sequence

from sare_lotofacil.statistics.baseline import UNIFORM_BRIER


class BacktestLeakageError(RuntimeError):
    """Bloqueia o experimento quando qualquer informação ultrapassa o corte de treino."""


@dataclass(frozen=True, slots=True)
class TemporalVariable:
    name: str
    available_through_contest: int


@dataclass(frozen=True, slots=True)
class FittedTransform:
    name: str
    fitted_through_contest: int


@dataclass(frozen=True, slots=True)
class BacktestWindow:
    window_id: str
    training_last_contest: int
    target_contest: int
    variables: tuple[TemporalVariable, ...] = ()
    transforms: tuple[FittedTransform, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowOutcome:
    window_id: str
    training_last_contest: int
    target_contest: int
    state: str
    m0_brier: float
    model_brier: float | None
    delta_brier: float | None
    error_type: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class BacktestAuditReport:
    status: str
    predictive_evidence: str
    planned_windows: int
    successful_windows: int
    failed_windows: int
    success_rate: float
    min_successful_windows: int
    min_success_rate: float
    mean_model_brier: float | None
    mean_delta_brier: float | None
    outcomes: tuple[WindowOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_backtest_window(window: BacktestWindow) -> None:
    if not window.window_id.strip():
        raise ValueError("window_id obrigatório")
    if window.training_last_contest <= 0:
        raise ValueError("training_last_contest deve ser positivo")
    if window.target_contest <= window.training_last_contest:
        raise ValueError("target_contest deve ser posterior ao corte de treino")

    leaking_variables = tuple(
        variable
        for variable in window.variables
        if variable.available_through_contest > window.training_last_contest
    )
    if leaking_variables:
        names = ",".join(variable.name for variable in leaking_variables)
        raise BacktestLeakageError(
            f"LOOKAHEAD_LEAKAGE_DETECTED:variables={names};"
            f"training_last={window.training_last_contest};target={window.target_contest}"
        )

    leaking_transforms = tuple(
        transform
        for transform in window.transforms
        if transform.fitted_through_contest > window.training_last_contest
    )
    if leaking_transforms:
        names = ",".join(transform.name for transform in leaking_transforms)
        raise BacktestLeakageError(
            f"TRANSFORM_FIT_LEAKAGE_DETECTED:transforms={names};"
            f"training_last={window.training_last_contest};target={window.target_contest}"
        )


def run_audited_backtest(
    windows: Sequence[BacktestWindow],
    scorer: Callable[[BacktestWindow], float],
    *,
    min_successful_windows: int = 30,
    min_success_rate: float = 0.80,
) -> BacktestAuditReport:
    """Executa janelas predefinidas sem omitir falhas e sem tolerar lookahead.

    Leakage é fatal e bloqueia o experimento antes de qualquer janela ser pontuada.
    Falhas operacionais/numéricas do scorer são registradas como janelas FAILED e
    permanecem no denominador. Baixa cobertura retorna INCONCLUSIVE, nunca promoção.
    """
    if not windows:
        raise ValueError("é necessária ao menos uma janela")
    if min_successful_windows <= 0:
        raise ValueError("min_successful_windows deve ser positivo")
    if not 0.0 < min_success_rate <= 1.0:
        raise ValueError("min_success_rate deve estar em (0, 1]")

    ordered = tuple(windows)
    ids = tuple(window.window_id for window in ordered)
    if len(set(ids)) != len(ids):
        raise ValueError("window_id deve ser único")

    # Fail-closed: toda a proveniência temporal é validada antes da execução.
    for window in ordered:
        validate_backtest_window(window)

    outcomes: list[WindowOutcome] = []
    model_scores: list[float] = []
    deltas: list[float] = []

    for window in ordered:
        try:
            score = float(scorer(window))
            if not 0.0 <= score <= 1.0:
                raise ValueError("model_brier deve estar entre 0 e 1")
            delta = UNIFORM_BRIER - score
            model_scores.append(score)
            deltas.append(delta)
            outcomes.append(
                WindowOutcome(
                    window_id=window.window_id,
                    training_last_contest=window.training_last_contest,
                    target_contest=window.target_contest,
                    state="SUCCESS",
                    m0_brier=UNIFORM_BRIER,
                    model_brier=score,
                    delta_brier=delta,
                    error_type=None,
                    error_message=None,
                )
            )
        except BacktestLeakageError:
            raise
        except Exception as exc:
            outcomes.append(
                WindowOutcome(
                    window_id=window.window_id,
                    training_last_contest=window.training_last_contest,
                    target_contest=window.target_contest,
                    state="FAILED",
                    m0_brier=UNIFORM_BRIER,
                    model_brier=None,
                    delta_brier=None,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                )
            )

    planned = len(outcomes)
    successful = len(model_scores)
    failed = planned - successful
    success_rate = successful / planned
    enough_evidence = successful >= min_successful_windows and success_rate >= min_success_rate

    return BacktestAuditReport(
        status="VALID" if enough_evidence else "INCONCLUSIVE",
        predictive_evidence="NOT_ESTABLISHED",
        planned_windows=planned,
        successful_windows=successful,
        failed_windows=failed,
        success_rate=success_rate,
        min_successful_windows=min_successful_windows,
        min_success_rate=min_success_rate,
        mean_model_brier=fmean(model_scores) if model_scores else None,
        mean_delta_brier=fmean(deltas) if deltas else None,
        outcomes=tuple(outcomes),
    )
