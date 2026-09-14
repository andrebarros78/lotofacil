from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import numbers_to_mask, normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES


@dataclass(frozen=True, slots=True)
class JointCoverageResult:
    card_count: int
    min_hits: int
    covered_outcomes: int
    total_outcomes: int
    probability: float
    method: str
    independence_assumption_used: bool
    naive_independence_probability: float


def _iter_fixed_popcount_masks(width: int, popcount: int):
    if not 0 < popcount <= width:
        return
    value = (1 << popcount) - 1
    limit = 1 << width
    while value < limit:
        yield value
        lowbit = value & -value
        ripple = value + lowbit
        value = (((ripple ^ value) >> 2) // lowbit) | ripple


def single_card_tail_probability(min_hits: int) -> float:
    if not 0 <= min_hits <= DEFAULT_RULES.draw_size:
        raise ValueError("min_hits deve estar entre 0 e 15")
    total = math.comb(DEFAULT_RULES.universe_size, DEFAULT_RULES.draw_size)
    favorable = 0
    for hits in range(min_hits, DEFAULT_RULES.draw_size + 1):
        misses = DEFAULT_RULES.draw_size - hits
        if hits <= DEFAULT_RULES.draw_size and misses <= DEFAULT_RULES.universe_size - DEFAULT_RULES.draw_size:
            favorable += math.comb(DEFAULT_RULES.draw_size, hits) * math.comb(
                DEFAULT_RULES.universe_size - DEFAULT_RULES.draw_size,
                misses,
            )
    return favorable / total


def exact_joint_coverage(
    cards: Sequence[Iterable[int]],
    *,
    min_hits: int,
) -> JointCoverageResult:
    """Calcula Q_h(P) por enumeração conjunta dos 3.268.760 resultados.

    Todos os cartões enfrentam o mesmo resultado de 15 dezenas. A rotina nunca
    multiplica probabilidades de cartões como se seus eventos fossem independentes.
    A aproximação de independência é exposta apenas como diagnóstico comparativo.
    """
    normalized = tuple(normalize_numbers(card) for card in cards)
    if not normalized:
        raise ValueError("cards não pode ser vazio")
    if len(set(normalized)) != len(normalized):
        raise ValueError("cards precisam ser distintos")
    if not 0 <= min_hits <= DEFAULT_RULES.draw_size:
        raise ValueError("min_hits deve estar entre 0 e 15")

    card_masks = tuple(numbers_to_mask(card) for card in normalized)
    covered = 0
    total = math.comb(DEFAULT_RULES.universe_size, DEFAULT_RULES.draw_size)
    for draw_mask in _iter_fixed_popcount_masks(DEFAULT_RULES.universe_size, DEFAULT_RULES.draw_size):
        if any((card_mask & draw_mask).bit_count() >= min_hits for card_mask in card_masks):
            covered += 1

    single_probability = single_card_tail_probability(min_hits)
    naive = 1.0 - (1.0 - single_probability) ** len(card_masks)
    return JointCoverageResult(
        card_count=len(card_masks),
        min_hits=min_hits,
        covered_outcomes=covered,
        total_outcomes=total,
        probability=covered / total,
        method="EXACT_JOINT_ENUMERATION_25_CHOOSE_15",
        independence_assumption_used=False,
        naive_independence_probability=naive,
    )
