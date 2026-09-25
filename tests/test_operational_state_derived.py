from __future__ import annotations

from pathlib import Path

import pytest

from sare_lotofacil.operational_state import (
    DERIVED_STATE_FILES,
    StateTransactionError,
    publish_state_transaction,
    verify_state_commit,
)


def _committed_state(state: Path) -> None:
    publish_state_transaction(
        state,
        {
            "canonical_history.json": b'{"history":true}\n',
            "prospective_ledger.json": b'{"ledger":true}\n',
            "latest.json": b'{"latest":true}\n',
        },
        generation_id="baseline",
        metadata={"source": "github_operational_cycle"},
    )


def test_known_derived_artifacts_do_not_invalidate_core_commit_receipt(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _committed_state(state)

    (state / "learning_ledger.json").write_text('{"entries":8}\n', encoding="utf-8")
    (state / "adaptive_challenger.json").write_text('{"target":3789}\n', encoding="utf-8")

    verified = verify_state_commit(state, allow_legacy=False)
    assert verified["status"] == "STATE_COMMIT_VERIFIED"
    assert verified["verified_files"] == 3
    assert DERIVED_STATE_FILES == frozenset(
        {"learning_ledger.json", "adaptive_challenger.json"}
    )


def test_unknown_extra_file_still_fails_closed(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _committed_state(state)
    (state / "unexpected.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(StateTransactionError, match="file set mismatch"):
        verify_state_commit(state, allow_legacy=False)


def test_derived_artifact_cannot_be_published_as_core_transaction(tmp_path: Path) -> None:
    state = tmp_path / "operations"
    _committed_state(state)

    with pytest.raises(ValueError, match="derived operational state path is non-transactional"):
        publish_state_transaction(
            state,
            {"learning_ledger.json": b"{}\n"},
            generation_id="invalid-derived-transaction",
        )
