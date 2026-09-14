from __future__ import annotations

from dataclasses import dataclass

from sare_lotofacil.simulation.alternative import (
    simulate_marginal_bias,
    simulate_temporal_memory,
)
from sare_lotofacil.statistics.inference import (
    marginal_tests,
    temporal_lag_permutation_tests,
)


@dataclass(frozen=True, slots=True)
class MarginalBiasPowerResult:
    replications: int
    draw_count: int
    target_number: int
    target_probability: float
    alpha: float
    detections: int
    power: float
    mean_target_effect: float
    base_seed: int


@dataclass(frozen=True, slots=True)
class TemporalMemorySeparationResult:
    draw_count: int
    memory_probability: float
    retained_count: int
    alpha: float
    marginal_alerts: int
    temporal_alerts: int
    lag1_effect: float
    lag1_p_holm: float
    max_abs_marginal_effect: float
    seed: int
    permutation_replications: int


def measure_marginal_bias_power(
    *,
    replications: int = 30,
    draw_count: int = 400,
    target_number: int = 16,
    target_probability: float = 0.72,
    alpha: float = 0.05,
    base_seed: int = 20260914,
) -> MarginalBiasPowerResult:
    """Mede potência empírica do teste marginal sob alternativa controlada.

    Cada replicação gera uma série independente com probabilidade marginal conhecida
    para uma única dezena e aplica a família canônica de 25 testes com correção Holm.
    A detecção só conta quando a dezena-alvo é rejeitada no sentido esperado.
    """
    if replications <= 0:
        raise ValueError("replications deve ser positivo")
    if draw_count <= 1:
        raise ValueError("draw_count deve ser maior que 1")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha deve estar entre 0 e 1")

    detections = 0
    effects: list[float] = []
    label = f"number_{target_number:02d}"

    for offset in range(replications):
        simulation = simulate_marginal_bias(
            draw_count,
            target_number=target_number,
            target_probability=target_probability,
            seed=base_seed + offset,
        )
        stats = marginal_tests(simulation.draws)
        target = next(stat for stat in stats if stat.label == label)
        effects.append(target.effect)
        if target.p_holm < alpha and target.effect > 0.0:
            detections += 1

    return MarginalBiasPowerResult(
        replications=replications,
        draw_count=draw_count,
        target_number=target_number,
        target_probability=target_probability,
        alpha=alpha,
        detections=detections,
        power=detections / replications,
        mean_target_effect=sum(effects) / len(effects),
        base_seed=base_seed,
    )


def assess_temporal_memory_separation(
    *,
    draw_count: int = 600,
    memory_probability: float = 0.30,
    retained_count: int = 12,
    alpha: float = 0.05,
    seed: int = 20260914,
    permutation_replications: int = 399,
) -> TemporalMemorySeparationResult:
    """Avalia se memória temporal é detectada sem rejeição marginal espúria.

    O gerador temporal é simétrico entre as 25 dezenas. A validação aplica a família
    marginal canônica e, separadamente, o teste temporal por permutação de concursos
    completos. O resultado não é uma prova universal de separabilidade; é uma prova
    controlada, reproduzível, para a alternativa T18 predefinida.
    """
    if draw_count <= 10:
        raise ValueError("draw_count deve ser maior que 10")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha deve estar entre 0 e 1")
    if permutation_replications <= 0:
        raise ValueError("permutation_replications deve ser positivo")

    simulation = simulate_temporal_memory(
        draw_count,
        memory_probability=memory_probability,
        retained_count=retained_count,
        seed=seed,
    )
    marginal = marginal_tests(simulation.draws)
    temporal = temporal_lag_permutation_tests(
        simulation.draws,
        lags=(1, 2, 3, 5, 10),
        replications=permutation_replications,
        seed=seed + 100_000,
    )
    lag1 = next(stat for stat in temporal if stat.lag == 1)

    return TemporalMemorySeparationResult(
        draw_count=draw_count,
        memory_probability=memory_probability,
        retained_count=retained_count,
        alpha=alpha,
        marginal_alerts=sum(stat.p_holm < alpha for stat in marginal),
        temporal_alerts=sum(stat.p_holm < alpha for stat in temporal),
        lag1_effect=lag1.effect,
        lag1_p_holm=lag1.p_holm,
        max_abs_marginal_effect=max(abs(stat.effect) for stat in marginal),
        seed=seed,
        permutation_replications=permutation_replications,
    )
