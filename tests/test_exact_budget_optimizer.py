from __future__ import annotations

import math

import pytest

from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.coverage_guard import build_two_card_coverage_guard
from sare_lotofacil.portfolios.exact_budget_optimizer import (
    MAX_EXACT_OPTIMIZER_CARDS,
    evaluate_portfolio_exact,
    optimize_budget_exact,
)


def test_single_card_exact_histogram_matches_closed_form() -> None:
    card = tuple(range(1, 16))
    metrics = evaluate_portfolio_exact((card,))

    expected = {
        hits: math.comb(15, hits) * math.comb(10, 15 - hits)
        for hits in range(5, 16)
    }

    assert dict(metrics.best_hits_histogram) == expected
    assert metrics.total_outcomes == DEFAULT_RULES.combination_space == 3_268_760
    assert metrics.guaranteed_min_best_hits == 5
    assert metrics.coverage_count(15) == 1


def test_two_card_guard_has_exact_floor_eight() -> None:
    decision = build_two_card_coverage_guard(
        range(1, 16),
        target_contest=3790,
    )

    metrics = evaluate_portfolio_exact(decision.cards)

    assert metrics.guaranteed_min_best_hits == 8
    assert metrics.coverage_count(8) == DEFAULT_RULES.combination_space
    assert metrics.coverage_count(15) == 2


def test_budget_optimizer_selects_guard_when_it_is_only_floor_eight_partner() -> None:
    lead = tuple(range(1, 16))
    guard = build_two_card_coverage_guard(
        lead,
        target_contest=3790,
    ).guard_card
    overlapping = tuple(range(6, 21))

    selection = optimize_budget_exact(
        (lead, guard, overlapping),
        budget_cents=2 * DEFAULT_RULES.simple_bet_cost_cents,
        mandatory_indices=(0,),
    )

    assert selection.selected_candidate_indices == (0, 1)
    assert selection.cards == (lead, guard)
    assert selection.metrics.guaranteed_min_best_hits == 8
    assert selection.candidate_subsets_evaluated == 2


def test_budget_optimizer_proves_every_declared_subset_at_fixed_card_count() -> None:
    candidates = (
        tuple(range(1, 16)),
        tuple(range(11, 26)),
        tuple((*range(1, 6), *range(16, 26))),
        tuple((*range(6, 11), *range(16, 26))),
    )

    selection = optimize_budget_exact(
        candidates,
        budget_cents=3 * DEFAULT_RULES.simple_bet_cost_cents,
        mandatory_indices=(0,),
    )

    # With card 0 mandatory, choose exactly two of the remaining three.
    assert selection.candidate_subsets_evaluated == 3
    assert selection.cost_cents == 3 * DEFAULT_RULES.simple_bet_cost_cents
    assert selection.unused_cents == 0
    assert selection.metrics.coverage_count(15) == 3
    assert selection.to_dict()["candidate_pool_optimality_proven"] is True
    assert selection.to_dict()["global_full_space_optimality_proven"] is False


def test_budget_above_exact_scope_is_rejected_instead_of_silently_capped() -> None:
    candidates = (
        tuple(range(1, 16)),
        tuple(range(11, 26)),
        tuple((*range(1, 6), *range(16, 26))),
        tuple((*range(6, 11), *range(16, 26))),
        tuple((*range(1, 10), *range(20, 26))),
    )

    with pytest.raises(ValueError, match="BUDGET_EXCEEDS_EXACT_OPTIMIZER_CARD_CAP"):
        optimize_budget_exact(
            candidates,
            budget_cents=(MAX_EXACT_OPTIMIZER_CARDS + 1) * DEFAULT_RULES.simple_bet_cost_cents,
            mandatory_indices=(0,),
        )
