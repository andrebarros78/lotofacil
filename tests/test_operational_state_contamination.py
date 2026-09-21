from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts import github_operational_cycle as cycle
from scripts.github_operator_freeze_cards import run as run_operator_freeze
from scripts.verify_github_operational_state import _verify_operator_cards, verify
from sare_lotofacil.analysis.post_contest_report import (
    build_post_contest_reports,
    render_post_contest_report_markdown,
)
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.portfolios import frozen as frozen_mod
from sare_lotofacil.portfolios.frozen import (
    card_for_generation_index,
    card_sha256,
    empty_operator_card_ledger,
    freeze_operator_cards,
    validate_operator_card_ledger,
)


def _records(count: int = 6):
    base = date(2026, 1, 1)
    return tuple(
        validate_contest(index, base + timedelta(days=index), range(1, 16))
        for index in range(1, count + 1)
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _state_fixture(tmp_path: Path) -> Path:
    state = tmp_path / "operations"
    state.mkdir(parents=True)
    records = _records(6)

    history = {
        "schema_version": 1,
        "records": [
            {
                "contest_id": record.contest_id,
                "draw_date": record.draw_date.isoformat(),
                "numbers": list(record.numbers),
            }
            for record in records
        ],
    }
    history_path = state / "canonical_history.json"
    _write_json(history_path, history)

    manifest_path = state / "bootstrap_manifest.json"
    _write_json(manifest_path, {"schema_version": 1, "fixture": True})

    evaluated = cycle._build_prediction(
        6,
        "snapshot-before-6",
        records[:5],
        "2026-09-20T10:00:00+00:00",
    )
    cycle._evaluate_prediction(evaluated, records[5])
    pending = cycle._build_prediction(
        7,
        "snapshot-current",
        records,
        "2026-09-21T10:00:00+00:00",
    )
    ledger = cycle._empty_ledger()
    ledger["predictions"] = [evaluated, pending]
    ledger["summary"] = cycle.summarize_ledger(ledger)
    ledger_path = state / "prospective_ledger.json"
    _write_json(ledger_path, ledger)

    reports = build_post_contest_reports(ledger)
    _write_json(state / "post_contest_reports.json", reports)
    _write_json(state / "latest_post_contest_report.json", reports["latest_report"])
    (state / "latest_post_contest_report.md").write_text(
        render_post_contest_report_markdown(reports["latest_report"]) + "\n",
        encoding="utf-8",
    )

    latest = {
        "status": "GITHUB_OPERATIONAL_CYCLE_PASS",
        "official_latest_contest": 6,
        "next_prediction_target": 7,
        "snapshot_contests": 6,
        "snapshot_id": "snap-current",
        "snapshot_hash": "snapshot-current",
        "canonical_history_sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
        "bootstrap_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "prospective": ledger["summary"],
        "post_contest_report": {
            "report_count": reports["report_count"],
            "latest_contest": reports["latest_contest"],
            "emitted_for_contests": [6],
        },
    }
    _write_json(state / "latest.json", latest)
    return state


def _ledger(state: Path) -> dict:
    return json.loads((state / "prospective_ledger.json").read_text(encoding="utf-8"))


def _save_ledger(state: Path, ledger: dict) -> None:
    _write_json(state / "prospective_ledger.json", ledger)
    latest = json.loads((state / "latest.json").read_text(encoding="utf-8"))
    latest["prospective"] = ledger["summary"]
    _write_json(state / "latest.json", latest)


def test_clean_fixture_passes_full_operational_verifier(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    result = verify(state)
    assert result["status"] == "GITHUB_OPERATIONAL_AUDIT_PASS"
    assert result["pending_predictions"] == 1
    assert result["last_contest"] == 6


def test_verifier_rejects_wrong_primary_card_even_with_prediction_rehashed(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    ledger = _ledger(state)
    pending = ledger["predictions"][-1]
    pending["primary_card"]["card"] = list(range(11, 26))
    pending["prediction_sha256"] = cycle._sha256(cycle._prediction_hash_payload(pending))
    _save_ledger(state, ledger)

    with pytest.raises(RuntimeError, match="primary card semantic mismatch"):
        verify(state)


def test_verifier_rejects_observed_numbers_contamination(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    ledger = _ledger(state)
    evaluated = ledger["predictions"][0]
    evaluated["evaluation"]["observed_numbers"] = list(range(11, 26))
    _save_ledger(state, ledger)

    with pytest.raises(RuntimeError, match="evaluation observed numbers mismatch"):
        verify(state)


def test_verifier_rejects_primary_card_hit_contamination(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    ledger = _ledger(state)
    evaluated = ledger["predictions"][0]
    evaluated["primary_card_evaluation"]["hits"] -= 1
    _save_ledger(state, ledger)

    with pytest.raises(RuntimeError, match="primary card hit mismatch"):
        verify(state)


def test_verifier_rejects_latest_target_and_history_hash_drift(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    latest_path = state / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["next_prediction_target"] = 8
    _write_json(latest_path, latest)
    with pytest.raises(RuntimeError, match="next prediction target diverges"):
        verify(state)

    state = _state_fixture(tmp_path / "second")
    latest_path = state / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["canonical_history_sha256"] = "0" * 64
    _write_json(latest_path, latest)
    with pytest.raises(RuntimeError, match="canonical history hash diverges"):
        verify(state)


def _prospective_for_operator(state: Path) -> dict:
    return json.loads((state / "prospective_ledger.json").read_text(encoding="utf-8"))


def test_operator_verifier_rejects_unjustified_generation_skip(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    prospective = _prospective_for_operator(state)
    pending = prospective["predictions"][-1]
    reserved = (pending["primary_card"]["card"],)

    ledger = empty_operator_card_ledger()
    ledger, _ = freeze_operator_cards(
        ledger,
        target_contest=7,
        requested_card_count=1,
        state_snapshot_hash="snapshot-current",
        created_at_utc="2026-09-21T10:01:00+00:00",
        idempotency_key="skip-proof",
        source_commit="source-sha",
        workflow_run_id="run-1",
        reserved_cards=reserved,
    )

    request = ledger["requests"][0]
    item = request["cards"][0]
    index = 3
    card = card_for_generation_index(7, index)
    digest = card_sha256(card)
    item["generation_index"] = index
    item["card"] = list(card)
    item["payload_hash"] = digest
    item["card_sha256"] = digest
    item["freeze_id"] = "freeze-" + frozen_mod._sha256(
        {
            "target_contest": 7,
            "type": frozen_mod.FREEZE_TYPE,
            "payload_hash": digest,
            "generation_index": index,
            "idempotency_key": "skip-proof",
        }
    )[:32]
    request["generation_index_next"] = index + 1
    request["request_sha256"] = frozen_mod._sha256(
        frozen_mod._request_hash_payload(request)
    )
    validate_operator_card_ledger(ledger)
    _write_json(state / "operator_card_ledger.json", ledger)

    with pytest.raises(RuntimeError, match="OPERATOR_CARD_UNJUSTIFIED_GENERATION_SKIP"):
        _verify_operator_cards(state, prospective)


def test_operator_verifier_rejects_cross_snapshot_contamination(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    prospective = _prospective_for_operator(state)
    pending = prospective["predictions"][-1]
    ledger = empty_operator_card_ledger()
    ledger, _ = freeze_operator_cards(
        ledger,
        target_contest=7,
        requested_card_count=1,
        state_snapshot_hash="wrong-snapshot",
        created_at_utc="2026-09-21T10:02:00+00:00",
        idempotency_key="snapshot-proof",
        source_commit="source-sha",
        workflow_run_id="run-2",
        reserved_cards=(pending["primary_card"]["card"],),
    )
    _write_json(state / "operator_card_ledger.json", ledger)

    with pytest.raises(RuntimeError, match="OPERATOR_CARD_STATE_SNAPSHOT_MISMATCH"):
        _verify_operator_cards(state, prospective)


def test_operator_writer_rejects_noncanonical_future_target(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    with pytest.raises(RuntimeError, match="OPERATOR_CARD_TARGET_MUST_EQUAL_CANONICAL_NEXT"):
        run_operator_freeze(
            state,
            card_count=1,
            target_contest=8,
            idempotency_key="future-target",
            source_commit="source-sha",
            workflow_run_id="run-3",
        )


def test_operator_writer_rejects_pending_prediction_snapshot_drift(tmp_path: Path) -> None:
    state = _state_fixture(tmp_path)
    ledger = _ledger(state)
    ledger["predictions"][-1]["training_snapshot_hash"] = "stale-snapshot"
    _save_ledger(state, ledger)

    with pytest.raises(RuntimeError, match="OPERATOR_CARD_STATE_SNAPSHOT_MISMATCH"):
        run_operator_freeze(
            state,
            card_count=1,
            target_contest=7,
            idempotency_key="stale-snapshot",
            source_commit="source-sha",
            workflow_run_id="run-4",
        )
