from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from sare_lotofacil.domain.masks import normalize_numbers, numbers_to_mask


@dataclass(frozen=True, slots=True)
class ContestRecord:
    contest_id: int
    draw_date: date
    numbers: tuple[int, ...]
    mask: int


def validate_contest(contest_id: int, draw_date: date, numbers: Iterable[int]) -> ContestRecord:
    if not isinstance(contest_id, int) or isinstance(contest_id, bool) or contest_id <= 0:
        raise ValueError("contest_id deve ser inteiro positivo")
    if not isinstance(draw_date, date):
        raise ValueError("draw_date deve ser date")
    normalized = normalize_numbers(numbers)
    return ContestRecord(
        contest_id=contest_id,
        draw_date=draw_date,
        numbers=normalized,
        mask=numbers_to_mask(normalized),
    )
