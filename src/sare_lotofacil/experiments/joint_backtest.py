from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from statistics import fmean, stdev
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.joint_models import (
    UNIFORM_JOINT_LOG_LOSS,
    AdditiveConditionalSubsetModel,
    joint_log_loss,
)


@dataclass(frozen=True, slots=True)
class JointWindowOutcome:
    target_index: int
    training_size: int
    joint_log_loss: float
    joint_log_skill_vs_uniform: float
    map_card: tuple[int, ...]
    map_hits: int
    exact_15: bool


@dataclass(frozen=True, slots=True)
class JointWalkForwardResult:
    model_name: str
    status: str
    predictive_evidence: str
    predictions: int
    min_train: int
    prior_strength: float
    uniform_joint_log_loss: float
    mean_joint_log_loss: float
    mean_joint_log_skill: float
    joint_log_skill_ci_low: float
    joint_log_skill_ci_high: float
    mean_map_hits: float
    min_map_hits: int
    max_map_hits: int
    exact_15_hits: int
    map_hits_histogram: tuple[tuple[int, int], ...]
    outcomes: tuple[JointWindowOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _model_from_counts(
    counts: Sequence[int],
    *,
    training_size: int,
    prior_strength: float,
    prior_inclusion: float,
) -> AdditiveConditionalSubsetModel:
    if len(counts) != 25:
        raise ValueError("são necessários 25 contadores")
    if training_size < 0:
        raise ValueError("training_size inválido")
    if prior_strength <= 0:
        raise ValueError("prior_strength deve ser positivo")
    if not 0.0 < prior_inclusion < 1.0:
        raise ValueError("prior_inclusion deve estar em (0, 1)")

    alpha = prior_strength * prior_inclusion
    beta = prior_strength * (1.0 - prior_inclusion)
    log_weights: list[float] = []
    for count in counts:
        posterior_p = (int(count) + alpha) / (training_size + alpha + beta)
        log_weights.append(math.log(posterior_p) - math.log1p(-posterior_p))
    return AdditiveConditionalSubsetModel(
        tuple(log_weights),
        source=f"P15_H101_PREQUENTIAL_PRIOR_{prior_strength:g}",
    )


def _mean_ci95(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        raise ValueError("é necessário ao menos um valor")
    mean = fmean(values)
    if len(values) == 1:
        return mean, mean, mean
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin


def walk_forward_additive_joint(
    draws: Sequence[Iterable[int]],
    *,
    min_train: int = 100,
    prior_strength: float = 100.0,
    prior_inclusion: float = 0.6,
    min_successful_windows: int = 30,
) -> JointWalkForwardResult:
    """Prequential evaluation of P15-H101 with no target leakage.

    For each target, model parameters are computed only from contests before the
    target.  The target is scored, the single MAP card is evaluated, and only
    then is the target incorporated into the state for the next window.
    """

    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    if min_successful_windows <= 0:
        raise ValueError("min_successful_windows deve ser positivo")

    counts = [0] * 25
    for draw in normalized[:min_train]:
        for number in draw:
            counts[number - 1] += 1

    outcomes: list[JointWindowOutcome] = []
    skills: list[float] = []
    losses: list[float] = []
    map_hits_values: list[int] = []
    histogram: dict[int, int] = {}

    for target_index in range(min_train, len(normalized)):
        model = _model_from_counts(
            counts,
            training_size=target_index,
            prior_strength=prior_strength,
            prior_inclusion=prior_inclusion,
        )
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

        # Update only after scoring the frozen target.
        for number in target:
            counts[number - 1] += 1

    mean_skill, ci_low, ci_high = _mean_ci95(skills)
    status = "VALID" if len(outcomes) >= min_successful_windows else "INCONCLUSIVE"

    return JointWalkForwardResult(
        model_name="P15_H101_REGULARIZED_CONDITIONAL_BERNOULLI",
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
