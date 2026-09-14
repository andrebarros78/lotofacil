from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


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
    rateio_source_by_tier: tuple[tuple[int, str], ...] = ()
    round_id: str | None = None


@dataclass(frozen=True, slots=True)
class HorizonCashflow:
    horizon_contests: int
    initial_balance_cents: int
    final_balance_cents: int
    net_loss_cents: int
    contests_with_negative_net: int
    net_loss_event: bool
    next_participation_cost_cents: int
    cannot_fund_next_participation: bool


def calculate_economic_audit(
    hits: Iterable[int],
    prize_cents_by_hits: Mapping[int, int],
    *,
    theoretical_cost_cents: int,
    rateio_source_by_hits: Mapping[int, str] | None = None,
    round_id: str | None = None,
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

    normalized_sources: dict[int, str] = {}
    if rateio_source_by_hits is not None:
        for tier, source in rateio_source_by_hits.items():
            tier = int(tier)
            source = str(source).strip()
            if tier not in {11, 12, 13, 14, 15}:
                raise ValueError(f"faixa de fonte inválida: {tier}")
            if not source:
                raise ValueError(f"fonte vazia na faixa {tier}")
            normalized_sources[tier] = source
        if set(normalized_sources) != {11, 12, 13, 14, 15}:
            raise ValueError("fontes de rateio precisam conter exatamente as faixas 11 a 15")

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
        rateio_source_by_tier=tuple((tier, normalized_sources[tier]) for tier in range(15, 10, -1)) if normalized_sources else (),
        round_id=round_id,
    )


def summarize_horizon_cashflow(
    initial_balance_cents: int,
    contest_net_cents: Sequence[int],
    *,
    next_participation_cost_cents: int,
) -> HorizonCashflow:
    if initial_balance_cents < 0:
        raise ValueError("initial_balance_cents não pode ser negativo")
    if not contest_net_cents:
        raise ValueError("contest_net_cents não pode ser vazio")
    if next_participation_cost_cents <= 0:
        raise ValueError("next_participation_cost_cents deve ser positivo")

    normalized = tuple(int(value) for value in contest_net_cents)
    final_balance = initial_balance_cents + sum(normalized)
    net_loss = initial_balance_cents - final_balance
    return HorizonCashflow(
        horizon_contests=len(normalized),
        initial_balance_cents=initial_balance_cents,
        final_balance_cents=final_balance,
        net_loss_cents=net_loss,
        contests_with_negative_net=sum(1 for value in normalized if value < 0),
        net_loss_event=net_loss > 0,
        next_participation_cost_cents=next_participation_cost_cents,
        cannot_fund_next_participation=final_balance < next_participation_cost_cents,
    )
