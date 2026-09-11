from __future__ import annotations

from collections.abc import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES

UNIFORM_PROBABILITY = DEFAULT_RULES.marginal_probability
UNIFORM_BRIER = UNIFORM_PROBABILITY * (1.0 - UNIFORM_PROBABILITY)


def validate_probabilities(probabilities: Sequence[float], *, atol: float = 1e-9) -> tuple[float, ...]:
    values = tuple(float(value) for value in probabilities)
    if len(values) != DEFAULT_RULES.universe_size:
        raise ValueError("são necessárias 25 probabilidades marginais")
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("probabilidades devem estar entre 0 e 1")
    if abs(sum(values) - DEFAULT_RULES.draw_size) > atol:
        raise ValueError("probabilidades marginais devem somar 15")
    return values


def brier_score(probabilities: Sequence[float], drawn_numbers: Iterable[int]) -> float:
    values = validate_probabilities(probabilities)
    draw = set(normalize_numbers(drawn_numbers))
    squared_errors = [
        (probability - (1.0 if index in draw else 0.0)) ** 2
        for index, probability in enumerate(values, start=1)
    ]
    return sum(squared_errors) / DEFAULT_RULES.universe_size


def uniform_baseline() -> tuple[float, ...]:
    return (UNIFORM_PROBABILITY,) * DEFAULT_RULES.universe_size


def delta_brier(model_brier: float) -> float:
    """Positivo significa melhoria sobre o baseline uniforme."""
    return UNIFORM_BRIER - float(model_brier)
