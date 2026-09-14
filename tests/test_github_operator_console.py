from __future__ import annotations

import json
from pathlib import Path

from scripts.github_operator_console import _portfolio, _recover_portfolio, _state_summary
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_operator_status_and_portfolio_are_read_only_derivations(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    state.mkdir()
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
            },
        },
    )
    _write(
        state / "prospective_ledger.json",
        {
            "summary": {
                "evaluated_predictions": 0,
                "pending_predictions": 1,
            }
        },
    )

    summary = _state_summary(state)
    assert summary["status"] == "GITHUB_OPERATOR_STATE_PASS"
    assert summary["official_latest_contest"] == 3779
    assert summary["next_prediction_target"] == 3780
    assert summary["predictive_evidence"] == "NOT_ESTABLISHED"
    assert summary["portfolio_ledger_available"] is False

    portfolio = _portfolio(state, card_count=3, seed=0)
    assert portfolio["status"] == "GITHUB_OPERATOR_PORTFOLIO_PASS"
    assert portfolio["target_contest"] == 3780
    assert portfolio["seed"] == 3780
    assert portfolio["card_count"] == 3
    assert len(portfolio["cards"]) == 3
    assert portfolio["evidence_label"] == UNPROVEN_LABEL
    assert portfolio["predictive_evidence"] == "NOT_ESTABLISHED"


def test_operator_recovers_exact_original_portfolio_by_id(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    state.mkdir()
    original = {
        "portfolio_id": "portfolio-abc123",
        "portfolio_sha256": "abc123",
        "target_contest": 3780,
        "seed": 3780,
        "cards": [list(range(1, 16)), list(range(2, 17)), list(range(3, 18))],
        "theoretical_cost_cents": 1050,
        "predictive_evidence": "NOT_ESTABLISHED",
        "evidence_label": UNPROVEN_LABEL,
        "state_snapshot_id": "snap-test",
        "state_snapshot_hash": "snapshot-hash",
        "protocol_hash": "protocol-hash",
        "purchase": {"recorded": False, "actual_cost_cents": None},
        "evaluations": [],
    }
    _write(state / "portfolio_ledger.json", {"schema_version": 1, "portfolios": [original]})

    recovered = _recover_portfolio(state, "portfolio-abc123")
    assert recovered["status"] == "GITHUB_OPERATOR_PORTFOLIO_RECOVERY_PASS"
    assert recovered["portfolio"] == original
    assert recovered["cards_display"][0] == "01 02 03 04 05 06 07 08 09 10 11 12 13 14 15"
