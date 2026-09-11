import pytest

from sare_lotofacil.experiments.models import (
    exponential_update,
    frequency_regularized,
    walk_forward_exponential,
    walk_forward_frequency,
)
from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.baseline import uniform_baseline


def test_reference_models_preserve_probability_contract() -> None:
    draws = simulate_uniform_draws(120, seed=9).draws
    m1 = frequency_regularized(draws, lam=100)
    assert sum(m1) == pytest.approx(15.0)
    m2 = exponential_update(uniform_baseline(), draws[0], alpha=0.05)
    assert sum(m2) == pytest.approx(15.0)


def test_walk_forward_uses_only_past_data() -> None:
    draws = simulate_uniform_draws(160, seed=10).draws
    m1 = walk_forward_frequency(draws, min_train=100, lam=100)
    m2 = walk_forward_exponential(draws, min_train=100, alpha=0.05)
    assert m1.predictions == 60
    assert m2.predictions == 60
    assert 0.0 <= m1.mean_brier <= 1.0
    assert 0.0 <= m2.mean_brier <= 1.0
