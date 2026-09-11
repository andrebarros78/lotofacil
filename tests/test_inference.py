import pytest

from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.inference import (
    binomial_two_sided_pvalue,
    fixed_split_frequency_shift,
    marginal_tests,
    pair_tests,
    temporal_repetition_monte_carlo,
)


def test_binomial_pvalue_contract() -> None:
    assert binomial_two_sided_pvalue(6, 10, 0.6) == pytest.approx(1.0)
    assert 0.0 < binomial_two_sided_pvalue(10, 10, 0.6) < 0.05


def test_marginal_and_pair_families_have_holm_adjustment() -> None:
    draws = simulate_uniform_draws(250, seed=44).draws
    marginal = marginal_tests(draws)
    pairs = pair_tests(draws)
    assert len(marginal) == 25
    assert len(pairs) == 300
    assert all(item.p_holm >= item.p_value for item in marginal)
    assert all(item.p_holm >= item.p_value for item in pairs)


def test_temporal_monte_carlo_never_returns_zero_pvalue() -> None:
    draws = simulate_uniform_draws(100, seed=45).draws
    result = temporal_repetition_monte_carlo(draws, replications=99, seed=46)
    assert result.p_value >= 0.01
    assert result.null_expected == 9.0


def test_fixed_split_detects_large_controlled_shift() -> None:
    rng_draws = list(simulate_uniform_draws(400, seed=47).draws)
    first = []
    second = []
    for draw in rng_draws[:200]:
        values = set(draw)
        if 1 not in values:
            values.remove(max(values))
            values.add(1)
        first.append(tuple(sorted(values)))
    for draw in rng_draws[200:]:
        values = set(draw)
        if 1 in values:
            values.remove(1)
            replacement = next(number for number in range(25, 1, -1) if number not in values)
            values.add(replacement)
        second.append(tuple(sorted(values)))
    tests = fixed_split_frequency_shift(tuple(first + second), split_index=200)
    number_one = tests[0]
    assert number_one.effect < -0.9
    assert number_one.p_holm < 0.001
