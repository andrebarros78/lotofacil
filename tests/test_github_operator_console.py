from __future__ import annotations

import json
from pathlib import Path

from scripts.github_operator_console import _portfolio, _state_summary
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

    portfolio = _portfolio(state, card_count=3, seed=0)
    assert portfolio["status"] == "GITHUB_OPERATOR_PORTFOLIO_PASS"
    assert portfolio["target_contest"] == 3780
    assert portfolio["seed"] == 3780
    assert portfolio["card_count"] == 3
    assert len(portfolio["cards"]) == 3
    assert portfolio["evidence_label"] == UNPROVEN_LABEL
    assert portfolio["predictive_evidence"] == "NOT_ESTABLISHED"
