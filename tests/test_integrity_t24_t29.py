from __future__ import annotations

import pytest

from sare_lotofacil.experiments.backtest import BacktestWindow, FittedTransform, TemporalVariable
from sare_lotofacil.experiments.integrity import (
    OptionalStoppingViolation,
    assess_performance_gap_for_leakage,
)
from sare_lotofacil.experiments.protocol import ExperimentProtocol
from sare_lotofacil.experiments.reproducibility import ScientificRunIdentity
from sare_lotofacil.portfolios.coverage import exact_joint_coverage
from sare_lotofacil.simulation.risk import summarize_binary_risk


def test_t24_zero_ruin_events_keep_positive_upper_risk_bound() -> None:
    estimate = summarize_binary_risk(0, 1000, confidence=0.95)

    assert estimate.probability == 0.0
    assert estimate.interval_low == 0.0
    assert estimate.interval_high > 0.0
    assert estimate.monte_carlo_resolution == pytest.approx(0.001)
    assert estimate.interval_method == "WILSON_SCORE"


def test_t25_zero_replications_is_input_error_not_zero_risk() -> None:
    with pytest.raises(ValueError, match="replications deve ser inteiro positivo"):
        summarize_binary_risk(0, 0)


def test_t26_test_better_than_train_is_not_leakage_by_itself() -> None:
    window = BacktestWindow(
        window_id="t26-clean-window",
        training_last_contest=199,
        target_contest=200,
        variables=(TemporalVariable("history_prefix", 199),),
        transforms=(FittedTransform("train_fitted", 199),),
    )
    assessment = assess_performance_gap_for_leakage(
        window,
        train_metric=0.24,
        test_metric=0.20,
    )

    assert assessment.test_metric < assessment.train_metric
    assert assessment.leakage_detected is False
    assert assessment.status == "NO_LEAKAGE_EVIDENCE_FROM_PERFORMANCE_GAP"
    assert assessment.basis == "TEMPORAL_PROVENANCE_ONLY"


def test_t27_repeated_pvalue_optional_stopping_is_blocked_by_protocol() -> None:
    protocol = ExperimentProtocol(
        hypothesis_id="t27",
        question="Parar quando p ficar favorável é permitido?",
        h0="Sem efeito",
        h1="Com efeito",
        snapshot_id="snap-t27",
        stopping_rule="inspect_repeatedly_until_p_below_0_05",
    )

    with pytest.raises(OptionalStoppingViolation) as exc_info:
        _ = protocol.protocol_hash

    assert exc_info.value.code == "OPTIONAL_STOPPING_FORBIDDEN"


def test_t28_fixed_seed_data_code_environment_normalize_to_same_content() -> None:
    first = ScientificRunIdentity(
        seed=20260914,
        data_hash="data-sha",
        code_commit="code-sha",
        environment_hash="env-sha",
        protocol_hash="protocol-sha",
        scientific_payload={
            "metric": {"delta": 0.001, "brier": 0.239},
            "run_id": "run-a",
            "created_at_utc": "2026-09-14T10:00:00Z",
        },
    )
    second = ScientificRunIdentity(
        seed=20260914,
        data_hash="data-sha",
        code_commit="code-sha",
        environment_hash="env-sha",
        protocol_hash="protocol-sha",
        scientific_payload={
            "created_at_utc": "2026-09-14T11:00:00Z",
            "run_id": "run-b",
            "metric": {"brier": 0.239, "delta": 0.001},
        },
    )

    assert first.normalized_json == second.normalized_json
    assert first.content_hash == second.content_hash
    changed_seed = ScientificRunIdentity(
        seed=20260915,
        data_hash="data-sha",
        code_commit="code-sha",
        environment_hash="env-sha",
        protocol_hash="protocol-sha",
        scientific_payload=second.scientific_payload,
    )
    assert changed_seed.content_hash != first.content_hash


def test_t29_correlated_fixed_cards_use_exact_joint_coverage_not_independence() -> None:
    cards = (
        tuple(range(1, 16)),
        (*tuple(range(1, 15)), 16),
    )
    coverage = exact_joint_coverage(cards, min_hits=14)

    assert coverage.total_outcomes == 3_268_760
    assert coverage.covered_outcomes > 0
    assert 0.0 < coverage.probability < 1.0
    assert coverage.method == "EXACT_JOINT_ENUMERATION_25_CHOOSE_15"
    assert coverage.independence_assumption_used is False
    assert abs(coverage.probability - coverage.naive_independence_probability) > 1e-8
