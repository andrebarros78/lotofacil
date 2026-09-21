from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import intersection_hits, numbers_to_mask, normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.resource_limits import (
    MAX_CARDS_PER_REQUEST,
    MAX_GENERATION_ATTEMPTS,
    ResourceLimitError,
    require_runtime,
)

UNPROVEN_LABEL = "CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA"


@dataclass(frozen=True, slots=True)
class Portfolio:
    seed: int
    cards: tuple[tuple[int, ...], ...]
    cost_cents: int
    evidence_label: str = UNPROVEN_LABEL


def normalize_portfolio_cards(
    cards: Sequence[Iterable[int]],
    *,
    expected_count: int | None = None,
) -> tuple[tuple[int, ...], ...]:
    normalized = tuple(normalize_numbers(card) for card in cards)
    if expected_count is not None and len(normalized) != expected_count:
        raise ValueError("DELIVERED_CARD_COUNT_MISMATCH")
    if len(set(normalized)) != len(normalized):
        raise ValueError("DUPLICATE_CARD")
    return normalized


def generate_uniform_portfolio(card_count: int, *, seed: int) -> Portfolio:
    if not 1 <= card_count <= MAX_CARDS_PER_REQUEST:
        raise ValueError(
            f"card_count deve estar entre 1 e {MAX_CARDS_PER_REQUEST}"
        )
    rng = random.Random(seed)
    unique: set[tuple[int, ...]] = set()
    attempts = 0
    started = time.monotonic()
    while len(unique) < card_count:
        if attempts >= MAX_GENERATION_ATTEMPTS:
            raise ResourceLimitError(
                "GENERATION_ATTEMPTS_LIMIT_EXCEEDED "
                f"attempts={attempts} limit={MAX_GENERATION_ATTEMPTS}"
            )
        require_runtime(started)
        attempts += 1
        unique.add(tuple(sorted(rng.sample(range(1, 26), 15))))
    require_runtime(started)
    cards = normalize_portfolio_cards(tuple(sorted(unique)), expected_count=card_count)
    return Portfolio(
        seed=seed,
        cards=cards,
        cost_cents=card_count * DEFAULT_RULES.simple_bet_cost_cents,
    )


def audit_portfolio(portfolio: Portfolio, draw: Iterable[int]) -> tuple[int, ...]:
    result = normalize_numbers(draw)
    draw_mask = numbers_to_mask(result)
    return tuple(intersection_hits(numbers_to_mask(card), draw_mask) for card in portfolio.cards)
