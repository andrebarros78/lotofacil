from __future__ import annotations

from sare_lotofacil.analysis.nested_walk_forward import run_nested_walk_forward
from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_nested_walk_forward_is_temporal_and_lockbox_isolated() -> None:
    draws = simulate_uniform_draws(800, seed=2026091530).draws
    report = run_nested_walk_forward(
        draws,
        outer_folds=4,
        inner_folds=3,
    )

    assert report["status"] == "PASS"
    assert report["protocol"] == "NESTED_WALK_FORWARD_TEMPORAL_WITH_FINAL_LOCKBOX_V1"
    assert report["history_draw_count"] == 800
    assert report["leakage_safe"] is True
    assert report["automatic_model_promotion"] is False
    assert report["predictive_evidence"] == "NOT_ESTABLISHED"
    assert report["retrospective_predictive_evidence"] in {"ESTABLISHED", "NOT_ESTABLISHED"}

    development_end = report["development"]["stop"]
    assert development_end == 680

    outer = report["outer_walk_forward"]
    assert outer["fold_count"] == 4
    assert outer["test_windows_non_overlapping"] is True
    assert len(outer["folds"]) == 4

    previous_stop = None
    for fold in outer["folds"]:
        assert fold["candidate_count"] == 10
        assert fold["leakage_safe"] is True
        assert fold["available_history_end"] == fold["test_start"]
        assert fold["test_start"] < fold["test_stop"] <= development_end
        if previous_stop is not None:
            assert fold["test_start"] == previous_stop
        previous_stop = fold["test_stop"]
        for block in fold["inner_validation_blocks"]:
            assert block["start"] < block["stop"] <= fold["test_start"]
        metrics = fold["test_error_metrics"]
        assert metrics["observations"] == metrics["windows"] * 25
        assert 0.0 <= metrics["brier"] <= 1.0
        assert 0.0 <= metrics["mae"] <= 1.0
        assert 0.0 <= metrics["rmse"] <= 1.0
        assert metrics["log_loss"] >= 0.0
        assert 0.0 <= metrics["calibration_ece_10"] <= 1.0

    outer_ci = outer["aggregate"]["delta_brier_ci_95"]
    assert outer_ci["method"] == "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95"
    assert outer_ci["replications"] == 2000

    final_selection = report["final_inner_selection"]
    assert final_selection["available_history_end"] == development_end
    assert final_selection["candidate_count"] == 10
    assert final_selection["inner_fold_count"] == 5

    lockbox = report["final_lockbox"]
    assert lockbox["start"] == development_end
    assert lockbox["stop"] == 800
    assert lockbox["windows"] == 120
    assert lockbox["used_for_model_selection"] is False
    assert lockbox["selection_frozen_before_evaluation"] is True
    assert lockbox["selection_fingerprint_sha256"] == final_selection["pre_lockbox_selection_fingerprint_sha256"]
    assert lockbox["error_metrics"]["observations"] == 120 * 25
    assert lockbox["delta_brier_ci_95"]["method"] == "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95"


def test_changing_only_lockbox_cannot_change_selection_or_outer_results() -> None:
    draws = simulate_uniform_draws(800, seed=2026091531).draws
    replacement_lockbox = simulate_uniform_draws(120, seed=2026091532).draws
    altered = tuple(draws[:680]) + tuple(replacement_lockbox)

    original_report = run_nested_walk_forward(
        draws,
        outer_folds=4,
        inner_folds=3,
    )
    altered_report = run_nested_walk_forward(
        altered,
        outer_folds=4,
        inner_folds=3,
    )

    assert original_report["development"] == altered_report["development"]
    assert original_report["outer_walk_forward"] == altered_report["outer_walk_forward"]
    assert original_report["final_inner_selection"] == altered_report["final_inner_selection"]
    assert (
        original_report["final_lockbox"]["selection_fingerprint_sha256"]
        == altered_report["final_lockbox"]["selection_fingerprint_sha256"]
    )
    assert (
        original_report["final_lockbox"]["error_metrics"]["brier"]
        != altered_report["final_lockbox"]["error_metrics"]["brier"]
    )
