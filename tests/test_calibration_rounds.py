from __future__ import annotations

from sare_lotofacil.analysis.calibration_rounds import run_calibration_error_rounds
from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_20_round_calibration_and_error_metrics_are_complete() -> None:
    draws = simulate_uniform_draws(650, seed=2026091520).draws
    report = run_calibration_error_rounds(draws, rounds=20)

    assert report["status"] == "PASS"
    assert report["round_count"] == 20
    assert report["history_draw_count"] == 650
    assert report["predictive_evidence"] == "NOT_ESTABLISHED"
    assert report["rounds_are_independent"] is False

    rounds = report["rounds"]
    assert len(rounds) == 20
    assert rounds[-1]["prefix_draws"] == 650
    assert len({item["prefix_draws"] for item in rounds}) == 20

    for item in rounds:
        assert item["train_end"] < item["calibration_end"] < item["prefix_draws"]
        assert item["candidate_count"] == 10
        assert item["leakage_safe"] is True
        metrics = item["holdout_error_metrics"]
        assert metrics["windows"] >= 30
        assert metrics["observations"] == metrics["windows"] * 25
        assert 0.0 <= metrics["brier"] <= 1.0
        assert 0.0 <= metrics["mae"] <= 1.0
        assert 0.0 <= metrics["rmse"] <= 1.0
        assert 0.0 <= metrics["calibration_ece_10"] <= 1.0

    summary = report["summary"]
    assert summary["positive_delta_rounds"] + summary["non_positive_delta_rounds"] == 20
    assert sum(summary["selected_model_counts"].values()) == 20
