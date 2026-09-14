from __future__ import annotations

import pytest

from sare_lotofacil.analysis.regime import assess_marginal_regime
from sare_lotofacil.simulation.alternative import simulate_marginal_regime_shift
from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.regime import scan_marginal_regime_change


def test_regime_scan_registers_every_predefined_candidate_label() -> None:
    draws = simulate_uniform_draws(240, seed=11).draws
    labels = tuple(f"contest-{index:04d}" for index in range(1, 241))
    scan = scan_marginal_regime_change(
        draws,
        candidate_labels=labels,
        min_segment=60,
        candidate_stride=20,
    )

    expected_indices = tuple(range(60, 240 - 60 + 1, 20))
    assert tuple(item.candidate_index for item in scan.candidates) == expected_indices
    assert tuple(item.candidate_label for item in scan.candidates) == tuple(labels[index] for index in expected_indices)
    assert scan.strongest in scan.candidates
    assert scan.statistic == scan.strongest.max_abs_z


def test_t16_null_false_alarm_is_independently_calibrated_with_binomial_uncertainty() -> None:
    draws = simulate_uniform_draws(500, seed=17).draws
    assessment = assess_marginal_regime(
        draws,
        min_segment=60,
        candidate_stride=10,
        calibration_replications=99,
        validation_replications=99,
        seed=20260914,
    )

    calibration = assessment.calibration
    assert calibration.compatible_with_target is True
    assert calibration.validation_ci95_low <= calibration.target_alpha <= calibration.validation_ci95_high
    assert 0.0 <= calibration.validation_false_alarm_rate <= 1.0
    assert assessment.state == "STABLE"
    assert assessment.mode == "RETROSPECTIVE_DISCOVERY"
    assert assessment.monte_carlo_p_value > calibration.target_alpha


def test_t19_known_regime_shift_is_detected_and_location_is_registered() -> None:
    simulation = simulate_marginal_regime_shift(
        500,
        change_index=250,
        target_number=16,
        post_probability=0.85,
        seed=321,
    )
    labels = tuple(f"contest-{index:04d}" for index in range(1, 501))
    assessment = assess_marginal_regime(
        simulation.draws,
        candidate_labels=labels,
        min_segment=60,
        candidate_stride=10,
        calibration_replications=99,
        validation_replications=99,
        seed=20260914,
    )

    assert assessment.calibration.compatible_with_target is True
    assert assessment.state == "ALERT"
    assert assessment.monte_carlo_p_value <= 0.05
    assert assessment.scan.strongest.candidate_index == 250
    assert assessment.scan.strongest.candidate_label == labels[250]
    assert assessment.scan.strongest.strongest_number == 16
    assert assessment.scan.strongest.effect > 0.20


def test_regime_requires_two_minimum_segments() -> None:
    draws = simulate_uniform_draws(150, seed=7).draws
    with pytest.raises(ValueError, match="amostra insuficiente"):
        scan_marginal_regime_change(draws, min_segment=100)


def test_controlled_alternative_validates_inputs() -> None:
    with pytest.raises(ValueError):
        simulate_marginal_regime_shift(100, change_index=0, seed=1)
    with pytest.raises(ValueError):
        simulate_marginal_regime_shift(100, change_index=50, target_number=26, seed=1)
    with pytest.raises(ValueError):
        simulate_marginal_regime_shift(100, change_index=50, post_probability=1.1, seed=1)
