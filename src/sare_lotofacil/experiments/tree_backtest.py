from __future__ import annotations

import math
from statistics import fmean, stdev
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.joint_backtest import JointWalkForwardResult, JointWindowOutcome
from sare_lotofacil.experiments.joint_models import UNIFORM_JOINT_LOG_LOSS
from sare_lotofacil.experiments.tree_joint import fit_tree_joint_from_counts


def _mean_ci95(values: Sequence[float]) -> tuple[float, float, float]:
    mean = fmean(values)
    if len(values) == 1:
        return mean, mean, mean
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin


def _update_counts(draw: tuple[int, ...], one_counts: list[int], pair11_counts: list[list[int]]) -> None:
    indices = [number - 1 for number in draw]
    for i in indices:
        one_counts[i] += 1
    for a_pos in range(len(indices)):
        i = indices[a_pos]
        for b_pos in range(a_pos + 1, len(indices)):
            j = indices[b_pos]
            pair11_counts[i][j] += 1
            pair11_counts[j][i] += 1


def walk_forward_tree_joint(
    draws: Sequence[Iterable[int]],
    *,
    min_train: int = 100,
    prior_strength: float = 20.0,
    prior_inclusion: float = 0.6,
    min_successful_windows: int = 30,
) -> JointWalkForwardResult:
    """Leakage-safe P15-H103 walk-forward for pairwise tree dependence."""

    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")

    one_counts = [0] * 25
    pair11_counts = [[0] * 25 for _ in range(25)]
    for draw in normalized[:min_train]:
        _update_counts(draw, one_counts, pair11_counts)

    outcomes: list[JointWindowOutcome] = []
    skills: list[float] = []
    losses: list[float] = []
    hits_values: list[int] = []
    histogram: dict[int, int] = {}

    for target_index in range(min_train, len(normalized)):
        model = fit_tree_joint_from_counts(
            n=target_index,
            one_counts=one_counts,
            pair11_counts=pair11_counts,
            prior_strength=prior_strength,
            prior_inclusion=prior_inclusion,
        )
        target = normalized[target_index]
        loss = -model.card_log_probability(target)
        skill = UNIFORM_JOINT_LOG_LOSS - loss
        map_card = model.map_card()
        hits = len(set(map_card).intersection(target))

        losses.append(loss)
        skills.append(skill)
        hits_values.append(hits)
        histogram[hits] = histogram.get(hits, 0) + 1
        outcomes.append(
            JointWindowOutcome(
                target_index=target_index,
                training_size=target_index,
                joint_log_loss=loss,
                joint_log_skill_vs_uniform=skill,
                map_card=map_card,
                map_hits=hits,
                exact_15=hits == 15,
            )
        )

        _update_counts(target, one_counts, pair11_counts)

    mean_skill, ci_low, ci_high = _mean_ci95(skills)
    status = "VALID" if len(outcomes) >= min_successful_windows else "INCONCLUSIVE"
    return JointWalkForwardResult(
        model_name="P15_H103_TREE_PAIRWISE_FIXED_CARDINALITY",
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
        mean_map_hits=fmean(hits_values),
        min_map_hits=min(hits_values),
        max_map_hits=max(hits_values),
        exact_15_hits=sum(1 for hits in hits_values if hits == 15),
        map_hits_histogram=tuple(sorted(histogram.items())),
        outcomes=tuple(outcomes),
    )
