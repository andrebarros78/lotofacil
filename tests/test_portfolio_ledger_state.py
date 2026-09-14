import json

import pytest

from scripts.register_github_portfolio import register_portfolio
from scripts.verify_portfolio_ledger import verify


def _state(tmp_path):
    state = tmp_path / "operations"
    state.mkdir()
    (state / "latest.json").write_text(
        json.dumps({
            "next_prediction_target": 3780,
            "snapshot_id": "snap-abc",
            "snapshot_hash": "abc123",
            "prospective": {"predictive_evidence": "NOT_ESTABLISHED"},
        }),
        encoding="utf-8",
    )
    (state / "prospective_ledger.json").write_text(
        json.dumps({"protocol": {"protocol_hash": "protocol-123"}}),
        encoding="utf-8",
    )
    return state


def test_register_portfolio_is_idempotent_and_recoverable(tmp_path):
    state = _state(tmp_path)
    first = register_portfolio(
        state,
        card_count=10,
        seed=0,
        target_contest=0,
        source_code_sha="code-sha",
        operations_state_parent_sha="state-sha",
    )
    second = register_portfolio(
        state,
        card_count=10,
        seed=0,
        target_contest=0,
        source_code_sha="code-sha",
        operations_state_parent_sha="state-sha",
    )
    ledger = json.loads((state / "portfolio_ledger.json").read_text(encoding="utf-8"))
    assert first["created"] is True
    assert second["created"] is False
    assert first["portfolio_id"] == second["portfolio_id"]
    assert len(ledger["portfolios"]) == 1
    entry = ledger["portfolios"][0]
    assert entry["portfolio_id"] == first["portfolio_id"]
    assert entry["target_contest"] == 3780
    assert entry["purchase"]["recorded"] is False
    assert entry["purchase"]["actual_cost_cents"] is None
    assert verify(state)["status"] == "GITHUB_PORTFOLIO_LEDGER_AUDIT_PASS"


def test_register_portfolio_refuses_retroactive_or_future_skip(tmp_path):
    state = _state(tmp_path)
    with pytest.raises(ValueError, match="próximo concurso congelado"):
        register_portfolio(
            state,
            card_count=10,
            seed=1,
            target_contest=3779,
            source_code_sha="code-sha",
            operations_state_parent_sha="state-sha",
        )
    with pytest.raises(ValueError, match="próximo concurso congelado"):
        register_portfolio(
            state,
            card_count=10,
            seed=1,
            target_contest=3781,
            source_code_sha="code-sha",
            operations_state_parent_sha="state-sha",
        )
