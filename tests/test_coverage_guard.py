from __future__ import annotations

import pytest

from sare_lotofacil.portfolios.coverage_guard import (
    GUARANTEED_MIN_BEST_HITS,
    build_two_card_coverage_guard,
)


def _hits(card: tuple[int, ...], draw: tuple[int, ...]) -> int:
    return len(set(card).intersection(draw))


def test_guard_preserves_lead_and_builds_overlap_five_union_twenty_five() -> None:
    lead = tuple(range(1, 16))
    probabilities = tuple(number / 25 for number in range(1, 26))

    decision = build_two_card_coverage_guard(
        lead,
        target_contest=3790,
        probabilities=probabilities,
    )

    assert decision.lead_card == lead
    assert decision.retained_core == (11, 12, 13, 14, 15)
    assert decision.guard_card == tuple(range(11, 26))
    assert decision.overlap == 5
    assert decision.union_size == 25
    assert decision.guaranteed_min_best_hits == GUARANTEED_MIN_BEST_HITS == 8


def test_floor_eight_is_attainable_so_the_bound_is_not_overstated() -> None:
    decision = build_two_card_coverage_guard(
        range(1, 16),
        target_contest=3790,
    )
    # Core padrão = 01..05. Este resultado evita o core e divide as 15
    # dezenas entre as duas alas exclusivas em 8 + 7, atingindo o piso.
    draw = tuple((*range(6, 14), *range(16, 23)))

    best = max(_hits(card, draw) for card in decision.cards)

    assert best == 8


def test_guard_rejects_invalid_probability_vector() -> None:
    with pytest.raises(ValueError, match="25 values"):
        build_two_card_coverage_guard(
            range(1, 16),
            target_contest=3790,
            probabilities=(0.6,) * 24,
        )


def test_guard_rejects_invalid_lead_card() -> None:
    with pytest.raises(ValueError, match="esperadas 15 dezenas"):
        build_two_card_coverage_guard(
            range(1, 15),
            target_contest=3790,
        )
