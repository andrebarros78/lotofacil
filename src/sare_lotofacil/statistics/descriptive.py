from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import sqrt
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import intersection_hits, numbers_to_mask, normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES


@dataclass(frozen=True, slots=True)
class MarginalStat:
    number: int
    observed: int
    expected: float
    frequency: float
    difference: float
    z_score: float


@dataclass(frozen=True, slots=True)
class GeometryStat:
    total_sum: int
    odd_count: int
    even_count: int
    adjacent_pairs: int
    amplitude: int


def _validated_draws(draws: Iterable[Iterable[int]]) -> tuple[tuple[int, ...], ...]:
    result = tuple(normalize_numbers(draw) for draw in draws)
    if not result:
        raise ValueError("é necessário pelo menos um concurso")
    return result


def marginal_uniformity(draws: Iterable[Iterable[int]]) -> tuple[MarginalStat, ...]:
    normalized = _validated_draws(draws)
    n = len(normalized)
    counts = [0] * DEFAULT_RULES.universe_size
    for draw in normalized:
        for number in draw:
            counts[number - 1] += 1
    p = DEFAULT_RULES.marginal_probability
    expected = n * p
    std = sqrt(n * p * (1.0 - p))
    return tuple(
        MarginalStat(
            number=index + 1,
            observed=count,
            expected=expected,
            frequency=count / n,
            difference=count - expected,
            z_score=(count - expected) / std if std else 0.0,
        )
        for index, count in enumerate(counts)
    )


def pair_counts(draws: Iterable[Iterable[int]]) -> dict[tuple[int, int], int]:
    normalized = _validated_draws(draws)
    counts = {pair: 0 for pair in combinations(range(1, 26), 2)}
    for draw in normalized:
        for pair in combinations(draw, 2):
            counts[pair] += 1
    return counts


def repetition_counts(draws: Sequence[Iterable[int]]) -> tuple[int, ...]:
    normalized = _validated_draws(draws)
    if len(normalized) < 2:
        return ()
    masks = tuple(numbers_to_mask(draw) for draw in normalized)
    return tuple(intersection_hits(previous, current) for previous, current in zip(masks, masks[1:]))


def geometry(draw: Iterable[int]) -> GeometryStat:
    numbers = normalize_numbers(draw)
    odd_count = sum(number % 2 for number in numbers)
    adjacent_pairs = sum(right - left == 1 for left, right in zip(numbers, numbers[1:]))
    return GeometryStat(
        total_sum=sum(numbers),
        odd_count=odd_count,
        even_count=len(numbers) - odd_count,
        adjacent_pairs=adjacent_pairs,
        amplitude=numbers[-1] - numbers[0],
    )
