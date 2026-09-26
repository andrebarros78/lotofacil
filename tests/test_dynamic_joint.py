from __future__ import annotations

from sare_lotofacil.experiments.dynamic_backtest import fit_dynamic_joint, walk_forward_dynamic_joint
from sare_lotofacil.experiments.dynamic_joint import ExponentiallyWeightedJointState


def test_dynamic_state_half_life_decay() -> None:
    state = ExponentiallyWeightedJointState(half_life=1.0, prior_strength=10.0)
    state.update(tuple(range(1, 16)))
    assert state.effective_n == 1.0
    state.update(tuple(range(11, 26)))
    assert abs(state.effective_n - 1.5) < 1e-12
    assert state.updates == 2


def test_dynamic_walk_forward_detects_recent_regime() -> None:
    old = tuple(range(1, 16))
    new = tuple(range(11, 26))
    draws = [old for _ in range(100)] + [new for _ in range(80)]

    result = walk_forward_dynamic_joint(
        draws,
        half_life=10.0,
        min_train=100,
        prior_strength=10.0,
    )

    assert result.status == "VALID"
    assert result.predictions == 80
    assert result.outcomes[0].map_card == old
    assert result.outcomes[-1].map_card == new
    assert result.mean_map_hits > 12.0


def test_dynamic_fit_emphasizes_recent_observations() -> None:
    old = tuple(range(1, 16))
    new = tuple(range(11, 26))
    draws = [old for _ in range(100)] + [new for _ in range(40)]

    model = fit_dynamic_joint(draws, half_life=5.0, prior_strength=10.0)
    assert model.map_card() == new
