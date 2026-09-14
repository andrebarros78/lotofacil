from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class EconomicAudit:
    hits: tuple[int, ...]
    prize_by_card_cents: tuple[int, ...]
    prize_count_by_tier: tuple[tuple[int, int], ...]
    prize_total_cents: int
    theoretical_cost_cents: int
    hypothetical_net_cents: int
    purchase_recorded: bool = False
    actual_cost_cents: int | None = None
    actual_net_cents: int | None = None


def calculate_economic_audit(
    hits: Iterable[int],
    prize_cents_by_hits: Mapping[int, int],
    *,
    theoretical_cost_cents: int,
) -> EconomicAudit:
    normalized_hits = tuple(int(value) for value in hits)
    if not normalized_hits:
        raise ValueError("hits não pode ser vazio")
    if theoretical_cost_cents <= 0:
        raise ValueError("theoretical_cost_cents deve ser positivo")

    normalized_prizes: dict[int, int] = {}
    for tier, prize in prize_cents_by_hits.items():
        tier = int(tier)
        prize = int(prize)
        if tier not in {11, 12, 13, 14, 15}:
            raise ValueError(f"faixa inválida: {tier}")
        if prize < 0:
            raise ValueError(f"prêmio negativo na faixa {tier}")
        normalized_prizes[tier] = prize

    if set(normalized_prizes) != {11, 12, 13, 14, 15}:
        raise ValueError("rateio precisa conter exatamente as faixas 11 a 15")
    if any(value < 5 or value > 15 for value in normalized_hits):
        raise ValueError("quantidade de acertos fora da faixa 5..15")

    prize_by_card = tuple(normalized_prizes.get(value, 0) if value >= 11 else 0 for value in normalized_hits)
    prize_total = sum(prize_by_card)
    tier_counts = tuple(
        (tier, sum(1 for value in normalized_hits if value == tier))
        for tier in range(15, 10, -1)
    )
    return EconomicAudit(
        hits=normalized_hits,
        prize_by_card_cents=prize_by_card,
        prize_count_by_tier=tier_counts,
        prize_total_cents=prize_total,
        theoretical_cost_cents=theoretical_cost_cents,
        hypothetical_net_cents=prize_total - theoretical_cost_cents,
    )
