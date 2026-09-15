from __future__ import annotations

from sare_lotofacil.analysis.capacity_audit import (
    M1_LAMBDA_GRID,
    M2_ALPHA_GRID,
    run_parameter_training_audit,
    run_real_training_audit,
    run_synthetic_capacity_audit,
)
from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_synthetic_capacity_audit_passes_all_fail_closed_gates() -> None:
    report = run_synthetic_capacity_audit()
    assert report["status"] == "PASS"
    assert report["failed_gates"] == ()
    assert all(report["gates"].values())
    assert report["fault_injection"]["failed_windows"] == 8
    assert report["fault_injection"]["status"] == "INCONCLUSIVE"
    assert report["lookahead_blocked"] is True
    assert report["reproducibility"] is True


def test_real_training_audit_never_promotes_predictive_evidence() -> None:
    draws = simulate_uniform_draws(170, seed=2026091520).draws
    report = run_real_training_audit(draws, min_train=130)
    assert report["evaluation_windows"] == 40
    assert report["m0_brier"] == 0.24
    assert report["m1"]["backtest_status"] == "VALID"
    assert report["m2"]["backtest_status"] == "VALID"
    assert report["predictive_evidence"] == "NOT_ESTABLISHED"
    assert report["scientific_conclusion"] == "EVIDENCIA_PREDITIVA_INSUFICIENTE"


def test_parameter_training_uses_predeclared_validation_grid_and_separate_holdout() -> None:
    draws = simulate_uniform_draws(360, seed=2026091521).draws
    report = run_parameter_training_audit(draws)
    assert report["train_end"] == 216
    assert report["validation_end"] == 288
    assert report["holdout_windows"] == 72
    assert report["candidate_count"] == len(M1_LAMBDA_GRID) + len(M2_ALPHA_GRID)
    assert report["selected_on_validation"]["family"] in {"M1", "M2"}
    assert report["selected_holdout"]["planned_windows"] == 72
    assert report["predictive_evidence"] == "NOT_ESTABLISHED"
