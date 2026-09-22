from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import github_operational_cycle as cycle
from sare_lotofacil.analysis.post_contest_report import (
    build_post_contest_reports,
    render_post_contest_report_markdown,
)
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.operational_state import (
    STATE_COMMIT_FILE,
    StateTransactionError,
    publish_state_transaction,
    recover_state_transaction,
    verify_state_commit,
)
from sare_lotofacil.persistence.snapshot_identity import semantic_data_snapshot_hash
from scripts.verify_github_operational_state import verify


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _baseline_state(path: Path) -> dict[str, bytes]:
    files = {
        "canonical_history.json": b'{"version":"old-history"}\n',
        "prospective_ledger.json": b'{"version":"old-ledger"}\n',
        "latest.json": b'{"version":"old-latest"}\n',
    }
    for relative, content in files.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    publish_state_transaction(
        path,
        files,
        generation_id="cycle-baseline",
        metadata={"source": "github_operational_cycle"},
    )
    return files


@pytest.mark.parametrize("crash_after", [1, 2, 3])
def test_precommit_crash_recovers_complete_previous_generation(
    tmp_path: Path,
    crash_after: int,
) -> None:
    state = tmp_path / "operations"
    old = _baseline_state(state)
    new = {
        "canonical_history.json": b'{"version":"new-history"}\n',
        "prospective_ledger.json": b'{"version":"new-ledger"}\n',
        "latest.json": b'{"version":"new-latest"}\n',
    }

    with pytest.raises(StateTransactionError, match="INJECTED_CRASH_AFTER_REPLACE"):
        publish_state_transaction(
            state,
            new,
            generation_id=f"cycle-crash-{crash_after}",
            metadata={"source": "github_operational_cycle"},
            crash_after_replace=crash_after,
        )

    outcome = recover_state_transaction(state)
    assert outcome == "PREPARED_ROLLED_BACK"
    for relative, content in old.items():
        assert (state / relative).read_bytes() == content

    verified = verify_state_commit(state, allow_legacy=False)
    assert verified["status"] == "STATE_COMMIT_VERIFIED"
    assert verified["generation_id"] == "cycle-baseline"


def test_postcommit_crash_recovers_complete_new_generation(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    new = {
        "canonical_history.json": b'{"version":"new-history"}\n',
        "prospective_ledger.json": b'{"version":"new-ledger"}\n',
        "latest.json": b'{"version":"new-latest"}\n',
    }

    with pytest.raises(StateTransactionError, match="INJECTED_CRASH_AFTER_COMMIT"):
        publish_state_transaction(
            state,
            new,
            generation_id="cycle-committed-before-crash",
            metadata={"source": "github_operational_cycle"},
            crash_after_commit=True,
        )

    outcome = recover_state_transaction(state)
    assert outcome == "COMMITTED_COMPLETED"
    for relative, content in new.items():
        assert (state / relative).read_bytes() == content

    verified = verify_state_commit(state, allow_legacy=False)
    assert verified["generation_id"] == "cycle-committed-before-crash"


def test_commit_receipt_rejects_tampered_or_extra_files(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)

    (state / "latest.json").write_text('{"tampered":true}\n', encoding="utf-8")
    with pytest.raises(StateTransactionError, match="hash mismatch"):
        verify_state_commit(state, allow_legacy=False)

    state = tmp_path / "second"
    _baseline_state(state)
    (state / "uncommitted.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(StateTransactionError, match="file set mismatch"):
        verify_state_commit(state, allow_legacy=False)


def test_auxiliary_transaction_preserves_cycle_ancestry(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    publish_state_transaction(
        state,
        {"canonical_prizes.json": b'{"latest":3784}\n'},
        generation_id="prizes-3784",
        metadata={"source": "canonical_prize_update"},
    )

    verified = verify_state_commit(state, allow_legacy=False)
    assert verified["generation_id"] == "prizes-3784"
    assert verified["metadata"]["parent_generation_id"] == "cycle-baseline"
    assert verified["metadata"]["cycle_generation_id"] == "cycle-baseline"


def test_missing_committed_file_is_rejected(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    (state / "latest.json").unlink()

    with pytest.raises(StateTransactionError, match="file set mismatch"):
        verify_state_commit(state, allow_legacy=False)


def test_recovery_is_idempotent_after_precommit_crash(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    new = {
        "canonical_history.json": b'{"version":"new-history"}\n',
        "prospective_ledger.json": b'{"version":"new-ledger"}\n',
        "latest.json": b'{"version":"new-latest"}\n',
    }
    with pytest.raises(StateTransactionError, match="INJECTED_CRASH_AFTER_REPLACE"):
        publish_state_transaction(
            state,
            new,
            generation_id="cycle-idempotent-recovery",
            metadata={"source": "github_operational_cycle"},
            crash_after_replace=2,
        )

    assert recover_state_transaction(state) == "PREPARED_ROLLED_BACK"
    assert recover_state_transaction(state) == "CLEAN"


def test_generation_chain_advances_parent_generation(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    publish_state_transaction(
        state,
        {"latest.json": b'{"version":"b"}\n'},
        generation_id="cycle-b",
        metadata={"source": "github_operational_cycle"},
    )
    publish_state_transaction(
        state,
        {"latest.json": b'{"version":"c"}\n'},
        generation_id="cycle-c",
        metadata={"source": "github_operational_cycle"},
    )

    verified = verify_state_commit(state, allow_legacy=False)
    assert verified["generation_id"] == "cycle-c"
    assert verified["metadata"]["parent_generation_id"] == "cycle-b"
    assert verified["metadata"]["cycle_generation_id"] == "cycle-c"


def test_orphan_staging_and_atomic_temporaries_are_cleaned(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    state.mkdir(parents=True)
    orphan = state / ".state-txn" / "abandoned" / "new"
    orphan.mkdir(parents=True)
    (orphan / "latest.json").write_bytes(b"orphan\n")
    temp = state / ".latest.json.deadbeef.tmp"
    temp.write_bytes(b"temporary\n")

    assert recover_state_transaction(state) == "ORPHAN_STAGING_REMOVED"
    assert not (state / ".state-txn").exists()
    assert not temp.exists()
    assert recover_state_transaction(state) == "CLEAN"


def test_transactional_state_cannot_silently_regress_to_legacy(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    (state / STATE_COMMIT_FILE).unlink()

    with pytest.raises(
        StateTransactionError,
        match="state commit missing for transactional state",
    ):
        verify_state_commit(state, allow_legacy=True)


def _cycle_fixture(root: Path) -> tuple[Path, tuple]:
    state = root / "operations"
    state.mkdir(parents=True)
    records = tuple(
        validate_contest(
            contest_id,
            date(2026, 9, contest_id),
            tuple(range(contest_id, contest_id + 15)),
        )
        for contest_id in range(1, 7)
    )
    history = {
        "schema_version": 1,
        "created_at_utc": "2026-09-20T10:00:00+00:00",
        "records": [
            {
                "contest_id": record.contest_id,
                "draw_date": record.draw_date.isoformat(),
                "numbers": list(record.numbers),
            }
            for record in records
        ],
    }
    _write_json(state / "canonical_history.json", history)
    _write_json(state / "bootstrap_manifest.json", {"schema_version": 1, "fixture": True})

    evaluated = cycle._build_prediction(
        6,
        "snapshot-before-6",
        records[:5],
        "2026-09-20T10:00:00+00:00",
        data_snapshot_hash=semantic_data_snapshot_hash(records[:5]),
    )
    cycle._evaluate_prediction(evaluated, records[5])
    pending = cycle._build_prediction(
        7,
        "snapshot-current",
        records,
        "2026-09-21T10:00:00+00:00",
        data_snapshot_hash=semantic_data_snapshot_hash(records),
    )
    ledger = cycle._empty_ledger()
    ledger["predictions"] = [evaluated, pending]
    ledger["summary"] = cycle.summarize_ledger(ledger)
    _write_json(state / "prospective_ledger.json", ledger)

    reports = build_post_contest_reports(ledger)
    _write_json(state / "post_contest_reports.json", reports)
    _write_json(state / "latest_post_contest_report.json", reports["latest_report"])
    (state / "latest_post_contest_report.md").write_text(
        render_post_contest_report_markdown(reports["latest_report"]) + "\n",
        encoding="utf-8",
    )
    return state, records


def test_operational_cycle_migrates_legacy_state_to_committed_transaction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    state, records = _cycle_fixture(tmp_path)
    official = CaixaContest(
        record=records[-1],
        prize_tiers=(),
        source_url="fixture://official/6",
        captured_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        raw_payload={"numero": 6, "listaDezenas": list(records[-1].numbers)},
    )
    monkeypatch.setattr(cycle, "_resolve_official_latest", lambda current_last: official)
    monkeypatch.setattr(
        cycle,
        "analyze_core",
        lambda draws: SimpleNamespace(to_dict=lambda: {"fixture": True}),
    )

    result = cycle.run_cycle(state, tmp_path / "runtime")

    assert result["status"] == "GITHUB_OPERATIONAL_CYCLE_PASS"
    assert result["state_transaction"]["previous_commit_status"] == (
        "LEGACY_STATE_WITHOUT_TRANSACTION_COMMIT"
    )
    assert result["state_transaction"]["commit_status"] == "STATE_COMMIT_VERIFIED"
    assert (state / STATE_COMMIT_FILE).exists()

    persisted_latest = json.loads((state / "latest.json").read_text(encoding="utf-8"))
    assert persisted_latest["state_transaction"] == {
        "schema": "operational-state-transaction-v1",
        "generation_id": result["state_transaction"]["generation_id"],
        "recovery_before_cycle": result["state_transaction"]["recovery_before_cycle"],
        "previous_commit_status": "LEGACY_STATE_WITHOUT_TRANSACTION_COMMIT",
    }
    assert "commit_status" not in persisted_latest["state_transaction"]
    assert "committed_files" not in persisted_latest["state_transaction"]
    assert "state_commit_generation_id" not in persisted_latest["state_transaction"]

    audit = verify(state)
    assert audit["status"] == "GITHUB_OPERATIONAL_AUDIT_PASS"
    assert audit["state_transaction"]["status"] == "STATE_COMMIT_VERIFIED"
    assert (
        audit["state_transaction"]["metadata"]["runtime_db_sha256"]
        == hashlib.sha256((tmp_path / "runtime" / "sare.db").read_bytes()).hexdigest()
    )



def test_exact_replay_of_current_generation_is_a_noop(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    files = _baseline_state(state)
    before_commit = (state / STATE_COMMIT_FILE).read_bytes()
    before_hashes = {
        relative: hashlib.sha256((state / relative).read_bytes()).hexdigest()
        for relative in files
    }

    replay = publish_state_transaction(
        state,
        files,
        generation_id="cycle-baseline",
        metadata={"source": "github_operational_cycle", "ignored_on_replay": True},
    )

    assert replay["generation_id"] == "cycle-baseline"
    assert (state / STATE_COMMIT_FILE).read_bytes() == before_commit
    assert {
        relative: hashlib.sha256((state / relative).read_bytes()).hexdigest()
        for relative in files
    } == before_hashes
    verified = verify_state_commit(state, allow_legacy=False)
    assert verified["generation_id"] == "cycle-baseline"
    assert verified["metadata"].get("parent_generation_id") is None


def test_same_generation_with_different_bytes_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _baseline_state(state)
    before_commit = (state / STATE_COMMIT_FILE).read_bytes()

    with pytest.raises(
        StateTransactionError,
        match="generation id collision with different state",
    ):
        publish_state_transaction(
            state,
            {"latest.json": b'{"version":"collision"}\n'},
            generation_id="cycle-baseline",
            metadata={"source": "github_operational_cycle"},
        )

    assert (state / STATE_COMMIT_FILE).read_bytes() == before_commit
    assert verify_state_commit(state, allow_legacy=False)["generation_id"] == "cycle-baseline"
