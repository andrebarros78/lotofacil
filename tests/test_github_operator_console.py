from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from scripts.github_operator_console import _analyze, _portfolio, _primary_card, _ris, _state_summary
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL
from sare_lotofacil.portfolios.primary import PRIMARY_MODEL_NAME, SECONDARY_MODEL_NAME
from sare_lotofacil.simulation.null import simulate_uniform_draws


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _state_fixture(tmp_path: Path) -> Path:
    state = tmp_path / "operations"
    state.mkdir()
    draws = simulate_uniform_draws(105, seed=20260911).draws
    start = date(2026, 1, 1)
    _write(
        state / "canonical_history.json",
        {
            "records": [
                {
                    "contest_id": index,
                    "draw_date": (start + timedelta(days=index - 1)).isoformat(),
                    "numbers": list(numbers),
                }
                for index, numbers in enumerate(draws, start=1)
            ]
        },
    )
    _write(
        state / "latest.json",
        {
            "official_latest_contest": 3779,
            "next_prediction_target": 3780,
            "snapshot_id": "snap-test",
            "snapshot_hash": "snapshot-hash",
            "database_integrity": "ok",
            "canonical_history_sha256": "history-hash",
            "prospective": {
                "predictive_evidence": "NOT_ESTABLISHED",
                "prospective_state": "UNDER_TEST_COHORT_A",
                "evaluated_predictions": 0,
                "pending_predictions": 1,
            },
        },
    )
    _write(
        state / "prospective_ledger.json",
        {
            "summary": {
                "evaluated_predictions": 0,
                "pending_predictions": 1,
            },
            "predictions": [
                {
                    "target_contest": 3780,
                    "training_last_contest": 3779,
                    "models": {
                        PRIMARY_MODEL_NAME: [index / 100.0 for index in range(1, 26)],
                        SECONDARY_MODEL_NAME: [0.5] * 25,
                    },
                }
            ],
        },
    )
    return state


def test_operator_status_primary_card_and_portfolio_are_read_only_derivations(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)

    summary = _state_summary(state)
    assert summary["status"] == "GITHUB_OPERATOR_STATE_PASS"
    assert summary["official_latest_contest"] == 3779
    assert summary["next_prediction_target"] == 3780
    assert summary["predictive_evidence"] == "NOT_ESTABLISHED"

    primary = _primary_card(state)
    assert primary["status"] == "GITHUB_OPERATOR_PRIMARY_CARD_PASS"
    assert primary["target_contest"] == 3780
    assert primary["card_count"] == 1
    assert primary["card"] == list(range(11, 26))
    assert primary["decision_source"] == "DERIVED_FROM_FROZEN_LEGACY_MODEL_SCORES"
    assert primary["predictive_evidence"] == "NOT_ESTABLISHED"

    portfolio = _portfolio(state, card_count=1, seed=0)
    assert portfolio["status"] == "GITHUB_OPERATOR_PORTFOLIO_PASS"
    assert portfolio["target_contest"] == 3780
    assert portfolio["seed"] == 3780
    assert portfolio["card_count"] == 1
    assert len(portfolio["cards"]) == 1
    assert portfolio["evidence_label"] == UNPROVEN_LABEL
    assert portfolio["predictive_evidence"] == "NOT_ESTABLISHED"


def test_operator_ris_uses_canonical_state_without_numeric_score(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    ris = _ris(state)

    assert ris["status"] == "GITHUB_OPERATOR_RIS_PASS"
    assert ris["numeric_ris_enabled"] is False
    assert ris["score"] is None
    assert ris["snapshot_id"] == "snap-test"
    assert ris["dimensions"]["data_integrity"]["state"] == "VERIFIED"
    assert ris["dimensions"]["predictive_evidence"]["state"] == "UNDER_TEST"
    assert ris["dimensions"]["predictive_evidence"]["evidence"]["predictive_evidence"] == "NOT_ESTABLISHED"
    assert ris["dimensions"]["regime"]["state"] == "INCONCLUSIVE"
    assert "RIS_NUMERIC_FORBIDDEN_IN_1_X" in ris["guardrails"]


def test_operator_analyze_exposes_latest_constructive_post_contest_report(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    ledger_path = state / "prospective_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    prediction = ledger["predictions"][0]
    prediction["primary_card"] = {"card": list(range(11, 26))}
    prediction["evaluation"] = {
        "observed_contest": 3780,
        "observed_numbers": list(range(1, 16)),
        "delta_brier": {PRIMARY_MODEL_NAME: -0.001},
    }
    prediction["primary_card_evaluation"] = {"observed_contest": 3780, "hits": 5}
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")

    analysis = _analyze(state)
    report = analysis["latest_post_contest_report"]

    assert analysis["status"] == "GITHUB_OPERATOR_ANALYSIS_PASS"
    assert report["contest_number"] == 3780
    assert report["result_display"] == "01 02 03 04 05 06 07 08 09 10 11 12 13 14 15"
    assert report["generated_card_display"] == "11 12 13 14 15 16 17 18 19 20 21 22 23 24 25"
    assert report["hits"] == 5
    assert report["self_analysis"]["adjustments_suggested"]
    assert report["self_analysis"]["implementations_suggested"]
