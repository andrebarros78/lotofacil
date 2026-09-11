from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NullSimulation:
    seed: int
    draws: tuple[tuple[int, ...], ...]


def simulate_uniform_draws(count: int, *, seed: int) -> NullSimulation:
    if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
        raise ValueError("count deve ser inteiro positivo")
    rng = random.Random(seed)
    draws = tuple(tuple(sorted(rng.sample(range(1, 26), 15))) for _ in range(count))
    return NullSimulation(seed=seed, draws=draws)
