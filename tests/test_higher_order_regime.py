from __future__ import annotations

import math

from sare_lotofacil.experiments.higher_order_backtest import (
    fit_next_higher_order_regime,
    walk_forward_higher_order_regime,
)
from sare_lotofacil.experiments.higher_order_regime import (
    fit_higher_order_blocks,
    learn_information_blocks,
)


def test_information_blocks_partition_universe() -> None:
    a = tuple(range(1, 16))
    b = tuple(range(11, 26))
    blocks = learn_information_blocks([a, b] * 60)

    assert len(blocks) == 5
    assert all(len(block) == 5 for block in blocks)
    assert sorted(number for block in blocks for number in block) == list(range(1, 26))


def test_higher_order_model_is_proper_and_recovers_repeated_state() -> None:
    repeated = tuple(range(3, 18))
    model = fit_higher_order_blocks([repeated for _ in range(240)], prior_strength=8.0)
    score = model.map_score()

    assert score.card == repeated
    assert len(score.card) == 15
    assert math.isfinite(score.log_loss)
    assert 0.0 < score.probability <= 1.0


def test_higher_order_walk_forward_detects_strong_repeatable_structure() -> None:
    repeated = tuple(range(6, 21))
    result = walk_forward_higher_order_regime(
        [repeated for _ in range(160)],
        min_train=100,
        prior_strength=8.0,
        recent_window=60,
    )

    assert result.status == "VALID"
    assert result.predictions == 60
    assert result.mean_joint_log_skill > 0.0
    assert result.mean_map_hits == 15.0
    assert result.exact_15_hits == 60
    assert result.predictive_evidence == "NOT_ESTABLISHED"


def test_regime_selector_cannot_see_future_suffix() -> None:
    a = tuple(range(1, 16))
    b = tuple(range(11, 26))
    prefix = [a for _ in range(100)] + [b]
    history_one = prefix + [a for _ in range(39)]
    history_two = prefix + [b for _ in range(39)]

    first = walk_forward_higher_order_regime(
        history_one,
        min_train=100,
        prior_strength=8.0,
        recent_window=40,
    ).outcomes[0]
    second = walk_forward_higher_order_regime(
        history_two,
        min_train=100,
        prior_strength=8.0,
        recent_window=40,
    ).outcomes[0]

    assert first.map_card == second.map_card
    assert first.selected_regime == second.selected_regime
    assert first.selected_joint_log_loss == second.selected_joint_log_loss


def test_next_regime_candidate_has_exact_cardinality_and_auditable_decision() -> None:
    a = tuple(range(1, 16))
    b = tuple(range(11, 26))
    draws = [a if index % 3 else b for index in range(180)]

    model, decision = fit_next_higher_order_regime(
        draws,
        min_train=100,
        prior_strength=16.0,
        recent_window=60,
    )
    card = model.map_card()

    assert len(card) == 15
    assert len(set(card)) == 15
    assert decision.selected_regime in {"LONG", "RECENT"}
    assert decision.long_training_size == 180
    assert decision.recent_training_size == 60
