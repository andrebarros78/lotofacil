import pytest

from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.descriptive import geometry, marginal_uniformity, pair_counts, repetition_counts
from sare_lotofacil.statistics.multiplicity import holm_adjust


def test_descriptive_engines_on_valid_draws() -> None:
    draws = simulate_uniform_draws(200, seed=42).draws
    marginal = marginal_uniformity(draws)
    assert len(marginal) == 25
    assert sum(item.observed for item in marginal) == 200 * 15
    assert len(pair_counts(draws)) == 300
    repetitions = repetition_counts(draws)
    assert len(repetitions) == 199
    assert all(5 <= value <= 15 for value in repetitions)
    g = geometry(draws[0])
    assert g.odd_count + g.even_count == 15


def test_holm_adjustment_is_monotone_in_sorted_order() -> None:
    raw = (0.01, 0.04, 0.03)
    adjusted = holm_adjust(raw)
    assert adjusted == pytest.approx((0.03, 0.06, 0.06))
