from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.experiments.joint_models import AdditiveConditionalSubsetModel


@dataclass(slots=True)
class ExponentiallyWeightedJointState:
    """Leakage-safe dynamic inclusion state for P15-H102.

    The state is an exponentially discounted sufficient-statistic approximation:
    older contests receive geometrically decreasing weight. It is deliberately
    simple and interpretable. A fixed half-life is part of the predeclared
    model identity; changing it after observing the target invalidates the
    experiment.
    """

    half_life: float
    prior_strength: float = 100.0
    prior_inclusion: float = 0.6
    _weighted_counts: list[float] = field(default_factory=lambda: [0.0] * 25, init=False, repr=False)
    _effective_n: float = field(default=0.0, init=False, repr=False)
    _updates: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.half_life <= 0:
            raise ValueError("half_life deve ser positivo")
        if self.prior_strength <= 0:
            raise ValueError("prior_strength deve ser positivo")
        if not 0.0 < self.prior_inclusion < 1.0:
            raise ValueError("prior_inclusion deve estar em (0, 1)")

    @property
    def decay(self) -> float:
        return math.exp(math.log(0.5) / self.half_life)

    @property
    def updates(self) -> int:
        return self._updates

    @property
    def effective_n(self) -> float:
        return self._effective_n

    def update(self, draw: Iterable[int]) -> None:
        normalized = normalize_numbers(draw)
        decay = self.decay
        self._effective_n *= decay
        for index in range(25):
            self._weighted_counts[index] *= decay
        for number in normalized:
            self._weighted_counts[number - 1] += 1.0
        self._effective_n += 1.0
        self._updates += 1

    def model(self) -> AdditiveConditionalSubsetModel:
        alpha = self.prior_strength * self.prior_inclusion
        beta = self.prior_strength * (1.0 - self.prior_inclusion)
        log_weights: list[float] = []
        for weighted_count in self._weighted_counts:
            posterior_p = (weighted_count + alpha) / (self._effective_n + alpha + beta)
            log_weights.append(math.log(posterior_p) - math.log1p(-posterior_p))
        return AdditiveConditionalSubsetModel(
            tuple(log_weights),
            source=f"P15_H102_EW_HALF_LIFE_{self.half_life:g}",
        )
