from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarginalBiasSimulation:
    seed: int
    target_number: int
    target_probability: float
    draws: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class TemporalMemorySimulation:
    seed: int
    memory_probability: float
    retained_count: int
    draws: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class MarginalRegimeShiftSimulation:
    seed: int
    change_index: int
    target_number: int
    post_probability: float
    draws: tuple[tuple[int, ...], ...]


def _validate_count(count: int) -> None:
    if not isinstance(count, int) or isinstance(count, bool) or count <= 1:
        raise ValueError("count deve ser inteiro maior que 1")


def simulate_marginal_bias(
    count: int,
    *,
    target_number: int = 16,
    target_probability: float = 0.72,
    seed: int,
) -> MarginalBiasSimulation:
    """Gera viés marginal estacionário preservando exatamente 15 dezenas por concurso.

    A presença da dezena alvo segue ``target_probability``. Condicionado à presença,
    escolhem-se 14 das outras 24 dezenas; condicionado à ausência, escolhem-se 15
    das outras 24. O gerador serve exclusivamente para medir potência declarada.
    """
    _validate_count(count)
    if not 1 <= target_number <= 25:
        raise ValueError("target_number deve estar entre 1 e 25")
    if not 0.0 <= target_probability <= 1.0:
        raise ValueError("target_probability deve estar entre 0 e 1")

    rng = random.Random(seed)
    universe = tuple(range(1, 26))
    others = tuple(number for number in universe if number != target_number)
    draws: list[tuple[int, ...]] = []
    for _ in range(count):
        if rng.random() < target_probability:
            draw = tuple(sorted((target_number, *rng.sample(others, 14))))
        else:
            draw = tuple(sorted(rng.sample(others, 15)))
        draws.append(draw)
    return MarginalBiasSimulation(
        seed=seed,
        target_number=target_number,
        target_probability=target_probability,
        draws=tuple(draws),
    )


def simulate_temporal_memory(
    count: int,
    *,
    memory_probability: float = 0.35,
    retained_count: int = 13,
    seed: int,
) -> TemporalMemorySimulation:
    """Gera dependência temporal sem escolher uma dezena privilegiada.

    O primeiro concurso é uniforme 15-de-25. Em cada transição, com probabilidade
    ``memory_probability``, o novo concurso retém exatamente ``retained_count``
    dezenas do anterior e completa as demais a partir do complemento. Caso contrário,
    um novo concurso uniforme é sorteado. O kernel é simétrico por permutação das
    25 dezenas, preservando a distribuição marginal uniforme em regime estacionário,
    enquanto altera deliberadamente a dependência entre concursos.
    """
    _validate_count(count)
    if not 0.0 <= memory_probability <= 1.0:
        raise ValueError("memory_probability deve estar entre 0 e 1")
    if not isinstance(retained_count, int) or isinstance(retained_count, bool):
        raise ValueError("retained_count deve ser inteiro")
    if not 5 <= retained_count <= 15:
        raise ValueError("retained_count deve estar entre 5 e 15")

    rng = random.Random(seed)
    universe = tuple(range(1, 26))
    first = tuple(sorted(rng.sample(universe, 15)))
    draws: list[tuple[int, ...]] = [first]

    for _ in range(1, count):
        previous = draws[-1]
        if rng.random() < memory_probability:
            previous_set = set(previous)
            complement = tuple(number for number in universe if number not in previous_set)
            retained = rng.sample(previous, retained_count)
            newcomers = rng.sample(complement, 15 - retained_count)
            draw = tuple(sorted((*retained, *newcomers)))
        else:
            draw = tuple(sorted(rng.sample(universe, 15)))
        draws.append(draw)

    return TemporalMemorySimulation(
        seed=seed,
        memory_probability=memory_probability,
        retained_count=retained_count,
        draws=tuple(draws),
    )


def simulate_marginal_regime_shift(
    count: int,
    *,
    change_index: int,
    target_number: int = 16,
    post_probability: float = 0.85,
    seed: int,
) -> MarginalRegimeShiftSimulation:
    """Gera alternativa controlada com mudança marginal conhecida.

    Antes de ``change_index`` os concursos são uniformes 15-de-25. Depois da
    mudança, a presença de ``target_number`` segue ``post_probability``; os
    demais números são amostrados uniformemente sem reposição condicionados à
    presença/ausência do alvo. O gerador existe apenas para medir poder/sensibilidade.
    """
    _validate_count(count)
    if not 1 <= change_index < count:
        raise ValueError("change_index deve separar dois segmentos não vazios")
    if not 1 <= target_number <= 25:
        raise ValueError("target_number deve estar entre 1 e 25")
    if not 0.0 <= post_probability <= 1.0:
        raise ValueError("post_probability deve estar entre 0 e 1")

    rng = random.Random(seed)
    universe = tuple(range(1, 26))
    others = tuple(number for number in universe if number != target_number)
    draws: list[tuple[int, ...]] = []

    for index in range(count):
        if index < change_index:
            draw = tuple(sorted(rng.sample(universe, 15)))
        elif rng.random() < post_probability:
            draw = tuple(sorted((target_number, *rng.sample(others, 14))))
        else:
            draw = tuple(sorted(rng.sample(others, 15)))
        draws.append(draw)

    return MarginalRegimeShiftSimulation(
        seed=seed,
        change_index=change_index,
        target_number=target_number,
        post_probability=post_probability,
        draws=tuple(draws),
    )
