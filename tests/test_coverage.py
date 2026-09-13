from fractions import Fraction

import pytest

from sare_lotofacil.domain.combinatorics import exact_hit_probability
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.coverage import (
    portfolio_fifteen_coverage_exact,
    single_card_threshold_coverage_exact,
)


def test_single_card_threshold_coverage_is_exact_hypergeometric_sum():
    expected = sum((exact_hit_probability(k) for k in range(11, 16)), Fraction())
    assert single_card_threshold_coverage_exact(11) == expected
    assert single_card_threshold_coverage_exact(15) == Fraction(1, DEFAULT_RULES.combination_space)


def test_distinct_portfolio_fifteen_coverage_is_exact_without_independence_assumption():
    cards = [
        tuple(range(1, 16)),
        tuple(range(2, 17)),
        tuple(range(3, 18)),
    ]
    assert portfolio_fifteen_coverage_exact(cards) == Fraction(3, DEFAULT_RULES.combination_space)


def test_exact_fifteen_coverage_rejects_duplicate_cards():
    card = tuple(range(1, 16))
    with pytest.raises(ValueError, match="duplicados"):
        portfolio_fifteen_coverage_exact([card, card])
