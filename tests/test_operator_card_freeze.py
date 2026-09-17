from __future__ import annotations

import copy
import json

import pytest

from sare_lotofacil.portfolios.frozen import (
    COMBINATION_SPACE,
    empty_operator_card_ledger,
    freeze_operator_cards,
    recover_operator_freezes,
    validate_operator_card_ledger,
)


def _freeze(ledger: dict, count: int, *, key: str, reserved=()):
    return freeze_operator_cards(
        ledger,
        target_contest=3781,
        requested_card_count=count,
        state_snapshot_hash="snapshot-3780",
        created_at_utc="2026-09-17T20:00:00+00:00",
        idempotency_key=key,
        source_commit="01c9cf12d7c69fccc0b1c9a2324092258d366925",
        workflow_run_id="r1-test-run",
        reserved_cards=reserved,
    )


def _cards(ledger: dict) -> list[tuple[int, ...]]:
    return [
        tuple(item["card"])
        for request in ledger["requests"]
        for item in request["cards"]
        if int(request["target_contest"]) == 3781
    ]


def test_1_plus_1_produces_two_distinct_freezes() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 1, key="req-1")
    ledger, _ = _freeze(ledger, 1, key="req-2")
    records = recover_operator_freezes(ledger, target_contest=3781, expected_card_count=2)
    assert len(records) == 2
    assert len({tuple(item["card"]) for item in records}) == 2
    assert len({item["freeze_id"] for item in records}) == 2


def test_repeated_operator_requests_accumulate_1_1_10_1_4_to_17() -> None:
    ledger = empty_operator_card_ledger()
    reserved = (tuple(range(1, 16)),)
    expected_total = 0
    for sequence, requested in enumerate((1, 1, 10, 1, 4), start=1):
        ledger, result = _freeze(ledger, requested, key=f"req-{sequence}", reserved=reserved)
        expected_total += requested
        assert result["status"] == "GITHUB_OPERATOR_CARD_FREEZE_PASS"
        assert result["generated_card_count"] == requested
        assert result["operator_frozen_cards_for_target"] == expected_total
    cards = _cards(ledger)
    assert len(cards) == 17
    assert len(set(cards)) == 17
    assert reserved[0] not in set(cards)
    assert validate_operator_card_ledger(ledger)["operator_frozen_cards"] == 17


def test_idempotent_replay_does_not_duplicate_freezes() -> None:
    ledger = empty_operator_card_ledger()
    ledger, first = _freeze(ledger, 4, key="same-request")
    frozen_before = json.dumps(ledger, sort_keys=True)
    ledger, replay = _freeze(ledger, 4, key="same-request")
    frozen_after = json.dumps(ledger, sort_keys=True)
    assert replay["status"] == "GITHUB_OPERATOR_CARD_FREEZE_IDEMPOTENT_REPLAY"
    assert replay["generated_card_count"] == 0
    assert replay["replayed_freeze_count"] == 4
    assert replay["freeze_ids"] == first["freeze_ids"]
    assert frozen_after == frozen_before
    assert len(_cards(ledger)) == 4


def test_same_idempotency_key_with_different_request_is_rejected() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 1, key="conflict")
    with pytest.raises(RuntimeError, match="OPERATOR_CARD_IDEMPOTENCY_CONFLICT"):
        _freeze(ledger, 2, key="conflict")


def test_restart_roundtrip_preserves_recovery_and_next_generation() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 6, key="initial")
    restarted = json.loads(json.dumps(ledger))
    assert validate_operator_card_ledger(restarted)["operator_frozen_cards"] == 6
    before = tuple(tuple(item["card"]) for item in recover_operator_freezes(restarted, target_contest=3781, expected_card_count=6))
    restarted, _ = _freeze(restarted, 1, key="after-restart")
    after = _cards(restarted)
    assert tuple(after[:6]) == before
    assert len(after) == 7
    assert len(set(after)) == 7


def test_expected_card_count_mismatch_fails_explicitly() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 1, key="one")
    with pytest.raises(RuntimeError, match="FROZEN_CARD_COUNT_MISMATCH"):
        recover_operator_freezes(ledger, target_contest=3781, expected_card_count=2)


def test_freeze_records_have_required_identity_and_provenance() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 1, key="provenance")
    item = ledger["requests"][0]["cards"][0]
    for field in (
        "freeze_id",
        "target_contest",
        "type",
        "card",
        "payload_hash",
        "created_at_utc",
        "source_commit",
        "workflow_run_id",
        "model_identity",
        "config_identity",
        "state_ref",
        "idempotency_key",
    ):
        assert item[field]


def test_ledger_tampering_is_detected() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 1, key="tamper")
    mutated = copy.deepcopy(ledger)
    mutated["requests"][0]["cards"][0]["payload_hash"] = "0" * 64
    with pytest.raises(RuntimeError, match="OPERATOR_CARD_(REQUEST_HASH|HASH)_MISMATCH"):
        validate_operator_card_ledger(mutated)


def test_freeze_path_does_not_inherit_legacy_100_card_limit() -> None:
    ledger = empty_operator_card_ledger()
    ledger, result = _freeze(ledger, 101, key="101-cards")
    assert result["generated_card_count"] == 101
    assert len(set(_cards(ledger))) == 101
    assert COMBINATION_SPACE == 3268760
