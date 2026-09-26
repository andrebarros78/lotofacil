from __future__ import annotations

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.global_certified_optimizer import (
    EXPECTED_FOUR_CARD_COVERAGE13_CLASS,
    EXPECTED_FOUR_CARD_FEASIBLE_HISTOGRAMS,
    EXPECTED_FOUR_CARD_FLOOR10_HISTOGRAMS,
    EXPECTED_FOUR_CARD_FLOOR9_HISTOGRAMS,
    EXPECTED_FOUR_CARD_HISTOGRAM,
    certify_four_card_native_selection,
    certify_small_global_selection,
    evaluate_histogram_exact,
    membership_histogram,
    realize_histogram,
)

ANCHOR = (3, 4, 5, 7, 8, 11, 12, 15, 16, 17, 18, 19, 23, 24, 25)


def _native_certificate() -> dict[str, object]:
    return {
        "status": "GLOBAL_ORBIT_SEARCH_PROVEN",
        "feasible_membership_histograms": EXPECTED_FOUR_CARD_FEASIBLE_HISTOGRAMS,
        "floor_ge_9_histograms": EXPECTED_FOUR_CARD_FLOOR9_HISTOGRAMS,
        "floor_ge_10_histograms": EXPECTED_FOUR_CARD_FLOOR10_HISTOGRAMS,
        "coverage13_optimal_class_histograms": EXPECTED_FOUR_CARD_COVERAGE13_CLASS,
        "best_membership_histogram": list(EXPECTED_FOUR_CARD_HISTOGRAM),
        "best_metrics": {
            "objective_vector": [9, 4, 604, 19504, 237504, 1310584, 33982067],
        },
    }


def test_four_card_global_histogram_realizes_anchor_and_exact_floor_nine() -> None:
    cards = realize_histogram(EXPECTED_FOUR_CARD_HISTOGRAM, anchor_card=ANCHOR)
    metrics = evaluate_histogram_exact(EXPECTED_FOUR_CARD_HISTOGRAM)

    assert cards[0] == ANCHOR
    assert membership_histogram(cards) == EXPECTED_FOUR_CARD_HISTOGRAM
    assert metrics.guaranteed_min_best_hits == 9
    assert metrics.coverage_count(9) == DEFAULT_RULES.combination_space
    assert metrics.coverage_count(15) == 4
    assert metrics.coverage_count(14) == 604
    assert metrics.coverage_count(13) == 19504
    assert metrics.coverage_count(12) == 237504
    assert metrics.coverage_count(11) == 1310584
    assert metrics.best_hits_sum == 33982067


def test_native_four_card_certificate_is_recomputed_not_trusted_blindly() -> None:
    selection = certify_four_card_native_selection(
        _native_certificate(),
        anchor_card=ANCHOR,
    )

    assert selection.card_count == 4
    assert selection.cards[0] == ANCHOR
    assert selection.metrics.objective_vector() == (
        9,
        4,
        604,
        19504,
        237504,
        1310584,
        33982067,
    )
    assert selection.to_dict()["global_full_space_optimality_proven"] is True


def test_small_global_frontier_is_exhaustively_certified() -> None:
    expected = {
        1: (5, 1, 151, 4876, 59476, 346126, 29418840),
        2: (8, 2, 302, 9752, 118952, 692252, 32299560),
        3: (9, 3, 453, 14628, 178428, 1028578, 33370690),
    }

    for card_count, objective in expected.items():
        selection = certify_small_global_selection(card_count, anchor_card=ANCHOR)
        assert selection.metrics.objective_vector() == objective
        assert selection.cards[0] == ANCHOR
        assert selection.to_dict()["global_full_space_optimality_proven"] is True
