from fractions import Fraction

from hypothesis import given, settings, strategies as st

from sare_lotofacil.domain.combinatorics import exact_hit_distribution
from sare_lotofacil.domain.masks import mask_to_numbers, numbers_to_mask
from sare_lotofacil.portfolios.core import generate_uniform_portfolio


valid_draws = st.sets(st.integers(min_value=1, max_value=25), min_size=15, max_size=15).map(tuple)


@given(valid_draws)
def test_mask_round_trip_is_reversible(numbers):
    normalized = tuple(sorted(numbers))
    assert mask_to_numbers(numbers_to_mask(normalized)) == normalized


def test_exact_hit_distribution_is_a_probability_distribution():
    distribution = exact_hit_distribution()
    assert set(distribution) == set(range(5, 16))
    assert all(probability >= 0 for probability in distribution.values())
    assert sum(distribution.values(), Fraction()) == Fraction(1, 1)


@given(
    card_count=st.integers(min_value=3, max_value=30),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
)
@settings(max_examples=40, deadline=None)
def test_generated_portfolio_preserves_card_invariants(card_count, seed):
    portfolio = generate_uniform_portfolio(card_count, seed=seed)
    assert len(portfolio.cards) == card_count
    assert len(set(portfolio.cards)) == card_count
    assert all(len(card) == 15 for card in portfolio.cards)
    assert all(len(set(card)) == 15 for card in portfolio.cards)
    assert all(1 <= number <= 25 for card in portfolio.cards for number in card)
