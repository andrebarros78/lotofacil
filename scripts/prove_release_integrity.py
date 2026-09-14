from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from sare_lotofacil.analysis.regime import assess_marginal_regime
from sare_lotofacil.economics import calculate_economic_audit, summarize_horizon_cashflow
from sare_lotofacil.experiments.backtest import (
    BacktestLeakageError,
    BacktestWindow,
    FittedTransform,
    TemporalVariable,
    run_audited_backtest,
)
from sare_lotofacil.experiments.integrity import (
    OptionalStoppingViolation,
    assess_performance_gap_for_leakage,
)
from sare_lotofacil.experiments.protocol import ExperimentProtocol
from sare_lotofacil.experiments.reproducibility import ScientificRunIdentity
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect
from sare_lotofacil.persistence.operations import evaluate_portfolio_revision, persist_uniform_portfolio
from sare_lotofacil.persistence.repository import persist_caixa_contest
from sare_lotofacil.portfolios.core import generate_uniform_portfolio, normalize_portfolio_cards
from sare_lotofacil.portfolios.coverage import exact_jackpot_coverage, exact_joint_coverage
from sare_lotofacil.portfolios.primary import (
    PRIMARY_MODEL_NAME,
    SECONDARY_MODEL_NAME,
    SELECTION_METHOD,
    build_primary_card,
    select_primary_card,
)
from sare_lotofacil.portfolios.search import PortfolioSearchPolicy, search_bounded_portfolio
from sare_lotofacil.simulation.alternative import simulate_marginal_regime_shift
from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.simulation.risk import summarize_binary_risk
from sare_lotofacil.simulation.validation import assess_temporal_memory_separation, measure_marginal_bias_power

ARTIFACTS = Path("artifacts")


def _write(name: str, payload: dict) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prove_regime() -> None:
    null_assessment = assess_marginal_regime(
        simulate_uniform_draws(500, seed=17).draws,
        min_segment=60,
        candidate_stride=10,
        calibration_replications=99,
        validation_replications=99,
        seed=20260914,
    )
    assert null_assessment.calibration.compatible_with_target is True
    assert null_assessment.state == "STABLE"
    assert null_assessment.calibration.validation_ci95_low <= 0.05 <= null_assessment.calibration.validation_ci95_high

    shifted = simulate_marginal_regime_shift(
        500,
        change_index=250,
        target_number=16,
        post_probability=0.85,
        seed=321,
    )
    labels = tuple(f"contest-{index:04d}" for index in range(1, 501))
    alert = assess_marginal_regime(
        shifted.draws,
        candidate_labels=labels,
        min_segment=60,
        candidate_stride=10,
        calibration_replications=99,
        validation_replications=99,
        seed=20260914,
    )
    assert alert.state == "ALERT"
    assert alert.scan.strongest.candidate_index == 250
    assert alert.scan.strongest.strongest_number == 16
    assert alert.mode == "RETROSPECTIVE_DISCOVERY"
    payload = {
        "status": "REGIME_CALIBRATION_RELEASE_PROOF_PASS",
        "null_state": null_assessment.state,
        "calibration_compatible": null_assessment.calibration.compatible_with_target,
        "controlled_shift_state": alert.state,
        "controlled_shift_candidate_index": alert.scan.strongest.candidate_index,
        "controlled_shift_number": alert.scan.strongest.strongest_number,
        "mode": alert.mode,
    }
    _write("regime_calibration_release_proof.json", payload)
    print(payload["status"])


def prove_controlled_alternatives() -> None:
    t17 = measure_marginal_bias_power(
        replications=30,
        draw_count=400,
        target_number=16,
        target_probability=0.72,
        alpha=0.05,
        base_seed=20260914,
    )
    assert t17.power >= 0.80 and t17.detections >= 24 and t17.mean_target_effect >= 0.08
    t18 = assess_temporal_memory_separation(
        draw_count=600,
        memory_probability=0.30,
        retained_count=12,
        alpha=0.05,
        seed=20260914,
        permutation_replications=399,
    )
    assert t18.marginal_alerts == 0
    assert t18.temporal_alerts >= 1
    assert t18.lag1_effect > 0.50
    assert t18.lag1_p_holm < 0.05
    payload = {"status": "CONTROLLED_ALTERNATIVES_RELEASE_PROOF_PASS", "t17": asdict(t17), "t18": asdict(t18)}
    _write("controlled_alternatives_release_proof.json", payload)
    print(payload["status"])


def prove_backtest() -> None:
    blocked_variable = False
    try:
        run_audited_backtest(
            (BacktestWindow("t20", 199, 200, (TemporalVariable("future_result_200", 200),), ()),),
            lambda _: 0.20,
            min_successful_windows=1,
        )
    except BacktestLeakageError as exc:
        blocked_variable = "LOOKAHEAD_LEAKAGE_DETECTED" in str(exc)
    assert blocked_variable

    blocked_transform = False
    try:
        run_audited_backtest(
            (
                BacktestWindow(
                    "t21",
                    249,
                    250,
                    (TemporalVariable("history_prefix", 249),),
                    (FittedTransform("global_standardizer", 400),),
                ),
            ),
            lambda _: 0.20,
            min_successful_windows=1,
        )
    except BacktestLeakageError as exc:
        blocked_transform = "TRANSFORM_FIT_LEAKAGE_DETECTED" in str(exc)
    assert blocked_transform

    windows = tuple(
        BacktestWindow(
            f"w{i}",
            100 + i,
            101 + i,
            (TemporalVariable("history_prefix", 100 + i),),
            (FittedTransform("fit", 100 + i),),
        )
        for i in range(5)
    )

    def scorer(window):
        if window.window_id == "w2":
            raise ArithmeticError("synthetic-window-failure")
        return 0.20

    t22 = run_audited_backtest(windows, scorer, min_successful_windows=4, min_success_rate=0.80)
    assert t22.planned_windows == 5
    assert t22.successful_windows == 4
    assert t22.failed_windows == 1
    assert t22.success_rate == 0.80
    assert all(outcome.m0_brier == 0.24 for outcome in t22.outcomes)

    short = tuple(
        BacktestWindow(
            f"s{i}",
            200 + i,
            201 + i,
            (TemporalVariable("history_prefix", 200 + i),),
            (FittedTransform("fit", 200 + i),),
        )
        for i in range(3)
    )
    t23 = run_audited_backtest(short, lambda _: 0.10, min_successful_windows=10, min_success_rate=0.80)
    assert t23.status == "INCONCLUSIVE"
    assert t23.predictive_evidence == "NOT_ESTABLISHED"
    payload = {
        "status": "BACKTEST_INTEGRITY_RELEASE_PROOF_PASS",
        "t20_blocked": blocked_variable,
        "t21_blocked": blocked_transform,
        "t22": {
            "planned": t22.planned_windows,
            "success": t22.successful_windows,
            "failed": t22.failed_windows,
            "success_rate": t22.success_rate,
            "ledger_hash": t22.content_hash,
        },
        "t23": {
            "status": t23.status,
            "predictive_evidence": t23.predictive_evidence,
            "planned": t23.planned_windows,
            "success": t23.successful_windows,
        },
    }
    _write("backtest_integrity_release_proof.json", payload)
    print(payload["status"])


def prove_risk_repro_coverage() -> None:
    t24 = summarize_binary_risk(0, 1000, confidence=0.95)
    assert t24.probability == 0.0 and t24.interval_low == 0.0 and t24.interval_high > 0.0
    t25_blocked = False
    try:
        summarize_binary_risk(0, 0)
    except ValueError:
        t25_blocked = True
    assert t25_blocked

    clean_window = BacktestWindow(
        "t26",
        199,
        200,
        (TemporalVariable("history_prefix", 199),),
        (FittedTransform("fit", 199),),
    )
    t26 = assess_performance_gap_for_leakage(clean_window, train_metric=0.24, test_metric=0.20)
    assert t26.test_metric < t26.train_metric and t26.leakage_detected is False

    t27_blocked = False
    try:
        ExperimentProtocol(
            hypothesis_id="t27",
            question="optional?",
            h0="h0",
            h1="h1",
            snapshot_id="snap",
            stopping_rule="inspect_repeatedly_until_p_below_0_05",
        ).validate()
    except OptionalStoppingViolation as exc:
        t27_blocked = exc.code == "OPTIONAL_STOPPING_FORBIDDEN"
    assert t27_blocked

    first = ScientificRunIdentity(
        seed=20260914,
        data_hash="data-sha",
        code_commit="code-sha",
        environment_hash="env-sha",
        protocol_hash="protocol-sha",
        scientific_payload={"metric": {"delta": 0.001, "brier": 0.239}, "run_id": "a", "created_at_utc": "2026-09-14T10:00:00Z"},
    )
    second = ScientificRunIdentity(
        seed=20260914,
        data_hash="data-sha",
        code_commit="code-sha",
        environment_hash="env-sha",
        protocol_hash="protocol-sha",
        scientific_payload={"created_at_utc": "2026-09-14T11:00:00Z", "run_id": "b", "metric": {"brier": 0.239, "delta": 0.001}},
    )
    assert first.normalized_json == second.normalized_json
    assert first.content_hash == second.content_hash

    t29 = exact_joint_coverage((tuple(range(1, 16)), (*tuple(range(1, 15)), 16)), min_hits=14)
    assert t29.total_outcomes == 3_268_760
    assert t29.independence_assumption_used is False
    assert abs(t29.probability - t29.naive_independence_probability) > 1e-8
    payload = {
        "status": "RISK_REPRO_JOINT_COVERAGE_RELEASE_PROOF_PASS",
        "t24": asdict(t24),
        "t25_zero_replications_blocked": t25_blocked,
        "t26": asdict(t26),
        "t27_optional_stopping_blocked": t27_blocked,
        "t28_content_hash": first.content_hash,
        "t29": asdict(t29),
        "interpretation": "T24-T29 prove risk/statistical integrity, reproducibility and joint portfolio coverage; they do not establish predictive advantage.",
    }
    _write("risk_repro_joint_coverage_release_proof.json", payload)
    print(payload["status"])


def prove_portfolio_economics() -> None:
    single = generate_uniform_portfolio(1, seed=1)
    assert len(single.cards) == 1 and single.cost_cents == 350
    t30_blocked = []
    for count in (0, 101):
        try:
            generate_uniform_portfolio(count, seed=1)
        except ValueError:
            t30_blocked.append(count)
    assert t30_blocked == [0, 101]

    card = tuple(range(1, 16))
    duplicate_blocked = False
    try:
        normalize_portfolio_cards((card, card), expected_count=2)
    except ValueError as exc:
        duplicate_blocked = "DUPLICATE_CARD" in str(exc)
    assert duplicate_blocked
    generated = generate_uniform_portfolio(10, seed=20260914)
    assert len(generated.cards) == len(set(generated.cards)) == 10

    strict_policy = PortfolioSearchPolicy(max_overlap=0, max_exposure=1.0, max_attempts=12, seed=7)
    t32 = search_bounded_portfolio(3, policy=strict_policy)
    assert t32.status == "SEARCH_LIMIT_REACHED" and t32.attempts == 12 and not t32.cards
    assert "INFEASIBLE" not in t32.status
    relaxed_policy = PortfolioSearchPolicy(max_overlap=10, max_exposure=1.0, max_attempts=12, seed=7)
    assert strict_policy.config_id != relaxed_policy.config_id

    jackpot = exact_jackpot_coverage(generate_uniform_portfolio(5, seed=34).cards)
    assert jackpot.covered_outcomes == 5 and jackpot.total_outcomes == 3_268_760
    assert jackpot.probability == 5 / 3_268_760

    unpurchased = calculate_economic_audit(
        [11, 10, 9],
        {15: 1_000_000, 14: 50_000, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=1_050,
    )
    assert unpurchased.purchase_recorded is False
    assert unpurchased.actual_cost_cents is None
    assert unpurchased.actual_net_cents is None

    sources = {tier: f"caixa://contest-500/revision-1/tier-{tier}" for tier in (15, 14, 13, 12, 11)}
    t36 = calculate_economic_audit(
        [15, 14],
        {15: 80_000_000, 14: 125_000, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=700,
        rateio_source_by_hits=sources,
        round_id="contest-500/revision-1",
    )
    assert t36.prize_by_card_cents == (80_000_000, 125_000)
    assert dict(t36.rateio_source_by_tier)[15] != dict(t36.rateio_source_by_tier)[14]

    t37 = calculate_economic_audit(
        [14, 14, 15],
        {15: 50_000_000, 14: 98_765, 13: 3_500, 12: 1_400, 11: 700},
        theoretical_cost_cents=1_050,
        round_id="contest-501/revision-1",
    )
    assert t37.prize_by_card_cents[0] == t37.prize_by_card_cents[1] == 98_765

    one = summarize_horizon_cashflow(1_000, [-300], next_participation_cost_cents=300)
    prolonged = summarize_horizon_cashflow(1_000, [-300, -300, -300, -300], next_participation_cost_cents=300)
    assert one.horizon_contests == 1 and prolonged.horizon_contests == 4
    assert one.net_loss_cents == 300 and prolonged.net_loss_cents == 1_200
    assert one.cannot_fund_next_participation is False and prolonged.cannot_fund_next_participation is True

    db = "/tmp/t30-t39-release.db"
    Path(db).unlink(missing_ok=True)
    portfolio = persist_uniform_portfolio(db, card_count=3, seed=39, target_contest=500)
    contest = CaixaContest(
        record=validate_contest(500, date(2026, 9, 14), range(1, 16)),
        prize_tiers=(),
        source_url="fixture://contest/500/revision/1",
        captured_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        raw_payload={"numero": 500, "listaDezenas": list(range(1, 16))},
    )
    persisted = persist_caixa_contest(db, contest, source_class="SINTETICO")
    assert persisted.revision == 1
    first = evaluate_portfolio_revision(db, portfolio.portfolio_id, 500, 1)
    second = evaluate_portfolio_revision(db, portfolio.portfolio_id, 500, 1)
    assert first == second
    with connect(db) as connection:
        revision_rows = connection.execute("SELECT COUNT(*) FROM revision_evaluations").fetchone()[0]
        audit_rows = connection.execute("SELECT COUNT(*) FROM audit_events WHERE action='PORTFOLIO_REVISION_EVALUATED'").fetchone()[0]
        schema_version = int(connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0])
    assert revision_rows == 1 and audit_rows == 1 and schema_version == SCHEMA_VERSION == 6

    payload = {
        "status": "PORTFOLIO_ECONOMIC_INTEGRITY_RELEASE_PROOF_PASS",
        "t30_single_card_allowed": True,
        "t30_blocked_counts": t30_blocked,
        "t31_duplicate_blocked": duplicate_blocked,
        "t31_delivered_count": len(generated.cards),
        "t32": asdict(t32),
        "t33_strict_policy_id": strict_policy.config_id,
        "t33_relaxed_policy_id": relaxed_policy.config_id,
        "t34": asdict(jackpot),
        "t35": {
            "purchase_recorded": unpurchased.purchase_recorded,
            "actual_cost_cents": unpurchased.actual_cost_cents,
            "actual_net_cents": unpurchased.actual_net_cents,
            "theoretical_cost_cents": unpurchased.theoretical_cost_cents,
        },
        "t36": {"prize_by_card_cents": t36.prize_by_card_cents, "rateio_source_by_tier": t36.rateio_source_by_tier, "round_id": t36.round_id},
        "t37_prize_by_card_cents": t37.prize_by_card_cents,
        "t38_one": asdict(one),
        "t38_prolonged": asdict(prolonged),
        "t39": {
            "evaluation_id": first.evaluation_id,
            "contest_id": first.contest_id,
            "revision": first.revision,
            "revision_rows": revision_rows,
            "audit_rows": audit_rows,
            "schema_version": schema_version,
        },
        "interpretation": "T30-T39 prove portfolio constraints and economic/audit integrity; they do not establish predictive advantage.",
    }
    _write("portfolio_economic_integrity_release_proof.json", payload)
    print(payload["status"])


def prove_primary_card() -> None:
    primary = [index / 100.0 for index in range(1, 26)]
    secondary = [0.5] * 25
    first = select_primary_card(primary, secondary, target_contest=101, training_last_contest=100)
    second = select_primary_card(primary, secondary, target_contest=101, training_last_contest=100)
    assert first == second
    assert first.card == tuple(range(11, 26))
    assert len(first.card) == len(set(first.card)) == 15
    assert first.primary_model == PRIMARY_MODEL_NAME
    assert first.secondary_model == SECONDARY_MODEL_NAME
    assert first.selection_method == SELECTION_METHOD
    assert len(first.decision_sha256) == 64

    tied_primary = [0.6] * 25
    rising_secondary = [index / 100.0 for index in range(1, 26)]
    tiebreak = select_primary_card(tied_primary, rising_secondary, target_contest=101, training_last_contest=100)
    assert tiebreak.card == tuple(range(11, 26))

    draws = tuple(tuple(range(1, 16)) for _ in range(120))
    from_history = build_primary_card(draws, target_contest=121, training_last_contest=120)
    assert from_history.card == tuple(range(1, 16))

    non_next_blocked = False
    try:
        select_primary_card(primary, secondary, target_contest=102, training_last_contest=100)
    except ValueError as exc:
        non_next_blocked = "PRIMARY_CARD_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE" in str(exc)
    assert non_next_blocked

    payload = {
        "status": "PRIMARY_CARD_RELEASE_PROOF_PASS",
        "selection_method": first.selection_method,
        "primary_model": first.primary_model,
        "secondary_model": first.secondary_model,
        "card": list(first.card),
        "card_count": 1,
        "number_count": len(first.card),
        "deterministic": first.decision_sha256 == second.decision_sha256,
        "decision_sha256": first.decision_sha256,
        "m2_tiebreak_verified": list(tiebreak.card) == list(range(11, 26)),
        "non_next_target_blocked": non_next_blocked,
        "history_selection_card": list(from_history.card),
        "predictive_evidence": "NOT_ESTABLISHED",
    }
    _write("primary_card_release_proof.json", payload)
    print(payload["status"])


def main() -> int:
    prove_regime()
    prove_controlled_alternatives()
    prove_backtest()
    prove_risk_repro_coverage()
    prove_portfolio_economics()
    prove_primary_card()
    print("RELEASE_INTEGRITY_SUITE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
