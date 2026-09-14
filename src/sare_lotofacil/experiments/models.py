from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import stdev
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.backtest import (
    BacktestAuditReport,
    BacktestWindow,
    FittedTransform,
    TemporalVariable,
    run_audited_backtest,
)
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER, brier_score, delta_brier, uniform_baseline


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    model_name: str
    predictions: int
    mean_brier: float
    uniform_brier: float
    delta_brier: float
    delta_brier_ci_low: float
    delta_brier_ci_high: float
    delta_min: float
    planned_windows: int
    successful_windows: int
    failed_windows: int
    success_rate: float
    backtest_status: str
    window_ledger_hash: str
    failed_window_ids: tuple[str, ...]


def _paired_delta_interval(model_scores: Sequence[float]) -> tuple[float, float, float]:
    if not model_scores:
        raise ValueError("é necessária pelo menos uma previsão")
    improvements = tuple(UNIFORM_BRIER - float(score) for score in model_scores)
    mean_delta = sum(improvements) / len(improvements)
    if len(improvements) == 1:
        return mean_delta, mean_delta, mean_delta
    standard_error = stdev(improvements) / math.sqrt(len(improvements))
    margin = 1.96 * standard_error
    return mean_delta, mean_delta - margin, mean_delta + margin


def _windows(total: int, min_train: int, *, transform_name: str) -> tuple[BacktestWindow, ...]:
    return tuple(
        BacktestWindow(
            window_id=f"contest-{target_index + 1}",
            training_last_contest=target_index,
            target_contest=target_index + 1,
            variables=(TemporalVariable("history_prefix", target_index),),
            transforms=(FittedTransform(transform_name, target_index),),
        )
        for target_index in range(min_train, total)
    )


def _result_from_audit(model_name: str, audit: BacktestAuditReport, *, delta_min: float) -> WalkForwardResult:
    scores = tuple(
        float(outcome.model_brier)
        for outcome in audit.outcomes
        if outcome.state == "SUCCESS" and outcome.model_brier is not None
    )
    if not scores:
        raise RuntimeError("BACKTEST_NO_SUCCESSFUL_WINDOWS")
    mean_score = sum(scores) / len(scores)
    mean_delta, ci_low, ci_high = _paired_delta_interval(scores)
    return WalkForwardResult(
        model_name=model_name,
        predictions=len(scores),
        mean_brier=mean_score,
        uniform_brier=UNIFORM_BRIER,
        delta_brier=mean_delta,
        delta_brier_ci_low=ci_low,
        delta_brier_ci_high=ci_high,
        delta_min=delta_min,
        planned_windows=audit.planned_windows,
        successful_windows=audit.successful_windows,
        failed_windows=audit.failed_windows,
        success_rate=audit.success_rate,
        backtest_status=audit.status,
        window_ledger_hash=audit.content_hash,
        failed_window_ids=tuple(
            outcome.window_id for outcome in audit.outcomes if outcome.state == "FAILED"
        ),
    )


def frequency_regularized(training_draws: Sequence[Iterable[int]], *, lam: float = 100.0) -> tuple[float, ...]:
    if lam < 0:
        raise ValueError("lam deve ser não negativo")
    normalized = tuple(normalize_numbers(draw) for draw in training_draws)
    if not normalized:
        return uniform_baseline()
    counts = [0] * 25
    for draw in normalized:
        for number in draw:
            counts[number - 1] += 1
    n = len(normalized)
    return tuple((count + 0.6 * lam) / (n + lam) for count in counts)


def exponential_update(probabilities: Sequence[float], observed_draw: Iterable[int], *, alpha: float = 0.05) -> tuple[float, ...]:
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha deve estar em (0, 1]")
    if len(probabilities) != 25:
        raise ValueError("são necessárias 25 probabilidades")
    observed = set(normalize_numbers(observed_draw))
    updated = tuple(
        (1.0 - alpha) * float(probability) + alpha * (1.0 if index in observed else 0.0)
        for index, probability in enumerate(probabilities, start=1)
    )
    # Cada concurso possui exatamente 15 dezenas; a atualização convexa preserva soma 15.
    return updated


def walk_forward_frequency(
    draws: Sequence[Iterable[int]], *, min_train: int = 100, lam: float = 100.0, delta_min: float = 0.0
) -> WalkForwardResult:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    if delta_min < 0:
        raise ValueError("delta_min não pode ser negativo")

    windows = _windows(len(normalized), min_train, transform_name="frequency_regularized")

    def scorer(window: BacktestWindow) -> float:
        target_index = window.target_contest - 1
        probabilities = frequency_regularized(normalized[:target_index], lam=lam)
        return brier_score(probabilities, normalized[target_index])

    audit = run_audited_backtest(
        windows,
        scorer,
        min_successful_windows=30,
        min_success_rate=1.0,
    )
    return _result_from_audit(
        f"M1_frequency_regularized_lambda_{lam:g}",
        audit,
        delta_min=delta_min,
    )


def walk_forward_exponential(
    draws: Sequence[Iterable[int]], *, min_train: int = 100, alpha: float = 0.05, delta_min: float = 0.0
) -> WalkForwardResult:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    if delta_min < 0:
        raise ValueError("delta_min não pode ser negativo")

    probabilities = uniform_baseline()
    for draw in normalized[:min_train]:
        probabilities = exponential_update(probabilities, draw, alpha=alpha)

    windows = _windows(len(normalized), min_train, transform_name="exponential_state")

    def scorer(window: BacktestWindow) -> float:
        nonlocal probabilities
        target_index = window.target_contest - 1
        target = normalized[target_index]
        score = brier_score(probabilities, target)
        probabilities = exponential_update(probabilities, target, alpha=alpha)
        return score

    audit = run_audited_backtest(
        windows,
        scorer,
        min_successful_windows=30,
        min_success_rate=1.0,
    )
    return _result_from_audit(
        f"M2_exponential_alpha_{alpha:g}",
        audit,
        delta_min=delta_min,
    )
