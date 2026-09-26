from __future__ import annotations

import math
from collections import deque
from dataclasses import asdict, dataclass
from statistics import fmean, stdev
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.higher_order_regime import (
    BLOCK_COUNT,
    PATTERN_COUNT,
    BlockPatternConditionalModel,
    fit_block_pattern_from_counts,
    learn_information_blocks,
    pattern_counts_from_draws,
)
from sare_lotofacil.experiments.joint_models import UNIFORM_JOINT_LOG_LOSS


@dataclass(frozen=True, slots=True)
class HigherOrderWindowOutcome:
    target_index: int
    training_size: int
    selected_regime: str
    selector_advantage_before_target: float
    long_joint_log_loss: float
    recent_joint_log_loss: float
    selected_joint_log_loss: float
    selected_joint_log_skill_vs_uniform: float
    map_card: tuple[int, ...]
    map_hits: int
    exact_15: bool


@dataclass(frozen=True, slots=True)
class HigherOrderRegimeResult:
    model_name: str
    status: str
    predictive_evidence: str
    predictions: int
    min_train: int
    prior_strength: float
    recent_window: int
    selector_alpha: float
    switch_margin: float
    blocks: tuple[tuple[int, ...], ...]
    uniform_joint_log_loss: float
    mean_joint_log_loss: float
    mean_joint_log_skill: float
    joint_log_skill_ci_low: float
    joint_log_skill_ci_high: float
    long_mean_joint_log_skill: float
    recent_mean_joint_log_skill: float
    mean_map_hits: float
    min_map_hits: int
    max_map_hits: int
    exact_15_hits: int
    selected_long_windows: int
    selected_recent_windows: int
    final_selector_advantage: float
    map_hits_histogram: tuple[tuple[int, int], ...]
    outcomes: tuple[HigherOrderWindowOutcome, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class NextRegimeDecision:
    selected_regime: str
    selector_advantage: float
    blocks: tuple[tuple[int, ...], ...]
    long_training_size: int
    recent_training_size: int


def _mean_ci95(values: Sequence[float]) -> tuple[float, float, float]:
    if not values:
        raise ValueError("é necessário ao menos um valor")
    mean = fmean(values)
    if len(values) == 1:
        return mean, mean, mean
    margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return mean, mean - margin, mean + margin


def _pattern_for_block(draw_set: set[int], block: Sequence[int]) -> int:
    pattern = 0
    for bit, number in enumerate(block):
        if number in draw_set:
            pattern |= 1 << bit
    return pattern


def _adjust_counts(
    counts: list[list[int]],
    draw: tuple[int, ...],
    blocks: Sequence[Sequence[int]],
    delta: int,
) -> None:
    selected = set(draw)
    for block_index, block in enumerate(blocks):
        pattern = _pattern_for_block(selected, block)
        counts[block_index][pattern] += delta
        if counts[block_index][pattern] < 0:
            raise RuntimeError("P15_HIGHER_ORDER_NEGATIVE_PATTERN_COUNT")


def _new_counts() -> list[list[int]]:
    return [[0] * PATTERN_COUNT for _ in range(BLOCK_COUNT)]


def _fit_models(
    *,
    blocks: tuple[tuple[int, ...], ...],
    static_counts: Sequence[Sequence[int]],
    static_n: int,
    recent_counts: Sequence[Sequence[int]],
    recent_n: int,
    prior_strength: float,
) -> tuple[BlockPatternConditionalModel, BlockPatternConditionalModel]:
    long_model = fit_block_pattern_from_counts(
        blocks=blocks,
        pattern_counts=static_counts,
        n=static_n,
        prior_strength=prior_strength,
        source="P15_H104_HIGHER_ORDER_LONG_REGIME",
    )
    recent_model = fit_block_pattern_from_counts(
        blocks=blocks,
        pattern_counts=recent_counts,
        n=recent_n,
        prior_strength=prior_strength,
        source="P15_H104_HIGHER_ORDER_RECENT_REGIME",
    )
    return long_model, recent_model


def walk_forward_higher_order_regime(
    draws: Sequence[Iterable[int]],
    *,
    min_train: int = 100,
    prior_strength: float = 32.0,
    recent_window: int = 180,
    selector_alpha: float = 0.05,
    switch_margin: float = 0.0,
    selector_warmup: int = 30,
    min_successful_windows: int = 30,
) -> HigherOrderRegimeResult:
    """Prequential P15-H104 with higher-order factors and hard regime switching.

    The information-derived block partition is learned once from the initial
    training window and frozen.  Long and recent models are both scored on each
    target.  Which model supplies the single MAP card is decided *before* the
    target from an EWMA of prior loss differences; target information is used
    only after scoring.  This prevents regime selection leakage.
    """

    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train deve ser positivo e menor que o histórico")
    if recent_window <= 0:
        raise ValueError("recent_window deve ser positivo")
    if not 0.0 < selector_alpha <= 1.0:
        raise ValueError("selector_alpha deve estar em (0,1]")
    if selector_warmup < 0:
        raise ValueError("selector_warmup inválido")

    blocks = learn_information_blocks(normalized[:min_train])
    static_counts = pattern_counts_from_draws(normalized[:min_train], blocks)

    recent_seed = normalized[max(0, min_train - recent_window) : min_train]
    recent_queue: deque[tuple[int, ...]] = deque(recent_seed)
    recent_counts = pattern_counts_from_draws(recent_seed, blocks)

    selector_advantage = 0.0  # positive => recent had lower past log-loss
    selector_observations = 0

    outcomes: list[HigherOrderWindowOutcome] = []
    selected_losses: list[float] = []
    selected_skills: list[float] = []
    long_skills: list[float] = []
    recent_skills: list[float] = []
    hits_values: list[int] = []
    histogram: dict[int, int] = {}
    selected_long = 0
    selected_recent = 0

    for target_index in range(min_train, len(normalized)):
        long_model, recent_model = _fit_models(
            blocks=blocks,
            static_counts=static_counts,
            static_n=target_index,
            recent_counts=recent_counts,
            recent_n=len(recent_queue),
            prior_strength=prior_strength,
        )

        can_switch = selector_observations >= selector_warmup
        selected_regime = "RECENT" if can_switch and selector_advantage > switch_margin else "LONG"
        selected_model = recent_model if selected_regime == "RECENT" else long_model
        if selected_regime == "RECENT":
            selected_recent += 1
        else:
            selected_long += 1

        target = normalized[target_index]
        long_loss = -long_model.card_log_probability(target)
        recent_loss = -recent_model.card_log_probability(target)
        selected_loss = recent_loss if selected_regime == "RECENT" else long_loss
        selected_skill = UNIFORM_JOINT_LOG_LOSS - selected_loss
        map_card = selected_model.map_card()
        hits = len(set(map_card).intersection(target))

        selected_losses.append(selected_loss)
        selected_skills.append(selected_skill)
        long_skills.append(UNIFORM_JOINT_LOG_LOSS - long_loss)
        recent_skills.append(UNIFORM_JOINT_LOG_LOSS - recent_loss)
        hits_values.append(hits)
        histogram[hits] = histogram.get(hits, 0) + 1
        outcomes.append(
            HigherOrderWindowOutcome(
                target_index=target_index,
                training_size=target_index,
                selected_regime=selected_regime,
                selector_advantage_before_target=selector_advantage,
                long_joint_log_loss=long_loss,
                recent_joint_log_loss=recent_loss,
                selected_joint_log_loss=selected_loss,
                selected_joint_log_skill_vs_uniform=selected_skill,
                map_card=map_card,
                map_hits=hits,
                exact_15=hits == 15,
            )
        )

        # Update regime evidence only after the frozen target has been scored.
        observed_advantage = long_loss - recent_loss
        selector_advantage = (
            observed_advantage
            if selector_observations == 0
            else (1.0 - selector_alpha) * selector_advantage + selector_alpha * observed_advantage
        )
        selector_observations += 1

        # Advance long state.
        _adjust_counts(static_counts, target, blocks, +1)

        # Advance bounded recent state, evicting only after the target was scored.
        if len(recent_queue) >= recent_window:
            evicted = recent_queue.popleft()
            _adjust_counts(recent_counts, evicted, blocks, -1)
        recent_queue.append(target)
        _adjust_counts(recent_counts, target, blocks, +1)

    mean_skill, ci_low, ci_high = _mean_ci95(selected_skills)
    status = "VALID" if len(outcomes) >= min_successful_windows else "INCONCLUSIVE"
    return HigherOrderRegimeResult(
        model_name="P15_H104_HIGHER_ORDER_BLOCK_REGIME",
        status=status,
        predictive_evidence="NOT_ESTABLISHED",
        predictions=len(outcomes),
        min_train=min_train,
        prior_strength=prior_strength,
        recent_window=recent_window,
        selector_alpha=selector_alpha,
        switch_margin=switch_margin,
        blocks=blocks,
        uniform_joint_log_loss=UNIFORM_JOINT_LOG_LOSS,
        mean_joint_log_loss=fmean(selected_losses),
        mean_joint_log_skill=mean_skill,
        joint_log_skill_ci_low=ci_low,
        joint_log_skill_ci_high=ci_high,
        long_mean_joint_log_skill=fmean(long_skills),
        recent_mean_joint_log_skill=fmean(recent_skills),
        mean_map_hits=fmean(hits_values),
        min_map_hits=min(hits_values),
        max_map_hits=max(hits_values),
        exact_15_hits=sum(1 for hits in hits_values if hits == 15),
        selected_long_windows=selected_long,
        selected_recent_windows=selected_recent,
        final_selector_advantage=selector_advantage,
        map_hits_histogram=tuple(sorted(histogram.items())),
        outcomes=tuple(outcomes),
    )


def fit_next_higher_order_regime(
    draws: Sequence[Iterable[int]],
    *,
    min_train: int = 100,
    prior_strength: float = 32.0,
    recent_window: int = 180,
    selector_alpha: float = 0.05,
    switch_margin: float = 0.0,
    selector_warmup: int = 30,
) -> tuple[BlockPatternConditionalModel, NextRegimeDecision]:
    """Replay the leakage-safe selector and return the model frozen for next draw."""

    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if min_train <= 0 or min_train >= len(normalized):
        raise ValueError("min_train inválido")

    blocks = learn_information_blocks(normalized[:min_train])
    static_counts = pattern_counts_from_draws(normalized[:min_train], blocks)
    recent_seed = normalized[max(0, min_train - recent_window) : min_train]
    recent_queue: deque[tuple[int, ...]] = deque(recent_seed)
    recent_counts = pattern_counts_from_draws(recent_seed, blocks)
    selector_advantage = 0.0
    selector_observations = 0

    for target_index in range(min_train, len(normalized)):
        long_model, recent_model = _fit_models(
            blocks=blocks,
            static_counts=static_counts,
            static_n=target_index,
            recent_counts=recent_counts,
            recent_n=len(recent_queue),
            prior_strength=prior_strength,
        )
        target = normalized[target_index]
        long_loss = -long_model.card_log_probability(target)
        recent_loss = -recent_model.card_log_probability(target)
        observed_advantage = long_loss - recent_loss
        selector_advantage = (
            observed_advantage
            if selector_observations == 0
            else (1.0 - selector_alpha) * selector_advantage + selector_alpha * observed_advantage
        )
        selector_observations += 1

        _adjust_counts(static_counts, target, blocks, +1)
        if len(recent_queue) >= recent_window:
            evicted = recent_queue.popleft()
            _adjust_counts(recent_counts, evicted, blocks, -1)
        recent_queue.append(target)
        _adjust_counts(recent_counts, target, blocks, +1)

    long_model, recent_model = _fit_models(
        blocks=blocks,
        static_counts=static_counts,
        static_n=len(normalized),
        recent_counts=recent_counts,
        recent_n=len(recent_queue),
        prior_strength=prior_strength,
    )
    can_switch = selector_observations >= selector_warmup
    selected_regime = "RECENT" if can_switch and selector_advantage > switch_margin else "LONG"
    selected_model = recent_model if selected_regime == "RECENT" else long_model
    return selected_model, NextRegimeDecision(
        selected_regime=selected_regime,
        selector_advantage=selector_advantage,
        blocks=blocks,
        long_training_size=len(normalized),
        recent_training_size=len(recent_queue),
    )
