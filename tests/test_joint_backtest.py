from __future__ import annotations

from sare_lotofacil.experiments.joint_backtest import walk_forward_additive_joint


def test_joint_walk_forward_detects_strong_synthetic_signal() -> None:
    repeated = tuple(range(11, 26))
    draws = [repeated for _ in range(140)]

    result = walk_forward_additive_joint(
        draws,
        min_train=100,
        prior_strength=10.0,
        min_successful_windows=30,
    )

    assert result.status == "VALID"
    assert result.predictions == 40
    assert result.mean_joint_log_skill > 0.0
    assert result.joint_log_skill_ci_low > 0.0
    assert result.mean_map_hits == 15.0
    assert result.exact_15_hits == 40
    assert result.predictive_evidence == "NOT_ESTABLISHED"


def test_joint_walk_forward_updates_only_after_target_scoring() -> None:
    first = tuple(range(1, 16))
    second = tuple(range(11, 26))
    draws = [first for _ in range(100)] + [second, second]

    result = walk_forward_additive_joint(
        draws,
        min_train=100,
        prior_strength=10.0,
        min_successful_windows=1,
    )

    first_outcome, second_outcome = result.outcomes
    assert first_outcome.target_index == 100
    assert first_outcome.map_card == first
    assert first_outcome.map_hits == 5
    assert second_outcome.target_index == 101
    assert second_outcome.training_size == 101


def test_joint_walk_forward_rejects_invalid_training_cut() -> None:
    draw = tuple(range(1, 16))
    draws = [draw for _ in range(10)]

    try:
        walk_forward_additive_joint(draws, min_train=10)
    except ValueError as exc:
        assert "min_train" in str(exc)
    else:
        raise AssertionError("expected ValueError")
