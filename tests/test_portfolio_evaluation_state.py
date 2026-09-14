import json

from scripts.register_github_portfolio import register_portfolio
from scripts.update_portfolio_evaluations import update_evaluations
from scripts.verify_portfolio_ledger import verify


def _write(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def _state(tmp_path):
    state = tmp_path / "operations"
    state.mkdir()
    _write(
        state / "latest.json",
        {
            "next_prediction_target": 10,
            "snapshot_id": "snap-9",
            "snapshot_hash": "snapshot-9",
            "prospective": {"predictive_evidence": "NOT_ESTABLISHED"},
        },
    )
    _write(state / "prospective_ledger.json", {"protocol": {"protocol_hash": "protocol-1"}})
    register_portfolio(
        state,
        card_count=10,
        seed=10,
        target_contest=10,
        source_code_sha="code-sha",
        operations_state_parent_sha="state-sha",
    )
    _write(
        state / "canonical_history.json",
        {
            "records": [
                {"contest_id": 10, "draw_date": "2026-09-14", "numbers": list(range(1, 16))}
            ]
        },
    )
    _write(
        state / "canonical_prizes.json",
        {
            "contests": [
                {
                    "contest_id": 10,
                    "revisions": [
                        {
                            "revision": 1,
                            "economic_signature_sha256": "sig-1",
                            "prize_tiers": [
                                {"hits": 15, "prize_cents": 1_000_000},
                                {"hits": 14, "prize_cents": 100_000},
                                {"hits": 13, "prize_cents": 10_000},
                                {"hits": 12, "prize_cents": 2_000},
                                {"hits": 11, "prize_cents": 1_000},
                            ],
                        }
                    ],
                }
            ]
        },
    )
    return state


def test_post_contest_evaluation_is_idempotent_and_auditable(tmp_path):
    state = _state(tmp_path)
    first = update_evaluations(state)
    second = update_evaluations(state)
    ledger = json.loads((state / "portfolio_ledger.json").read_text(encoding="utf-8"))
    entry = ledger["portfolios"][0]
    assert first["evaluated"] == [entry["portfolio_id"]]
    assert second["evaluated"] == []
    assert len(entry["evaluations"]) == 1
    evaluation = entry["evaluations"][0]
    assert evaluation["purchase_recorded"] is False
    assert evaluation["actual_cost_cents"] is None
    assert evaluation["actual_net_cents"] is None
    assert verify(state)["status"] == "GITHUB_PORTFOLIO_LEDGER_AUDIT_PASS"


def test_official_prize_revision_appends_new_evaluation_and_preserves_old(tmp_path):
    state = _state(tmp_path)
    update_evaluations(state)
    prizes = json.loads((state / "canonical_prizes.json").read_text(encoding="utf-8"))
    revised = {
        "revision": 2,
        "economic_signature_sha256": "sig-2",
        "prize_tiers": [
            {"hits": 15, "prize_cents": 2_000_000},
            {"hits": 14, "prize_cents": 200_000},
            {"hits": 13, "prize_cents": 20_000},
            {"hits": 12, "prize_cents": 4_000},
            {"hits": 11, "prize_cents": 2_000},
        ],
    }
    prizes["contests"][0]["revisions"].append(revised)
    _write(state / "canonical_prizes.json", prizes)

    result = update_evaluations(state)
    ledger = json.loads((state / "portfolio_ledger.json").read_text(encoding="utf-8"))
    evaluations = ledger["portfolios"][0]["evaluations"]
    assert result["evaluated"] == [ledger["portfolios"][0]["portfolio_id"]]
    assert [item["evaluation_revision"] for item in evaluations] == [1, 2]
    assert evaluations[0]["prize_revision"] == 1
    assert evaluations[1]["prize_revision"] == 2
    assert evaluations[0]["evaluation_sha256"] != evaluations[1]["evaluation_sha256"]
    assert verify(state)["evaluation_count"] == 2
