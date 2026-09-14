from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers


@dataclass(frozen=True, slots=True)
class RegimeCandidate:
    candidate_index: int
    candidate_label: str | None
    strongest_number: int
    before_frequency: float
    after_frequency: float
    effect: float
    max_abs_z: float


@dataclass(frozen=True, slots=True)
class MarginalRegimeScan:
    statistic: float
    strongest: RegimeCandidate
    candidates: tuple[RegimeCandidate, ...]
    min_segment: int
    candidate_stride: int
    expected_probability: float = 0.6


def scan_marginal_regime_change(
    draws: Sequence[Iterable[int]],
    *,
    candidate_labels: Sequence[str] | None = None,
    min_segment: int = 100,
    candidate_stride: int = 10,
) -> MarginalRegimeScan:
    """Escaneia mudanças marginais em pontos candidatos predefinidos.

    A estatística global é o maior |z| entre as 25 dezenas e todos os pontos
    candidatos. O z usa a variância marginal nula p(1-p)=0,24; dependência entre
    dezenas e multiplicidade temporal são tratadas posteriormente pela calibração
    Monte Carlo do máximo global, não por aproximação de testes independentes.
    """
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    n = len(normalized)
    if min_segment <= 0:
        raise ValueError("min_segment deve ser positivo")
    if candidate_stride <= 0:
        raise ValueError("candidate_stride deve ser positivo")
    if candidate_labels is not None and len(candidate_labels) != n:
        raise ValueError("candidate_labels deve ter o mesmo tamanho de draws")
    if n < 2 * min_segment:
        raise ValueError("amostra insuficiente para o scan de regime")

    candidate_indices = tuple(range(min_segment, n - min_segment + 1, candidate_stride))
    if not candidate_indices:
        raise ValueError("nenhum ponto candidato de regime disponível")
    candidate_set = set(candidate_indices)

    totals = [0] * 25
    for draw in normalized:
        for number in draw:
            totals[number - 1] += 1

    running = [0] * 25
    candidates: list[RegimeCandidate] = []
    global_best: RegimeCandidate | None = None

    for index, draw in enumerate(normalized, start=1):
        for number in draw:
            running[number - 1] += 1
        if index not in candidate_set:
            continue

        se = math.sqrt(0.24 * (1.0 / index + 1.0 / (n - index)))
        local_best: RegimeCandidate | None = None
        label = str(candidate_labels[index]) if candidate_labels is not None and index < n else None

        for zero_index in range(25):
            before = running[zero_index] / index
            after = (totals[zero_index] - running[zero_index]) / (n - index)
            effect = after - before
            z = abs(effect) / se
            candidate = RegimeCandidate(
                candidate_index=index,
                candidate_label=label,
                strongest_number=zero_index + 1,
                before_frequency=before,
                after_frequency=after,
                effect=effect,
                max_abs_z=z,
            )
            if local_best is None or (candidate.max_abs_z, -candidate.strongest_number) > (
                local_best.max_abs_z,
                -local_best.strongest_number,
            ):
                local_best = candidate

        assert local_best is not None
        candidates.append(local_best)
        if global_best is None or (
            local_best.max_abs_z,
            -local_best.candidate_index,
            -local_best.strongest_number,
        ) > (
            global_best.max_abs_z,
            -global_best.candidate_index,
            -global_best.strongest_number,
        ):
            global_best = local_best

    assert global_best is not None
    return MarginalRegimeScan(
        statistic=global_best.max_abs_z,
        strongest=global_best,
        candidates=tuple(candidates),
        min_segment=min_segment,
        candidate_stride=candidate_stride,
    )
