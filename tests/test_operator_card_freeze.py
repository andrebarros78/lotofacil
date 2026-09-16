from __future__ import annotations

from sare_lotofacil.portfolios.frozen import (
    COMBINATION_SPACE,
    empty_operator_card_ledger,
    freeze_operator_cards,
    validate_operator_card_ledger,
)


def _freeze(ledger: dict, count: int, *, reserved=()):
    return freeze_operator_cards(
        ledger,
        target_contest=3781,
        requested_card_count=count,
        state_snapshot_hash="snapshot-3780",
        created_at_utc="2026-09-16T19:30:00+00:00",
        reserved_cards=reserved,
    )


def _cards(ledger: dict) -> list[tuple[int, ...]]:
    return [
        tuple(item["card"])
        for request in ledger["requests"]
        for item in request["cards"]
        if int(request["target_contest"]) == 3781
    ]


def test_repeated_operator_requests_accumulate_and_never_duplicate_same_target() -> None:
    ledger = empty_operator_card_ledger()
    reserved = (tuple(range(1, 16)),)

    expected_total = 0
    for requested in (1, 1, 10, 1, 4):
        ledger, result = _freeze(ledger, requested, reserved=reserved)
        expected_total += requested
        assert result["status"] == "GITHUB_OPERATOR_CARD_FREEZE_PASS"
        assert result["generated_card_count"] == requested
        assert result["operator_frozen_cards_for_target"] == expected_total
        assert result["total_distinct_frozen_cards_for_target"] == expected_total + 1

    cards = _cards(ledger)
    assert len(cards) == 17
    assert len(set(cards)) == 17
    assert reserved[0] not in set(cards)
    assert ledger["summary"]["by_target"]["3781"] == {
        "requests": 5,
        "operator_frozen_cards": 17,
    }
    assert validate_operator_card_ledger(ledger)["operator_frozen_cards"] == 17


def test_six_existing_plus_1_1_10_1_4_reaches_23_frozen_operator_cards() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 6)
    for requested in (1, 1, 10, 1, 4):
        ledger, _ = _freeze(ledger, requested)

    cards = _cards(ledger)
    assert len(cards) == 23
    assert len(set(cards)) == 23
    assert ledger["summary"]["by_target"]["3781"]["operator_frozen_cards"] == 23


def test_freeze_path_does_not_inherit_legacy_100_card_request_limit() -> None:
    ledger = empty_operator_card_ledger()
    ledger, result = _freeze(ledger, 101)

    assert result["generated_card_count"] == 101
    assert len(set(_cards(ledger))) == 101
    assert COMBINATION_SPACE == 3268760


def test_operator_ledger_detects_tampering() -> None:
    ledger = empty_operator_card_ledger()
    ledger, _ = _freeze(ledger, 1)
    ledger["requests"][0]["cards"][0]["card"][0] = 25

    try:
        validate_operator_card_ledger(ledger)
    except (RuntimeError, ValueError):
        pass
    else:  # pragma: no cover
        raise AssertionError("tampering must be rejected")
