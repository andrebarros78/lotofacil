from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Iterator, Sequence

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.core import normalize_portfolio_cards
from sare_lotofacil.portfolios.exact_budget_optimizer import ExactPortfolioMetrics, evaluate_portfolio_exact

GLOBAL_OPTIMIZER_METHOD = "SYMMETRY_QUOTIENT_EXHAUSTIVE_ORBIT_CERTIFICATION_V1"
GLOBAL_NATIVE_METHOD = "EXHAUSTIVE_MEMBERSHIP_HISTOGRAM_CERTIFICATE_4_CARD_V1"
GLOBAL_MAX_CARDS = 4
EXPECTED_FOUR_CARD_FEASIBLE_HISTOGRAMS = 1_977_452
EXPECTED_FOUR_CARD_FLOOR9_HISTOGRAMS = 54_520
EXPECTED_FOUR_CARD_FLOOR10_HISTOGRAMS = 0
EXPECTED_FOUR_CARD_COVERAGE13_CLASS = 14_856
EXPECTED_FOUR_CARD_HISTOGRAM = (0, 0, 0, 1, 0, 2, 3, 4, 0, 2, 3, 4, 4, 2, 0, 0)


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _card_count_from_histogram(histogram: Sequence[int]) -> int:
    size = len(histogram)
    if size < 2 or size & (size - 1):
        raise ValueError("histogram length must be a power of two")
    card_count = int(math.log2(size))
    if card_count < 1 or card_count > GLOBAL_MAX_CARDS:
        raise ValueError("histogram card count outside global optimizer scope")
    return card_count


def validate_membership_histogram(histogram: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(int(value) for value in histogram)
    card_count = _card_count_from_histogram(normalized)
    if any(value < 0 for value in normalized):
        raise ValueError("histogram counts must be non-negative")
    if sum(normalized) != DEFAULT_RULES.universe_size:
        raise ValueError("histogram must contain exactly the 25 universe elements")
    for card_index in range(card_count):
        membership = sum(
            count
            for pattern, count in enumerate(normalized)
            if pattern & (1 << card_index)
        )
        if membership != DEFAULT_RULES.simple_card_size:
            raise ValueError(
                f"histogram card margin mismatch card={card_index} observed={membership}"
            )
    return normalized


def realize_histogram(
    histogram: Sequence[int],
    *,
    anchor_card: Iterable[int],
) -> tuple[tuple[int, ...], ...]:
    """Realiza um histograma de incidência ancorando o primeiro cartão.

    A função objetivo combinatória é invariante a permutações das 25 dezenas.
    Portanto, fixar o primeiro cartão em qualquer cartão simples de 15 dezenas é
    sem perda de generalidade. Os padrões com bit 0 são preenchidos pela
    complementar do cartão âncora; os padrões com bit 0 = 1, pelo próprio cartão.
    """
    normalized_histogram = validate_membership_histogram(histogram)
    card_count = _card_count_from_histogram(normalized_histogram)
    anchor = normalize_portfolio_cards((anchor_card,))[0]
    anchor_set = set(anchor)
    complement = tuple(
        number
        for number in range(1, DEFAULT_RULES.universe_size + 1)
        if number not in anchor_set
    )

    anchor_iter = iter(anchor)
    complement_iter = iter(complement)
    assignments: dict[int, tuple[int, ...]] = {}
    for pattern, count in enumerate(normalized_histogram):
        source = anchor_iter if pattern & 1 else complement_iter
        assignments[pattern] = tuple(next(source) for _ in range(count))

    cards = tuple(
        tuple(
            sorted(
                number
                for pattern, numbers in assignments.items()
                if pattern & (1 << card_index)
                for number in numbers
            )
        )
        for card_index in range(card_count)
    )
    normalized_cards = normalize_portfolio_cards(cards)
    if normalized_cards[0] != anchor:
        raise RuntimeError("GLOBAL_HISTOGRAM_ANCHOR_REALIZATION_MISMATCH")
    if membership_histogram(normalized_cards) != normalized_histogram:
        raise RuntimeError("GLOBAL_HISTOGRAM_REALIZATION_MISMATCH")
    return normalized_cards


def membership_histogram(cards: Sequence[Iterable[int]]) -> tuple[int, ...]:
    normalized = normalize_portfolio_cards(cards)
    card_count = len(normalized)
    if card_count < 1 or card_count > GLOBAL_MAX_CARDS:
        raise ValueError("cards outside global optimizer scope")
    card_sets = tuple(set(card) for card in normalized)
    histogram = [0] * (1 << card_count)
    for number in range(1, DEFAULT_RULES.universe_size + 1):
        pattern = 0
        for card_index, card in enumerate(card_sets):
            if number in card:
                pattern |= 1 << card_index
        histogram[pattern] += 1
    return tuple(histogram)


def evaluate_histogram_exact(histogram: Sequence[int]) -> ExactPortfolioMetrics:
    """Avalia exatamente o histograma sem depender dos rótulos das dezenas."""
    normalized = validate_membership_histogram(histogram)
    card_count = _card_count_from_histogram(normalized)
    states: dict[tuple[int, tuple[int, ...]], int] = {(0, (0,) * card_count): 1}
    remaining = DEFAULT_RULES.universe_size

    for pattern, group_count in enumerate(normalized):
        if group_count == 0:
            continue
        remaining -= group_count
        next_states: dict[tuple[int, tuple[int, ...]], int] = defaultdict(int)
        for (selected, hits), ways in states.items():
            min_take = max(0, DEFAULT_RULES.draw_size - selected - remaining)
            max_take = min(group_count, DEFAULT_RULES.draw_size - selected)
            for take in range(min_take, max_take + 1):
                hits_next = tuple(
                    hit + (take if pattern & (1 << index) else 0)
                    for index, hit in enumerate(hits)
                )
                next_states[(selected + take, hits_next)] += ways * math.comb(group_count, take)
        states = next_states

    best_hits_histogram: dict[int, int] = defaultdict(int)
    for (selected, hits), ways in states.items():
        if selected == DEFAULT_RULES.draw_size:
            best_hits_histogram[max(hits)] += ways
    total = sum(best_hits_histogram.values())
    if total != DEFAULT_RULES.combination_space:
        raise RuntimeError(
            f"GLOBAL_HISTOGRAM_OUTCOME_COUNT_MISMATCH observed={total} "
            f"expected={DEFAULT_RULES.combination_space}"
        )
    floor = min(hit for hit, count in best_hits_histogram.items() if count)
    best_hits_sum = sum(hit * count for hit, count in best_hits_histogram.items())
    coverage_counts = tuple(
        (
            threshold,
            sum(count for hit, count in best_hits_histogram.items() if hit >= threshold),
        )
        for threshold in range(5, DEFAULT_RULES.draw_size + 1)
    )
    return ExactPortfolioMetrics(
        card_count=card_count,
        total_outcomes=total,
        guaranteed_min_best_hits=floor,
        best_hits_sum=best_hits_sum,
        mean_best_hits=best_hits_sum / total,
        best_hits_histogram=tuple(sorted(best_hits_histogram.items())),
        coverage_counts_ge=coverage_counts,
    )


def _columns_are_distinct(histogram: Sequence[int], card_count: int) -> bool:
    for left in range(card_count):
        for right in range(left + 1, card_count):
            overlap = sum(
                count
                for pattern, count in enumerate(histogram)
                if pattern & (1 << left) and pattern & (1 << right)
            )
            if overlap == DEFAULT_RULES.simple_card_size:
                return False
    return True


def enumerate_feasible_histograms(card_count: int) -> Iterator[tuple[int, ...]]:
    if card_count < 1 or card_count > 3:
        raise ValueError("direct Python exhaustive histogram enumeration is limited to 1..3 cards")
    pattern_count = 1 << card_count
    histogram = [0] * pattern_count

    def visit(pattern: int, total: int, margins: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
        if pattern == pattern_count:
            if total == DEFAULT_RULES.universe_size and all(
                margin == DEFAULT_RULES.simple_card_size for margin in margins
            ):
                yield tuple(histogram)
            return

        max_count = DEFAULT_RULES.universe_size - total
        for card_index in range(card_count):
            if pattern & (1 << card_index):
                max_count = min(
                    max_count,
                    DEFAULT_RULES.simple_card_size - margins[card_index],
                )
        for count in range(max_count + 1):
            next_margins = tuple(
                margin + (count if pattern & (1 << card_index) else 0)
                for card_index, margin in enumerate(margins)
            )
            remaining_total = DEFAULT_RULES.universe_size - total - count
            if any(
                margin > DEFAULT_RULES.simple_card_size
                or DEFAULT_RULES.simple_card_size - margin > remaining_total
                for margin in next_margins
            ):
                continue
            histogram[pattern] = count
            yield from visit(pattern + 1, total + count, next_margins)
        histogram[pattern] = 0

    yield from visit(0, 0, (0,) * card_count)


@dataclass(frozen=True, slots=True)
class GlobalSelection:
    card_count: int
    histogram: tuple[int, ...]
    cards: tuple[tuple[int, ...], ...]
    metrics: ExactPortfolioMetrics
    orbit_histograms_evaluated: int
    proof_method: str

    def to_dict(self) -> dict[str, object]:
        cost = self.card_count * DEFAULT_RULES.simple_bet_cost_cents
        payload: dict[str, object] = {
            "card_count": self.card_count,
            "budget_cents": cost,
            "cost_cents": cost,
            "unused_cents": 0,
            "cards": [list(card) for card in self.cards],
            "membership_histogram": list(self.histogram),
            "metrics": self.metrics.to_dict(),
            "orbit_histograms_evaluated": self.orbit_histograms_evaluated,
            "optimizer_method": GLOBAL_OPTIMIZER_METHOD,
            "proof_method": self.proof_method,
            "global_full_space_optimality_proven": True,
            "optimality_scope": "GLOBAL_ALL_DISTINCT_SIMPLE_CARD_PORTFOLIOS_AT_FIXED_CARD_COUNT",
        }
        payload["selection_sha256"] = _sha256(payload)
        return payload


def certify_small_global_selection(
    card_count: int,
    *,
    anchor_card: Iterable[int],
) -> GlobalSelection:
    if card_count < 1 or card_count > 3:
        raise ValueError("small global certification only supports 1..3 cards")
    best_histogram: tuple[int, ...] | None = None
    best_metrics: ExactPortfolioMetrics | None = None
    evaluated = 0
    for histogram in enumerate_feasible_histograms(card_count):
        if not _columns_are_distinct(histogram, card_count):
            continue
        metrics = evaluate_histogram_exact(histogram)
        evaluated += 1
        if best_metrics is None or metrics.objective_vector() > best_metrics.objective_vector():
            best_histogram = histogram
            best_metrics = metrics
    if best_histogram is None or best_metrics is None:
        raise RuntimeError("GLOBAL_SMALL_OPTIMIZER_NO_FEASIBLE_PORTFOLIO")
    cards = realize_histogram(best_histogram, anchor_card=anchor_card)
    realized_metrics = evaluate_portfolio_exact(cards)
    if realized_metrics.objective_vector() != best_metrics.objective_vector():
        raise RuntimeError("GLOBAL_SMALL_REALIZATION_METRICS_MISMATCH")
    return GlobalSelection(
        card_count=card_count,
        histogram=best_histogram,
        cards=cards,
        metrics=best_metrics,
        orbit_histograms_evaluated=evaluated,
        proof_method="EXHAUSTIVE_ALL_FEASIBLE_MEMBERSHIP_HISTOGRAMS",
    )


def certify_four_card_native_selection(
    certificate: dict[str, object],
    *,
    anchor_card: Iterable[int],
) -> GlobalSelection:
    if certificate.get("status") != "GLOBAL_ORBIT_SEARCH_PROVEN":
        raise RuntimeError("GLOBAL_NATIVE_CERTIFICATE_STATUS_INVALID")
    expected_scalars = {
        "feasible_membership_histograms": EXPECTED_FOUR_CARD_FEASIBLE_HISTOGRAMS,
        "floor_ge_9_histograms": EXPECTED_FOUR_CARD_FLOOR9_HISTOGRAMS,
        "floor_ge_10_histograms": EXPECTED_FOUR_CARD_FLOOR10_HISTOGRAMS,
        "coverage13_optimal_class_histograms": EXPECTED_FOUR_CARD_COVERAGE13_CLASS,
    }
    for key, expected in expected_scalars.items():
        if int(certificate.get(key, -1)) != expected:
            raise RuntimeError(
                f"GLOBAL_NATIVE_CERTIFICATE_COUNT_MISMATCH key={key} "
                f"observed={certificate.get(key)} expected={expected}"
            )
    raw_histogram = certificate.get("best_membership_histogram")
    if not isinstance(raw_histogram, list):
        raise RuntimeError("GLOBAL_NATIVE_CERTIFICATE_HISTOGRAM_MISSING")
    histogram = validate_membership_histogram(raw_histogram)
    if histogram != EXPECTED_FOUR_CARD_HISTOGRAM:
        raise RuntimeError("GLOBAL_NATIVE_CERTIFICATE_HISTOGRAM_UNEXPECTED")

    cards = realize_histogram(histogram, anchor_card=anchor_card)
    metrics = evaluate_portfolio_exact(cards)
    expected_metrics = certificate.get("best_metrics")
    if not isinstance(expected_metrics, dict):
        raise RuntimeError("GLOBAL_NATIVE_CERTIFICATE_METRICS_MISSING")
    expected_objective = tuple(int(value) for value in expected_metrics["objective_vector"])
    if metrics.objective_vector() != expected_objective:
        raise RuntimeError(
            "GLOBAL_NATIVE_CERTIFICATE_METRICS_MISMATCH "
            f"observed={metrics.objective_vector()} expected={expected_objective}"
        )
    if metrics.guaranteed_min_best_hits != 9:
        raise RuntimeError("GLOBAL_NATIVE_FLOOR_NINE_NOT_REALIZED")
    return GlobalSelection(
        card_count=4,
        histogram=histogram,
        cards=cards,
        metrics=metrics,
        orbit_histograms_evaluated=EXPECTED_FOUR_CARD_FEASIBLE_HISTOGRAMS,
        proof_method=GLOBAL_NATIVE_METHOD,
    )
