from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence, TypeVar

T = TypeVar("T")


class TemporalIntegrityViolation(ValueError):
    """Falha fechada quando o contrato temporal permite informação indisponível no treino."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True, slots=True)
class TemporalIntegrityReport:
    status: str
    feature_offsets: tuple[int, ...]
    transform_fit_scope: str
    window_failure_policy: str
    violations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BacktestWindowFailure:
    window_id: str
    reason: str


@dataclass(frozen=True, slots=True)
class BacktestIntegrityReport:
    status: str
    total_windows: int
    successful_windows: int
    failed_windows: int
    min_required_windows: int
    failures: tuple[BacktestWindowFailure, ...]
    advantage_eligible: bool


def inspect_temporal_integrity(
    *,
    feature_offsets: Sequence[int],
    transform_fit_scope: str,
    window_failure_policy: str,
) -> TemporalIntegrityReport:
    offsets = tuple(int(value) for value in feature_offsets)
    violations: list[str] = []
    if not offsets:
        violations.append("FEATURE_OFFSETS_EMPTY")
    if any(offset >= 0 for offset in offsets):
        violations.append("FUTURE_OR_TARGET_FEATURE_OFFSET")
    if transform_fit_scope != "TRAIN_ONLY":
        violations.append("TRANSFORM_FIT_OUTSIDE_TRAIN")
    if window_failure_policy != "COUNT_IN_DENOMINATOR":
        violations.append("WINDOW_FAILURE_POLICY_NOT_AUDITABLE")
    return TemporalIntegrityReport(
        status="PASS" if not violations else "BLOCKED",
        feature_offsets=offsets,
        transform_fit_scope=transform_fit_scope,
        window_failure_policy=window_failure_policy,
        violations=tuple(violations),
    )


def enforce_temporal_integrity(
    *,
    feature_offsets: Sequence[int],
    transform_fit_scope: str,
    window_failure_policy: str,
) -> TemporalIntegrityReport:
    report = inspect_temporal_integrity(
        feature_offsets=feature_offsets,
        transform_fit_scope=transform_fit_scope,
        window_failure_policy=window_failure_policy,
    )
    if report.violations:
        code = report.violations[0]
        raise TemporalIntegrityViolation(code, ",".join(report.violations))
    return report


def audit_backtest_windows(
    window_ids: Sequence[str],
    evaluator: Callable[[str], T],
    *,
    min_required_windows: int,
) -> tuple[tuple[T, ...], BacktestIntegrityReport]:
    """Executa todas as janelas agendadas e nunca omite falha do denominador.

    A função é deliberadamente conservadora: qualquer falha torna o relatório
    inconclusivo, e quantidade insuficiente de janelas também nunca autoriza
    interpretação de vantagem.
    """
    if min_required_windows <= 0:
        raise ValueError("min_required_windows deve ser positivo")
    identifiers = tuple(str(value) for value in window_ids)
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("window_ids precisam ser únicos")

    results: list[T] = []
    failures: list[BacktestWindowFailure] = []
    for window_id in identifiers:
        try:
            results.append(evaluator(window_id))
        except Exception as exc:  # falha vira evidência auditável, não omissão silenciosa
            failures.append(
                BacktestWindowFailure(
                    window_id=window_id,
                    reason=f"{type(exc).__name__}: {exc}",
                )
            )

    total = len(identifiers)
    successful = len(results)
    failed = len(failures)
    if total < min_required_windows:
        status = "INCONCLUSIVE_INSUFFICIENT_WINDOWS"
    elif failed:
        status = "INCONCLUSIVE_WINDOW_FAILURES"
    else:
        status = "PASS"
    report = BacktestIntegrityReport(
        status=status,
        total_windows=total,
        successful_windows=successful,
        failed_windows=failed,
        min_required_windows=min_required_windows,
        failures=tuple(failures),
        advantage_eligible=status == "PASS",
    )
    return tuple(results), report
