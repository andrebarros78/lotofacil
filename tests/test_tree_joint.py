from __future__ import annotations

import math

from sare_lotofacil.experiments.tree_backtest import walk_forward_tree_joint
from sare_lotofacil.experiments.tree_joint import fit_tree_joint


def test_tree_joint_is_proper_on_identical_training_pattern() -> None:
    repeated = tuple(range(11, 26))
    model = fit_tree_joint([repeated for _ in range(200)], prior_strength=5.0)
    score = model.map_score()

    assert score.card == repeated
    assert score.probability > 0.0
    assert math.isfinite(score.log_loss)


def test_tree_map_respects_exact_cardinality() -> None:
    a = tuple(range(1, 16))
    b = tuple(range(11, 26))
    model = fit_tree_joint([a, b] * 100, prior_strength=20.0)

    card = model.map_card()
    assert len(card) == 15
    assert len(set(card)) == 15
    assert min(card) >= 1
    assert max(card) <= 25


def test_tree_walk_forward_detects_strong_pairwise_structure() -> None:
    a = tuple(range(1, 16))
    b = tuple(range(11, 26))
    draws = [a if index % 2 == 0 else b for index in range(180)]

    result = walk_forward_tree_joint(
        draws,
        min_train=100,
        prior_strength=5.0,
    )

    assert result.status == "VALID"
    assert result.predictions == 80
    assert result.mean_joint_log_skill > 0.0
    assert result.mean_map_hits >= 10.0


def test_tree_walk_forward_never_marks_retrospective_evidence_as_established() -> None:
    repeated = tuple(range(1, 16))
    result = walk_forward_tree_joint(
        [repeated for _ in range(140)],
        min_train=100,
        prior_strength=5.0,
    )
    assert result.predictive_evidence == "NOT_ESTABLISHED"
