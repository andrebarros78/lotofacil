from __future__ import annotations

from collections.abc import Sequence


def holm_adjust(p_values: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in p_values)
    if any(value < 0.0 or value > 1.0 for value in values):
        raise ValueError("p-values devem estar entre 0 e 1")
    n = len(values)
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    adjusted = [0.0] * n
    running_max = 0.0
    for rank, (original_index, value) in enumerate(ordered):
        candidate = min(1.0, (n - rank) * value)
        running_max = max(running_max, candidate)
        adjusted[original_index] = running_max
    return tuple(adjusted)
