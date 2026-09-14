from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass
from statistics import NormalDist, fmean
from typing import Any

from sare_lotofacil.simulation.alternative import simulate_marginal_bias, simulate_temporal_memory
from sare_lotofacil.statistics.inference import marginal_tests, temporal_lag_permutation_tests


@dataclass(frozen=True, slots=True)
class MarginalBiasPower:
    sample_size: int
    target_number: int
    target_probability: float
    alpha: float
    replications: int
    detections: int
    power: float
    power_ci95_low: float
    power_ci95_high: float
    any_family_alerts: int
    mean_target_frequency: float
    seed: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TemporalMemoryAssessment:
    sample_size: int
    memory_probability: float
    retained_count: int
    alpha: float
    temporal_replications: int
    seed: int
    marginal_alert_count: int
    marginal_max_abs_effect: float
    temporal_alert_lags: tuple[int, ...]
    lag1_effect: float
    lag1_adjusted_p: float
    mean_consecutive_repetition: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["temporal_alert_lags"] = list(self.temporal_alert_lags)
        return payload


def _wilson_interval(successes: int, trials: int, confidence: float = 0.95) -> tuple[float, float]:
    if trials <= 0:
        raise ValueError("trials deve ser positivo")
    if not 0 <= successes <= trials:
        raise ValueError("successes fora do intervalo")
    z = NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = (p + z * z / (2.0 * trials)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / trials + z * z / (4.0 * trials * trials)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def measure_marginal_bias_power(
    *,
    sample_size: int,
    target_number: int = 16,
    target_probability: float = 0.72,
    alpha: float = 0.05,
    replications: int = 99,
    seed: int = 20260914,
) -> MarginalBiasPower:
    """Mede potência empírica declarada do teste marginal completo com Holm."""
    if sample_size <= 1:
        raise ValueError("sample_size deve ser maior que 1")
    if replications <= 0:
        raise ValueError("replications deve ser positivo")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha deve estar entre 0 e 1")

    rng = random.Random(seed)
    target_label = f"number_{target_number:02d}"
    detections = 0
    any_family_alerts = 0
    frequencies: list[float] = []

    for _ in range(replications):
        simulation_seed = rng.randrange(0, 2**63)
        simulation = simulate_marginal_bias(
            sample_size,
            target_number=target_number,
            target_probability=target_probability,
            seed=simulation_seed,
        )
        stats = marginal_tests(simulation.draws)
        alerts = [item for item in stats if item.p_holm < alpha]
        if alerts:
            any_family_alerts += 1
        target = next(item for item in stats if item.label == target_label)
        frequencies.append(target.observed)
        if target.p_holm < alpha:
            detections += 1

    power = detections / replications
    low, high = _wilson_interval(detections, replications)
    return MarginalBiasPower(
        sample_size=sample_size,
        target_number=target_number,
        target_probability=target_probability,
        alpha=alpha,
        replications=replications,
        detections=detections,
        power=power,
        power_ci95_low=low,
        power_ci95_high=high,
        any_family_alerts=any_family_alerts,
        mean_target_frequency=fmean(frequencies),
        seed=seed,
    )


def assess_temporal_memory(
    *,
    sample_size: int,
    memory_probability: float = 0.35,
    retained_count: int = 13,
    alpha: float = 0.05,
    lags: tuple[int, ...] = (1, 2, 3, 5, 10),
    temporal_replications: int = 199,
    seed: int = 20260914,
) -> TemporalMemoryAssessment:
    """Avalia uma alternativa temporal controlada e reporta simultaneamente a família marginal.

    A aceitação científica esperada para T18 é evidência temporal detectável sem
    alerta marginal na realização controlada escolhida. Isso não implica que toda
    série dependente terá zero falsos alertas marginais; o resultado é registrado
    com seed e parâmetros para reprodução exata.
    """
    simulation = simulate_temporal_memory(
        sample_size,
        memory_probability=memory_probability,
        retained_count=retained_count,
        seed=seed,
    )
    marginal = marginal_tests(simulation.draws)
    temporal = temporal_lag_permutation_tests(
        simulation.draws,
        lags=lags,
        replications=temporal_replications,
        seed=seed,
    )
    alerts = tuple(item.lag for item in temporal if item.p_holm < alpha)
    lag1 = next(item for item in temporal if item.lag == 1)
    mean_repetition = lag1.observed
    return TemporalMemoryAssessment(
        sample_size=sample_size,
        memory_probability=memory_probability,
        retained_count=retained_count,
        alpha=alpha,
        temporal_replications=temporal_replications,
        seed=seed,
        marginal_alert_count=sum(item.p_holm < alpha for item in marginal),
        marginal_max_abs_effect=max(abs(item.effect) for item in marginal),
        temporal_alert_lags=alerts,
        lag1_effect=lag1.effect,
        lag1_adjusted_p=lag1.p_holm,
        mean_consecutive_repetition=mean_repetition,
    )
