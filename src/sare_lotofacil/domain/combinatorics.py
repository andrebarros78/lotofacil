from __future__ import annotations

from fractions import Fraction
from math import comb

from .rules import DEFAULT_RULES


def exact_hit_probability(hits: int) -> Fraction:
    """Probabilidade exata de k acertos para cartão fixo de 15 dezenas."""
    if hits < 5 or hits > 15:
        return Fraction(0, 1)
    favorable = comb(15, hits) * comb(10, 15 - hits)
    return Fraction(favorable, DEFAULT_RULES.combination_space)


def exact_hit_distribution() -> dict[int, Fraction]:
    return {hits: exact_hit_probability(hits) for hits in range(5, 16)}


def expected_hits() -> Fraction:
    distribution = exact_hit_distribution()
    return sum((Fraction(hits, 1) * probability for hits, probability in distribution.items()), Fraction())


def variance_hits() -> Fraction:
    mean = expected_hits()
    distribution = exact_hit_distribution()
    return sum((((Fraction(hits, 1) - mean) ** 2) * probability for hits, probability in distribution.items()), Fraction())


def pair_probability() -> Fraction:
    return Fraction(15 * 14, 25 * 24)


def triple_probability() -> Fraction:
    return Fraction(15 * 14 * 13, 25 * 24 * 23)


def draw_sum_mean() -> Fraction:
    return Fraction(15 * 26, 2)


def draw_sum_variance() -> Fraction:
    return Fraction(15 * 10, 24) * Fraction(25**2 - 1, 12)
