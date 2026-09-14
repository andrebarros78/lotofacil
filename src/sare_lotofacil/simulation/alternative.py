from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MarginalRegimeShiftSimulation:
    seed: int
    change_index: int
    target_number: int
    post_probability: float
    draws: tuple[tuple[int, ...], ...]


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
    if not isinstance(count, int) or isinstance(count, bool) or count <= 1:
        raise ValueError("count deve ser inteiro maior que 1")
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
