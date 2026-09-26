from __future__ import annotations

import math
from statistics import fmean, stdev
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.dynamic_joint import ExponentiallyWeightedJointState
from sare_lotofacil.experiments.joint_backtest import JointWalkForwardResult, JointWindowOutcome
from sare_lotofacil.experiments.joint_models import UNIFORM_JOINT_LOG_LOSS, joint_log_loss


def _mean_ci95(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        raise ValueError("é necessário ao menos um valor")
    mean = fmean(values)
    if len(values) == 1:
        return mean, mean, mean
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin


def walk_forward_dynamic_joint(
    draws: Sequence[Iterable[int]],
    *,
    half_life: float,
    min_train: int = 100,
    prior_strength: float = 100.0,
    prior_inclusion: float = 0.6,
    min_successful_windows: int = 30,
) -> JointWalkForwardResult:
    """Evaluate one fixed predeclared exponentially weighted P15-H102 model.

    The half-life is fixed for the entire run. It is not optimized on the target
    outcomes. Every target is scored before it is incorporated into the state.
    """

    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    if min_successful_windows <= 0:
        raise ValueError("min_successful_windows deve ser positivo")

    state = ExponentiallyWeightedJointState(
        half_life=half_life,
        prior_strength=prior_strength,
        prior_inclusion=prior_inclusion,
    )
    for draw in normalized[:min_train]:
        state.update(draw)

    outcomes: list[JointWindowOutcome] = []
    skills: list[float] = []
    losses: list[float] = []
    map_hits_values: list[int] = []
    histogram: dict[int, int] = {}

    for target_index in range(min_train, len(normalized)):
        model = state.model()
        target = normalized[target_index]
        loss = joint_log_loss(model, target)
        skill = UNIFORM_JOINT_LOG_LOSS - loss
        map_card = model.map_card()
        map_hits = len(set(map_card).intersection(target))

        losses.append(loss)
        skills.append(skill)
        map_hits_values.append(map_hits)
        histogram[map_hits] = histogram.get(map_hits, 0) + 1
        outcomes.append(
            JointWindowOutcome(
                target_index=target_index,
                training_size=target_index,
                joint_log_loss=loss,
                joint_log_skill_vs_uniform=skill,
                map_card=map_card,
                map_hits=map_hits,
                exact_15=map_hits == 15,
            )
        )

        state.update(target)

    mean_skill, ci_low, ci_high = _mean_ci95(skills)
    status = "VALID" if len(outcomes) >= min_successful_windows else "INCONCLUSIVE"

    return JointWalkForwardResult(
        model_name=f"P15_H102_EW_HALF_LIFE_{half_life:g}",
        status=status,
        predictive_evidence="NOT_ESTABLISHED",
        predictions=len(outcomes),
        min_train=min_train,
        prior_strength=prior_strength,
        uniform_joint_log_loss=UNIFORM_JOINT_LOG_LOSS,
        mean_joint_log_loss=fmean(losses),
        mean_joint_log_skill=mean_skill,
        joint_log_skill_ci_low=ci_low,
        joint_log_skill_ci_high=ci_high,
        mean_map_hits=fmean(map_hits_values),
        min_map_hits=min(map_hits_values),
        max_map_hits=max(map_hits_values),
        exact_15_hits=sum(1 for hits in map_hits_values if hits == 15),
        map_hits_histogram=tuple(sorted(histogram.items())),
        outcomes=tuple(outcomes),
    )


def fit_dynamic_joint(
    draws: Sequence[Iterable[int]],
    *,
    half_life: float,
    prior_strength: float = 100.0,
    prior_inclusion: float = 0.6,
):
    state = ExponentiallyWeightedJointState(
        half_life=half_life,
        prior_strength=prior_strength,
        prior_inclusion=prior_inclusion,
    )
    for draw in draws:
        state.update(draw)
    return state.model()
