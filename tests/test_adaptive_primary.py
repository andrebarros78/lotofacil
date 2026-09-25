from __future__ import annotations

import json
from datetime import date

from sare_lotofacil.portfolios.adaptive import (
    SELECTION_METHOD,
    build_adaptive_primary_card,
)
from scripts.build_adaptive_challenger import build_adaptive_challenger


def _draw(numbers: range | tuple[int, ...]) -> tuple[int, ...]:
    return tuple(numbers)


def _write_state(state, records, *, next_target: int, champion_card: list[int]) -> None:
    (state / "canonical_history.json").write_text(
        json.dumps({"records": records}), encoding="utf-8"
    )
    (state / "latest.json").write_text(
        json.dumps({"next_prediction_target": next_target}), encoding="utf-8"
    )
    (state / "prospective_ledger.json").write_text(
        json.dumps(
            {
                "predictions": [
                    {
                        "target_contest": next_target,
                        "primary_card": {
                            "card": champion_card,
                            "decision_sha256": "a" * 64,
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_adaptive_card_is_deterministic_has_mass_15_and_15_unique_numbers() -> None:
    draws = tuple(_draw(range(1, 16)) for _ in range(360))
    first = build_adaptive_primary_card(
        draws,
        target_contest=361,
        training_last_contest=360,
        validation_windows=60,
        min_train=300,
    )
    second = build_adaptive_primary_card(
        draws,
        target_contest=361,
        training_last_contest=360,
        validation_windows=60,
        min_train=300,
    )
    assert first == second
    assert first.selection_method == SELECTION_METHOD
    assert first.card == tuple(range(1, 16))
    assert len(first.card) == len(set(first.card)) == 15
    assert abs(sum(first.probabilities) - 15.0) < 1e-9
    assert len(first.leaderboard) >= 10


def test_adaptive_card_reacts_to_recent_regime_instead_of_full_history_lock_in() -> None:
    old = tuple(_draw(range(1, 16)) for _ in range(320))
    recent = tuple(_draw(range(11, 26)) for _ in range(120))
    draws = old + recent
    decision = build_adaptive_primary_card(
        draws,
        target_contest=441,
        training_last_contest=440,
        validation_windows=120,
        min_train=300,
    )
    assert len(set(decision.card).intersection(range(11, 26))) >= 12
    assert decision.selected_model.family in {"rolling", "exponential", "blend"}
    assert decision.selected_metrics.mean_hits >= 12.0


def test_adaptive_card_rejects_non_adjacent_target() -> None:
    draws = tuple(_draw(range(1, 16)) for _ in range(360))
    try:
        build_adaptive_primary_card(
            draws,
            target_contest=362,
            training_last_contest=360,
            validation_windows=60,
            min_train=300,
        )
    except ValueError as exc:
        assert str(exc) == "ADAPTIVE_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE"
    else:  # pragma: no cover
        raise AssertionError("non-adjacent target should fail")


def test_build_adaptive_challenger_uses_only_canonical_state(tmp_path) -> None:
    state = tmp_path / "operations"
    state.mkdir()
    records = [
        {
            "contest_id": contest_id,
            "draw_date": date(2025, 1, 1).isoformat(),
            "numbers": list(range(1, 16)),
        }
        for contest_id in range(1, 361)
    ]
    _write_state(
        state,
        records,
        next_target=361,
        champion_card=list(range(1, 16)),
    )
    payload = build_adaptive_challenger(state)
    assert payload["status"] == "ADAPTIVE_CHALLENGER_FROZEN"
    assert payload["target_contest"] == 361
    assert payload["card"] == list(range(1, 16))
    assert payload["champion_control"]["overlap"] == 15
    assert payload["policy"]["future_results_forbidden"] is True
    assert payload["policy"]["append_only_evaluation_history"] is True
    assert payload["history_summary"]["entry_count"] == 1
    assert payload["history_summary"]["pending_count"] == 1


def test_adaptive_history_is_idempotent_for_same_pending_target(tmp_path) -> None:
    state = tmp_path / "operations"
    state.mkdir()
    records = [
        {
            "contest_id": contest_id,
            "draw_date": "2025-01-01",
            "numbers": list(range(1, 16)),
        }
        for contest_id in range(1, 361)
    ]
    _write_state(state, records, next_target=361, champion_card=list(range(1, 16)))
    first = build_adaptive_challenger(state)
    (state / "adaptive_challenger.json").write_text(
        json.dumps(first), encoding="utf-8"
    )
    second = build_adaptive_challenger(state)

    assert second["decision_sha256"] == first["decision_sha256"]
    assert second["generated_at_utc"] == first["generated_at_utc"]
    assert second["history_summary"]["entry_count"] == 1
    assert second["history_summary"]["pending_count"] == 1


def test_adaptive_history_evaluates_frozen_target_before_freezing_next(tmp_path) -> None:
    state = tmp_path / "operations"
    state.mkdir()
    records = [
        {
            "contest_id": contest_id,
            "draw_date": "2025-01-01",
            "numbers": list(range(1, 16)),
        }
        for contest_id in range(1, 361)
    ]
    _write_state(state, records, next_target=361, champion_card=list(range(1, 16)))
    frozen = build_adaptive_challenger(state)
    (state / "adaptive_challenger.json").write_text(
        json.dumps(frozen), encoding="utf-8"
    )

    records.append(
        {
            "contest_id": 361,
            "draw_date": "2025-01-02",
            "numbers": list(range(1, 16)),
        }
    )
    _write_state(state, records, next_target=362, champion_card=list(range(1, 16)))
    advanced = build_adaptive_challenger(state)

    assert advanced["target_contest"] == 362
    assert advanced["history_summary"]["entry_count"] == 2
    assert advanced["history_summary"]["evaluated_count"] == 1
    assert advanced["history_summary"]["pending_count"] == 1
    prior = next(item for item in advanced["history"] if item["target_contest"] == 361)
    assert prior["evaluation"]["observed_contest"] == 361
    assert prior["evaluation"]["hits"] == 15
    assert prior["evaluation"]["gap_to_15"] == 0
    assert prior["evaluation"]["champion_hits"] == 15
    assert prior["evaluation"]["delta_hits_vs_champion"] == 0
