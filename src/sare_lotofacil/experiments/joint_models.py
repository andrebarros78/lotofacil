from __future__ import annotations

import math
from dataclasses import dataclass
from math import comb
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers

UNIVERSE_SIZE = 25
CARD_SIZE = 15
TOTAL_SIMPLE_CARDS = comb(UNIVERSE_SIZE, CARD_SIZE)
UNIFORM_JOINT_LOG_LOSS = math.log(TOTAL_SIMPLE_CARDS)


def _logaddexp(a: float, b: float) -> float:
    if a == -math.inf:
        return b
    if b == -math.inf:
        return a
    high = max(a, b)
    low = min(a, b)
    return high + math.log1p(math.exp(low - high))


def _log_fixed_cardinality_partition(log_weights: Sequence[float], card_size: int = CARD_SIZE) -> float:
    """Return log(sum(exp(sum selected log-weights))) over all fixed-size subsets.

    This is the elementary-symmetric-polynomial partition function evaluated in
    log space.  It gives an exact normalizer for an additive exponential-family
    distribution conditioned on selecting exactly ``card_size`` numbers.
    """

    if len(log_weights) != UNIVERSE_SIZE:
        raise ValueError(f"são necessários {UNIVERSE_SIZE} pesos")
    if card_size < 0 or card_size > len(log_weights):
        raise ValueError("card_size inválido")

    dp = [-math.inf] * (card_size + 1)
    dp[0] = 0.0
    seen = 0
    for raw_weight in log_weights:
        weight = float(raw_weight)
        if not math.isfinite(weight):
            raise ValueError("todos os pesos devem ser finitos")
        seen += 1
        upper = min(card_size, seen)
        for selected in range(upper, 0, -1):
            dp[selected] = _logaddexp(dp[selected], dp[selected - 1] + weight)
    return dp[card_size]


@dataclass(frozen=True, slots=True)
class JointCardScore:
    card: tuple[int, ...]
    log_probability: float
    log_loss: float
    probability: float


@dataclass(frozen=True, slots=True)
class AdditiveConditionalSubsetModel:
    """Proper joint distribution over the 3,268,760 simple Lotofácil cards.

    For a card S with |S|=15,

        P(S) ∝ exp(sum(h_i for i in S)).

    The cardinality constraint is exact: states with a size other than 15 do not
    exist in the model.  This is intentionally a simple first joint model.  It
    does not claim pairwise or causal structure and must not be promoted on the
    basis of retrospective fit alone.
    """

    log_weights: tuple[float, ...]
    source: str = "UNSPECIFIED"

    def __post_init__(self) -> None:
        if len(self.log_weights) != UNIVERSE_SIZE:
            raise ValueError(f"são necessários {UNIVERSE_SIZE} pesos")
        if not all(math.isfinite(float(value)) for value in self.log_weights):
            raise ValueError("todos os pesos devem ser finitos")

    @property
    def log_partition(self) -> float:
        return _log_fixed_cardinality_partition(self.log_weights, CARD_SIZE)

    def card_log_probability(self, card: Iterable[int]) -> float:
        normalized = normalize_numbers(card)
        numerator = sum(self.log_weights[number - 1] for number in normalized)
        return numerator - self.log_partition

    def score_card(self, card: Iterable[int]) -> JointCardScore:
        normalized = normalize_numbers(card)
        log_probability = self.card_log_probability(normalized)
        return JointCardScore(
            card=normalized,
            log_probability=log_probability,
            log_loss=-log_probability,
            probability=math.exp(log_probability),
        )

    def map_card(self) -> tuple[int, ...]:
        """Return the globally most probable 15-number card for this model.

        For an additive fixed-cardinality model the exact MAP solution is the
        set of the 15 largest log-weights.  Ties are resolved by the smaller
        number, making the result deterministic and auditable.
        """

        ranked = sorted(range(UNIVERSE_SIZE), key=lambda index: (-self.log_weights[index], index))
        return tuple(sorted(index + 1 for index in ranked[:CARD_SIZE]))

    def map_score(self) -> JointCardScore:
        return self.score_card(self.map_card())


def uniform_joint_model() -> AdditiveConditionalSubsetModel:
    return AdditiveConditionalSubsetModel((0.0,) * UNIVERSE_SIZE, source="M0_UNIFORM_JOINT")


def fit_regularized_additive_joint(
    training_draws: Sequence[Iterable[int]],
    *,
    prior_strength: float = 100.0,
    prior_inclusion: float = 0.6,
) -> AdditiveConditionalSubsetModel:
    """Fit a regularized additive joint model from historical inclusions.

    A Beta prior regularizes each number's inclusion propensity.  The posterior
    inclusion estimates are converted to log-odds and then conditioned on the
    structural Lotofácil rule that exactly 15 of 25 numbers are selected.

    The resulting distribution is a coherent joint distribution, but its
    conditional marginals are not asserted to equal the unconditioned Beta
    posterior means.  Predictive value must be established prospectively.
    """

    if prior_strength <= 0:
        raise ValueError("prior_strength deve ser positivo")
    if not 0.0 < prior_inclusion < 1.0:
        raise ValueError("prior_inclusion deve estar em (0, 1)")

    normalized = tuple(normalize_numbers(draw) for draw in training_draws)
    counts = [0] * UNIVERSE_SIZE
    for draw in normalized:
        for number in draw:
            counts[number - 1] += 1

    alpha = prior_strength * prior_inclusion
    beta = prior_strength * (1.0 - prior_inclusion)
    n = len(normalized)
    log_weights: list[float] = []
    for count in counts:
        posterior_p = (count + alpha) / (n + alpha + beta)
        log_weights.append(math.log(posterior_p) - math.log1p(-posterior_p))

    return AdditiveConditionalSubsetModel(
        tuple(log_weights),
        source=f"REGULARIZED_ADDITIVE_JOINT_PRIOR_{prior_strength:g}",
    )


def joint_log_loss(model: AdditiveConditionalSubsetModel, observed_draw: Iterable[int]) -> float:
    return -model.card_log_probability(observed_draw)


def joint_log_skill_vs_uniform(model: AdditiveConditionalSubsetModel, observed_draw: Iterable[int]) -> float:
    """Positive values mean the model assigns more probability than M0 to the observed full card."""

    return UNIFORM_JOINT_LOG_LOSS - joint_log_loss(model, observed_draw)
