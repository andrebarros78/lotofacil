from __future__ import annotations

from collections.abc import Iterable

from .rules import DEFAULT_RULES


def normalize_numbers(numbers: Iterable[int], *, expected_size: int = 15) -> tuple[int, ...]:
    normalized = tuple(sorted(numbers))
    if len(normalized) != expected_size:
        raise ValueError(f"esperadas {expected_size} dezenas, recebidas {len(normalized)}")
    if len(set(normalized)) != len(normalized):
        raise ValueError("dezenas repetidas não são permitidas")
    if normalized and (normalized[0] < 1 or normalized[-1] > DEFAULT_RULES.universe_size):
        raise ValueError("dezenas devem estar entre 1 e 25")
    return normalized


def numbers_to_mask(numbers: Iterable[int], *, expected_size: int = 15) -> int:
    normalized = normalize_numbers(numbers, expected_size=expected_size)
    mask = 0
    for number in normalized:
        mask |= 1 << (number - 1)
    return mask


def mask_to_numbers(mask: int) -> tuple[int, ...]:
    if mask < 0 or mask >= (1 << DEFAULT_RULES.universe_size):
        raise ValueError("máscara fora do universo de 25 bits")
    return tuple(index + 1 for index in range(DEFAULT_RULES.universe_size) if mask & (1 << index))


def intersection_hits(left_mask: int, right_mask: int) -> int:
    return (left_mask & right_mask).bit_count()
