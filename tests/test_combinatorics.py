from fractions import Fraction

from sare_lotofacil.domain.combinatorics import (
    draw_sum_mean,
    draw_sum_variance,
    exact_hit_distribution,
    exact_hit_probability,
    expected_hits,
    pair_probability,
    triple_probability,
    variance_hits,
)
from sare_lotofacil.domain.rules import DEFAULT_RULES


def test_combination_space_and_hit_distribution() -> None:
    assert DEFAULT_RULES.combination_space == 3_268_760
    distribution = exact_hit_distribution()
    assert sum(distribution.values()) == 1
    assert exact_hit_probability(15) == Fraction(1, 3_268_760)
    assert exact_hit_probability(14) == Fraction(150, 3_268_760)
    assert exact_hit_probability(13) == Fraction(4_725, 3_268_760)
    assert exact_hit_probability(12) == Fraction(54_600, 3_268_760)
    assert exact_hit_probability(11) == Fraction(286_650, 3_268_760)


def test_exact_moments_and_cooccurrence() -> None:
    assert expected_hits() == 9
    assert variance_hits() == Fraction(3, 2)
    assert pair_probability() == Fraction(7, 20)
    assert triple_probability() == Fraction(91, 460)
    assert draw_sum_mean() == 195
    assert draw_sum_variance() == 325


def test_expanded_bet_costs() -> None:
    expected = {15: 350, 16: 5_600, 17: 47_600, 18: 285_600, 19: 1_356_600, 20: 5_426_400}
    assert {n: DEFAULT_RULES.expanded_bet_cost_cents(n) for n in expected} == expected
