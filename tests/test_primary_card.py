from sare_lotofacil.portfolios.primary import (
    PRIMARY_MODEL_NAME,
    SECONDARY_MODEL_NAME,
    SELECTION_METHOD,
    build_primary_card,
    select_primary_card,
    validate_primary_card_payload,
)


def test_primary_card_selects_exactly_top_15_by_primary_score() -> None:
    primary = [index / 100.0 for index in range(1, 26)]
    secondary = [0.5] * 25
    decision = select_primary_card(
        primary,
        secondary,
        target_contest=101,
        training_last_contest=100,
    )
    assert decision.card == tuple(range(11, 26))
    assert decision.ranking[:5] == (25, 24, 23, 22, 21)
    assert decision.primary_model == PRIMARY_MODEL_NAME
    assert decision.secondary_model == SECONDARY_MODEL_NAME
    assert decision.selection_method == SELECTION_METHOD
    assert len(decision.decision_sha256) == 64


def test_primary_card_uses_secondary_model_only_as_tiebreak() -> None:
    primary = [0.6] * 25
    secondary = [index / 100.0 for index in range(1, 26)]
    decision = select_primary_card(
        primary,
        secondary,
        target_contest=101,
        training_last_contest=100,
    )
    assert decision.card == tuple(range(11, 26))


def test_primary_card_from_history_is_deterministic_and_single() -> None:
    draws = tuple(tuple(range(1, 16)) for _ in range(120))
    first = build_primary_card(draws, target_contest=121, training_last_contest=120)
    second = build_primary_card(draws, target_contest=121, training_last_contest=120)
    assert first == second
    assert first.card == tuple(range(1, 16))
    assert len(first.card) == len(set(first.card)) == 15


def test_primary_card_rejects_non_next_target() -> None:
    try:
        select_primary_card([0.6] * 25, [0.6] * 25, target_contest=102, training_last_contest=100)
    except ValueError as exc:
        assert str(exc) == "PRIMARY_CARD_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE"
    else:  # pragma: no cover
        raise AssertionError("target não adjacente deveria falhar")


def test_primary_card_payload_semantics_are_recomputed() -> None:
    primary = [index / 100.0 for index in range(1, 26)]
    secondary = [0.5] * 25
    decision = select_primary_card(
        primary,
        secondary,
        target_contest=101,
        training_last_contest=100,
    )
    verified = validate_primary_card_payload(
        decision.to_dict(),
        primary,
        secondary,
        target_contest=101,
        training_last_contest=100,
    )
    assert verified == decision


def test_primary_card_payload_rejects_coherently_rehashed_wrong_decision() -> None:
    primary = [index / 100.0 for index in range(1, 26)]
    secondary = [0.5] * 25
    payload = select_primary_card(
        primary,
        secondary,
        target_contest=101,
        training_last_contest=100,
    ).to_dict()
    payload["card"] = list(range(1, 16))
    payload["decision_sha256"] = "0" * 64

    try:
        validate_primary_card_payload(
            payload,
            primary,
            secondary,
            target_contest=101,
            training_last_contest=100,
        )
    except RuntimeError as exc:
        assert str(exc) == "PRIMARY_CARD_FROZEN_DECISION_MISMATCH"
    else:  # pragma: no cover
        raise AssertionError("decisão semântica adulterada deveria falhar")
