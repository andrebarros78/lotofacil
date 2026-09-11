from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

from sare_lotofacil.domain.masks import intersection_hits, numbers_to_mask, normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES

UNPROVEN_LABEL = "CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA"


@dataclass(frozen=True, slots=True)
class Portfolio:
    seed: int
    cards: tuple[tuple[int, ...], ...]
    cost_cents: int
    evidence_label: str = UNPROVEN_LABEL


def generate_uniform_portfolio(card_count: int, *, seed: int) -> Portfolio:
    if not 3 <= card_count <= 100:
        raise ValueError("card_count deve estar entre 3 e 100")
    rng = random.Random(seed)
    unique: set[tuple[int, ...]] = set()
    while len(unique) < card_count:
        unique.add(tuple(sorted(rng.sample(range(1, 26), 15))))
    cards = tuple(sorted(unique))
    return Portfolio(
        seed=seed,
        cards=cards,
        cost_cents=card_count * DEFAULT_RULES.simple_bet_cost_cents,
    )


def audit_portfolio(portfolio: Portfolio, draw: Iterable[int]) -> tuple[int, ...]:
    result = normalize_numbers(draw)
    draw_mask = numbers_to_mask(result)
    return tuple(intersection_hits(numbers_to_mask(card), draw_mask) for card in portfolio.cards)
