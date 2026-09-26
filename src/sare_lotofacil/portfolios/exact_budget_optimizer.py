from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import combinations
from typing import Iterable, Sequence

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.core import normalize_portfolio_cards

EXACT_EVALUATION_METHOD = "EXACT_MEMBERSHIP_PATTERN_DP_25_CHOOSE_15_V1"
EXACT_OPTIMIZER_METHOD = "EXHAUSTIVE_CANDIDATE_SUBSET_LEXICOGRAPHIC_V1"
MAX_EXACT_OPTIMIZER_CARDS = 4
MAX_EXACT_CANDIDATE_POOL = 8
TAIL_THRESHOLDS = (11, 12, 13, 14, 15)


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ExactPortfolioMetrics:
    card_count: int
    total_outcomes: int
    guaranteed_min_best_hits: int
    best_hits_sum: int
    mean_best_hits: float
    best_hits_histogram: tuple[tuple[int, int], ...]
    coverage_counts_ge: tuple[tuple[int, int], ...]
    method: str = EXACT_EVALUATION_METHOD

    def coverage_count(self, min_hits: int) -> int:
        mapping = dict(self.coverage_counts_ge)
        if min_hits not in mapping:
            raise ValueError("min_hits outside exact coverage table")
        return int(mapping[min_hits])

    def coverage_probability(self, min_hits: int) -> float:
        return self.coverage_count(min_hits) / self.total_outcomes

    def objective_vector(self) -> tuple[int, ...]:
        # Q15 is invariant for a fixed number of distinct 15-number cards, but
        # remains in the vector so the optimization contract explicitly covers
        # every prize tier requested by the project.
        return (
            self.guaranteed_min_best_hits,
            self.coverage_count(15),
            self.coverage_count(14),
            self.coverage_count(13),
            self.coverage_count(12),
            self.coverage_count(11),
            self.best_hits_sum,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "card_count": self.card_count,
            "total_outcomes": self.total_outcomes,
            "guaranteed_min_best_hits": self.guaranteed_min_best_hits,
            "best_hits_sum": self.best_hits_sum,
            "mean_best_hits": self.mean_best_hits,
            "best_hits_histogram": {str(hit): count for hit, count in self.best_hits_histogram},
            "coverage": {
                str(hit): {
                    "covered_outcomes": count,
                    "probability": count / self.total_outcomes,
                }
                for hit, count in self.coverage_counts_ge
                if hit in TAIL_THRESHOLDS
            },
            "objective_vector": list(self.objective_vector()),
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class ExactBudgetSelection:
    budget_cents: int
    cost_cents: int
    unused_cents: int
    selected_candidate_indices: tuple[int, ...]
    cards: tuple[tuple[int, ...], ...]
    metrics: ExactPortfolioMetrics
    candidate_subsets_evaluated: int
    candidate_pool_size: int
    optimizer_method: str = EXACT_OPTIMIZER_METHOD

    def to_dict(self) -> dict[str, object]:
        payload = {
            "budget_cents": self.budget_cents,
            "cost_cents": self.cost_cents,
            "unused_cents": self.unused_cents,
            "selected_candidate_indices": list(self.selected_candidate_indices),
            "cards": [list(card) for card in self.cards],
            "metrics": self.metrics.to_dict(),
            "candidate_subsets_evaluated": self.candidate_subsets_evaluated,
            "candidate_pool_size": self.candidate_pool_size,
            "optimizer_method": self.optimizer_method,
            "candidate_pool_optimality_proven": True,
            "global_full_space_optimality_proven": False,
            "global_full_space_size": DEFAULT_RULES.combination_space,
            "optimality_scope": "EXACT_OVER_DECLARED_CANDIDATE_POOL_ONLY",
        }
        payload["selection_sha256"] = _sha256(payload)
        return payload


def _membership_groups(cards: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, int], ...]:
    card_sets = tuple(set(card) for card in cards)
    counts: dict[int, int] = defaultdict(int)
    for number in range(1, DEFAULT_RULES.universe_size + 1):
        pattern = 0
        for index, card in enumerate(card_sets):
            if number in card:
                pattern |= 1 << index
        counts[pattern] += 1
    return tuple(sorted(counts.items()))


def evaluate_portfolio_exact(cards: Sequence[Iterable[int]]) -> ExactPortfolioMetrics:
    """Conta exatamente os 3.268.760 resultados sem hipótese de independência.

    Números com o mesmo padrão de pertencimento aos cartões são agrupados. O
    DP escolhe quantos elementos de cada grupo entram no resultado de 15 dezenas
    e multiplica cada transição pelo coeficiente binomial correspondente. Assim,
    cada combinação possível do universo é contada exatamente uma vez.
    """
    normalized = normalize_portfolio_cards(cards)
    if not normalized:
        raise ValueError("cards não pode ser vazio")
    if len(normalized) > MAX_EXACT_OPTIMIZER_CARDS:
        raise ValueError(
            f"EXACT_EVALUATION_CARD_LIMIT_EXCEEDED limit={MAX_EXACT_OPTIMIZER_CARDS}"
        )

    groups = _membership_groups(normalized)
    card_count = len(normalized)
    zero_hits = (0,) * card_count
    states: dict[tuple[int, tuple[int, ...]], int] = {(0, zero_hits): 1}
    remaining = sum(count for _, count in groups)

    for pattern, group_count in groups:
        remaining -= group_count
        next_states: dict[tuple[int, tuple[int, ...]], int] = defaultdict(int)
        for (selected, hits), ways in states.items():
            min_take = max(0, DEFAULT_RULES.draw_size - selected - remaining)
            max_take = min(group_count, DEFAULT_RULES.draw_size - selected)
            for take in range(min_take, max_take + 1):
                selected_next = selected + take
                if take:
                    hits_next = tuple(
                        hit + (take if pattern & (1 << index) else 0)
                        for index, hit in enumerate(hits)
                    )
                else:
                    hits_next = hits
                next_states[(selected_next, hits_next)] += ways * math.comb(group_count, take)
        states = next_states

    histogram: dict[int, int] = defaultdict(int)
    for (selected, hits), ways in states.items():
        if selected != DEFAULT_RULES.draw_size:
            continue
        histogram[max(hits)] += ways

    total = sum(histogram.values())
    expected_total = DEFAULT_RULES.combination_space
    if total != expected_total:
        raise RuntimeError(
            f"EXACT_DP_OUTCOME_COUNT_MISMATCH observed={total} expected={expected_total}"
        )
    if not histogram:
        raise RuntimeError("EXACT_DP_EMPTY_HISTOGRAM")

    floor = min(hit for hit, count in histogram.items() if count)
    best_hits_sum = sum(hit * count for hit, count in histogram.items())
    coverage_counts = tuple(
        (
            threshold,
            sum(count for hit, count in histogram.items() if hit >= threshold),
        )
        for threshold in range(5, DEFAULT_RULES.draw_size + 1)
    )
    metrics = ExactPortfolioMetrics(
        card_count=card_count,
        total_outcomes=total,
        guaranteed_min_best_hits=floor,
        best_hits_sum=best_hits_sum,
        mean_best_hits=best_hits_sum / total,
        best_hits_histogram=tuple(sorted(histogram.items())),
        coverage_counts_ge=coverage_counts,
    )

    # For distinct simple cards, the 15-hit union consists exactly of the cards.
    if metrics.coverage_count(15) != card_count:
        raise RuntimeError("EXACT_DP_JACKPOT_IDENTITY_MISMATCH")
    return metrics


def optimize_budget_exact(
    candidate_cards: Sequence[Iterable[int]],
    *,
    budget_cents: int,
    mandatory_indices: Sequence[int] = (0,),
) -> ExactBudgetSelection:
    """Prova o ótimo por enumeração de todos os subconjuntos do pool declarado.

    Não declara ótimo global sobre as 3.268.760 combinações possíveis de cartões.
    Esse limite é parte explícita do contrato de saída para evitar falsa prova.
    """
    candidates = normalize_portfolio_cards(candidate_cards)
    if not candidates:
        raise ValueError("candidate_cards não pode ser vazio")
    if len(candidates) > MAX_EXACT_CANDIDATE_POOL:
        raise ValueError(
            f"EXACT_CANDIDATE_POOL_LIMIT_EXCEEDED limit={MAX_EXACT_CANDIDATE_POOL}"
        )
    if budget_cents <= 0:
        raise ValueError("budget_cents deve ser positivo")

    mandatory = tuple(dict.fromkeys(int(index) for index in mandatory_indices))
    if any(index < 0 or index >= len(candidates) for index in mandatory):
        raise ValueError("mandatory index outside candidate pool")

    affordable_cards = budget_cents // DEFAULT_RULES.simple_bet_cost_cents
    if affordable_cards < len(mandatory):
        raise ValueError("budget insufficient for mandatory cards")
    if affordable_cards > MAX_EXACT_OPTIMIZER_CARDS:
        raise ValueError(
            "BUDGET_EXCEEDS_EXACT_OPTIMIZER_CARD_CAP "
            f"affordable={affordable_cards} limit={MAX_EXACT_OPTIMIZER_CARDS}"
        )

    card_count = min(affordable_cards, len(candidates))
    if card_count < 1:
        raise ValueError("budget does not fund one simple card")

    mandatory_set = set(mandatory)
    optional = tuple(index for index in range(len(candidates)) if index not in mandatory_set)
    needed = card_count - len(mandatory)
    if needed < 0 or needed > len(optional):
        raise ValueError("candidate pool cannot satisfy requested exact card count")

    best_indices: tuple[int, ...] | None = None
    best_metrics: ExactPortfolioMetrics | None = None
    best_objective: tuple[int, ...] | None = None
    evaluated = 0

    for extra in combinations(optional, needed):
        indices = tuple(sorted((*mandatory, *extra)))
        portfolio = tuple(candidates[index] for index in indices)
        metrics = evaluate_portfolio_exact(portfolio)
        objective = metrics.objective_vector()
        evaluated += 1
        if best_objective is None or objective > best_objective:
            best_indices = indices
            best_metrics = metrics
            best_objective = objective

    if best_indices is None or best_metrics is None:
        raise RuntimeError("EXACT_BUDGET_OPTIMIZER_NO_FEASIBLE_PORTFOLIO")

    cost = card_count * DEFAULT_RULES.simple_bet_cost_cents
    return ExactBudgetSelection(
        budget_cents=budget_cents,
        cost_cents=cost,
        unused_cents=budget_cents - cost,
        selected_candidate_indices=best_indices,
        cards=tuple(candidates[index] for index in best_indices),
        metrics=best_metrics,
        candidate_subsets_evaluated=evaluated,
        candidate_pool_size=len(candidates),
    )
