from __future__ import annotations

import math
from math import comb

from sare_lotofacil.experiments.joint_models import (
    TOTAL_SIMPLE_CARDS,
    UNIFORM_JOINT_LOG_LOSS,
    AdditiveConditionalSubsetModel,
    fit_regularized_additive_joint,
    joint_log_skill_vs_uniform,
    uniform_joint_model,
)


def test_uniform_joint_probability_is_exact() -> None:
    model = uniform_joint_model()
    card = tuple(range(1, 16))
    score = model.score_card(card)

    assert TOTAL_SIMPLE_CARDS == comb(25, 15) == 3_268_760
    assert math.isclose(score.probability, 1.0 / TOTAL_SIMPLE_CARDS, rel_tol=1e-12)
    assert math.isclose(score.log_loss, UNIFORM_JOINT_LOG_LOSS, rel_tol=1e-12)
    assert math.isclose(joint_log_skill_vs_uniform(model, card), 0.0, abs_tol=1e-12)


def test_additive_map_card_is_global_top_15_weights() -> None:
    log_weights = tuple(float(number) for number in range(1, 26))
    model = AdditiveConditionalSubsetModel(log_weights, source="TEST")

    assert model.map_card() == tuple(range(11, 26))
    assert model.map_score().card == tuple(range(11, 26))


def test_additive_model_prefers_higher_weight_card() -> None:
    model = AdditiveConditionalSubsetModel(tuple(float(number) / 10.0 for number in range(1, 26)))
    low_card = tuple(range(1, 16))
    high_card = tuple(range(11, 26))

    assert model.card_log_probability(high_card) > model.card_log_probability(low_card)


def test_regularized_fit_moves_repeated_numbers_up() -> None:
    repeated = tuple(range(11, 26))
    training = [repeated for _ in range(20)]
    model = fit_regularized_additive_joint(training, prior_strength=10.0)

    assert model.map_card() == repeated


def test_equal_log_weights_remain_uniform_under_cardinality_conditioning() -> None:
    model = AdditiveConditionalSubsetModel((3.5,) * 25)
    a = tuple(range(1, 16))
    b = tuple(range(11, 26))

    assert math.isclose(model.card_log_probability(a), -UNIFORM_JOINT_LOG_LOSS, rel_tol=1e-12)
    assert math.isclose(model.card_log_probability(b), -UNIFORM_JOINT_LOG_LOSS, rel_tol=1e-12)
