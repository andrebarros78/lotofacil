import pytest

from sare_lotofacil.statistics.baseline import (
    UNIFORM_BRIER,
    brier_score,
    delta_brier,
    uniform_baseline,
    validate_probabilities,
)


def test_uniform_baseline_is_exact_reference() -> None:
    probabilities = uniform_baseline()
    assert len(probabilities) == 25
    assert sum(probabilities) == pytest.approx(15.0)
    assert UNIFORM_BRIER == pytest.approx(0.24)
    assert brier_score(probabilities, range(1, 16)) == pytest.approx(0.24)
    assert delta_brier(0.24) == pytest.approx(0.0)


def test_probability_contract() -> None:
    with pytest.raises(ValueError):
        validate_probabilities([0.6] * 24)
    with pytest.raises(ValueError):
        validate_probabilities([0.5] * 25)
