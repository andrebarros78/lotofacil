from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER, brier_score, delta_brier, uniform_baseline


@dataclass(frozen=True, slots=True)
class WalkForwardResult:
    model_name: str
    predictions: int
    mean_brier: float
    uniform_brier: float
    delta_brier: float


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
    updated = tuple((1.0 - alpha) * float(probability) + alpha * (1.0 if index in observed else 0.0) for index, probability in enumerate(probabilities, start=1))
    return updated


def walk_forward_frequency(draws: Sequence[Iterable[int]], *, min_train: int = 100, lam: float = 100.0) -> WalkForwardResult:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    scores = []
    for target_index in range(min_train, len(normalized)):
        probabilities = frequency_regularized(normalized[:target_index], lam=lam)
        scores.append(brier_score(probabilities, normalized[target_index]))
    mean_score = sum(scores) / len(scores)
    return WalkForwardResult(
        model_name=f"M1_frequency_regularized_lambda_{lam:g}",
        predictions=len(scores),
        mean_brier=mean_score,
        uniform_brier=UNIFORM_BRIER,
        delta_brier=delta_brier(mean_score),
    )


def walk_forward_exponential(draws: Sequence[Iterable[int]], *, min_train: int = 100, alpha: float = 0.05) -> WalkForwardResult:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    probabilities = uniform_baseline()
    for draw in normalized[:min_train]:
        probabilities = exponential_update(probabilities, draw, alpha=alpha)
    scores = []
    for target_index in range(min_train, len(normalized)):
        target = normalized[target_index]
        scores.append(brier_score(probabilities, target))
        probabilities = exponential_update(probabilities, target, alpha=alpha)
    mean_score = sum(scores) / len(scores)
    return WalkForwardResult(
        model_name=f"M2_exponential_alpha_{alpha:g}",
        predictions=len(scores),
        mean_brier=mean_score,
        uniform_brier=UNIFORM_BRIER,
        delta_brier=delta_brier(mean_score),
    )
