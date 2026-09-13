from __future__ import annotations

from fractions import Fraction
from typing import Iterable, Sequence

from sare_lotofacil.domain.combinatorics import exact_hit_probability
from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES


def single_card_threshold_coverage_exact(min_hits: int) -> Fraction:
    """Exact H0 probability that one fixed 15-number card reaches ``min_hits``.

    This is deliberately exact: for a single card the complete probability is a
    cheap hypergeometric sum, so Monte Carlo would only add sampling error.
    """
    if not 5 <= min_hits <= 15:
        raise ValueError("min_hits deve estar entre 5 e 15")
    return sum(
        (exact_hit_probability(hits) for hits in range(min_hits, 16)),
        Fraction(),
    )


def portfolio_fifteen_coverage_exact(cards: Sequence[Iterable[int]]) -> Fraction:
    """Exact H0 probability of at least one 15-hit result for distinct cards.

    Each distinct simple card corresponds to exactly one outcome in the complete
    Lotofácil outcome space. Therefore Q_15(P)=|P|/C(25,15), with no independence
    approximation between cards.
    """
    normalized = tuple(normalize_numbers(card) for card in cards)
    if not normalized:
        raise ValueError("portfolio deve possuir ao menos um cartão")
    if len(set(normalized)) != len(normalized):
        raise ValueError("cartões duplicados não são permitidos")
    return Fraction(len(normalized), DEFAULT_RULES.combination_space)
