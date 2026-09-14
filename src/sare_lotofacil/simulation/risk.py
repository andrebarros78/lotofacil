from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True, slots=True)
class BinaryRiskEstimate:
    events: int
    replications: int
    probability: float
    confidence: float
    interval_low: float
    interval_high: float
    monte_carlo_resolution: float
    interval_method: str = "WILSON_SCORE"


def summarize_binary_risk(
    events: int,
    replications: int,
    *,
    confidence: float = 0.95,
) -> BinaryRiskEstimate:
    """Resume um evento binário de risco sem confundir zero observado com risco zero.

    O intervalo de Wilson é usado para evitar o legado em que zero eventos
    produziam intervalo [0, 0]. ``replications=0`` é erro de entrada: não existe
    amostra a partir da qual estimar risco ou resolução Monte Carlo.
    """
    if isinstance(replications, bool) or not isinstance(replications, int) or replications <= 0:
        raise ValueError("replications deve ser inteiro positivo")
    if isinstance(events, bool) or not isinstance(events, int) or not 0 <= events <= replications:
        raise ValueError("events deve ser inteiro entre 0 e replications")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence deve estar entre 0 e 1")

    n = replications
    p_hat = events / n
    z = NormalDist().inv_cdf(0.5 + confidence / 2.0)
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p_hat + z2 / (2.0 * n)) / denominator
    radius = (
        z
        * math.sqrt((p_hat * (1.0 - p_hat) / n) + (z2 / (4.0 * n * n)))
        / denominator
    )
    low = max(0.0, center - radius)
    high = min(1.0, center + radius)

    return BinaryRiskEstimate(
        events=events,
        replications=replications,
        probability=p_hat,
        confidence=confidence,
        interval_low=low,
        interval_high=high,
        monte_carlo_resolution=1.0 / n,
    )
