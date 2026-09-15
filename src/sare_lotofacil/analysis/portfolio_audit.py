from __future__ import annotations

import math
import random
from statistics import fmean
from typing import Iterable, Sequence

from sare_lotofacil.experiments.models import exponential_update
from sare_lotofacil.statistics.baseline import uniform_baseline


def _normalize_draw(draw: Iterable[int]) -> frozenset[int]:
    values = frozenset(int(value) for value in draw)
    if len(values) != 15 or any(value < 1 or value > 25 for value in values):
        raise ValueError("PRIMARY_POLICY_AUDIT_REQUIRES_VALID_15_OF_25_DRAWS")
    return values


def _block_bootstrap_mean_interval(
    values: Sequence[float],
    *,
    block_length: int = 20,
    replications: int = 2000,
    seed: int = 2026091515,
) -> tuple[float, float]:
    if not values:
        raise ValueError("BLOCK_BOOTSTRAP_REQUIRES_VALUES")
    if block_length < 1 or block_length > len(values):
        raise ValueError("INVALID_BLOCK_LENGTH")
    if replications < 100:
        raise ValueError("BLOCK_BOOTSTRAP_REQUIRES_AT_LEAST_100_REPLICATIONS")
    rng = random.Random(seed)
    n = len(values)
    starts = range(0, n - block_length + 1)
    means: list[float] = []
    for _ in range(replications):
        sample: list[float] = []
        while len(sample) < n:
            start = rng.choice(starts)
            sample.extend(values[start : start + block_length])
        means.append(fmean(sample[:n]))
    means.sort()
    low_index = max(0, math.floor(0.025 * (replications - 1)))
    high_index = min(replications - 1, math.ceil(0.975 * (replications - 1)))
    return means[low_index], means[high_index]


def run_primary_tiebreak_audit(
    draws: Sequence[Iterable[int]],
    *,
    evaluation_start: int | None = None,
) -> dict[str, object]:
    """Mede o valor incremental do M2 apenas onde M1 empata no corte de 15.

    O comparador neutro não escolhe um cartão alternativo arbitrário. Ele calcula
    a expectativa exata de acertos ao selecionar uniformemente os slots restantes
    dentro do grupo empatado pelo M1. Assim, a diferença observada mede apenas o
    desempate M2, não a parte fixa do cartão.
    """
    normalized = tuple(_normalize_draw(draw) for draw in draws)
    total = len(normalized)
    if total < 300:
        raise ValueError("PRIMARY_POLICY_AUDIT_REQUIRES_AT_LEAST_300_DRAWS")
    start = evaluation_start if evaluation_start is not None else (total * 80) // 100
    if start < 100 or total - start < 30:
        raise ValueError("PRIMARY_POLICY_AUDIT_REQUIRES_TRAINING_AND_EVALUATION_WINDOWS")

    counts = [0] * 25
    secondary = uniform_baseline()
    for draw in normalized[:start]:
        for number in draw:
            counts[number - 1] += 1
        secondary = exponential_update(secondary, draw, alpha=0.05)

    hit_deltas: list[float] = []
    m2_hits: list[int] = []
    neutral_expected_hits: list[float] = []
    tie_group_sizes: list[int] = []
    slots_list: list[int] = []
    windows_with_boundary_tie = 0
    windows_where_m2_changes_choice = 0

    for target_index in range(start, total):
        target = normalized[target_index]
        ordered_counts = sorted(counts, reverse=True)
        cutoff = ordered_counts[14]
        fixed = {number for number in range(1, 26) if counts[number - 1] > cutoff}
        tied = [number for number in range(1, 26) if counts[number - 1] == cutoff]
        slots = 15 - len(fixed)
        if slots < 0 or slots > len(tied):
            raise RuntimeError("PRIMARY_POLICY_AUDIT_INVALID_BOUNDARY")

        selected_from_tie = sorted(tied, key=lambda number: (-secondary[number - 1], number))[:slots]
        m2_card = fixed | set(selected_from_tie)
        if len(m2_card) != 15:
            raise RuntimeError("PRIMARY_POLICY_AUDIT_INVALID_CARD_SIZE")

        fixed_hits = len(fixed & target)
        tied_hits = len(set(tied) & target)
        expected_tie_hits = 0.0 if not tied else slots * tied_hits / len(tied)
        neutral_hits = fixed_hits + expected_tie_hits
        observed_m2_hits = len(m2_card & target)
        delta = observed_m2_hits - neutral_hits

        hit_deltas.append(delta)
        m2_hits.append(observed_m2_hits)
        neutral_expected_hits.append(neutral_hits)
        tie_group_sizes.append(len(tied))
        slots_list.append(slots)
        if len(tied) > slots:
            windows_with_boundary_tie += 1
            if 0 < slots < len(tied):
                windows_where_m2_changes_choice += 1

        for number in target:
            counts[number - 1] += 1
        secondary = exponential_update(secondary, target, alpha=0.05)

    mean_delta = fmean(hit_deltas)
    block_length = min(20, max(1, len(hit_deltas) // 10))
    ci_low, ci_high = _block_bootstrap_mean_interval(
        hit_deltas,
        block_length=block_length,
        replications=2000,
    )
    if ci_low > 0.0:
        conclusion = "M2_TIEBREAK_RETROSPECTIVE_POSITIVE_SIGNAL"
    elif ci_high < 0.0:
        conclusion = "M2_TIEBREAK_RETROSPECTIVE_NEGATIVE_SIGNAL"
    else:
        conclusion = "M2_TIEBREAK_NO_DEMONSTRATED_INCREMENTAL_VALUE"

    return {
        "protocol": "RETROSPECTIVE_PRIMARY_TIEBREAK_HOLDOUT",
        "evaluation_start_index": start,
        "evaluation_windows": len(hit_deltas),
        "m1_boundary_basis": "cumulative_frequency_order_lambda_invariant",
        "m2_alpha": 0.05,
        "m2_mean_hits": fmean(m2_hits),
        "neutral_expected_mean_hits": fmean(neutral_expected_hits),
        "mean_hit_delta_m2_minus_neutral": mean_delta,
        "block_bootstrap_ci_low": ci_low,
        "block_bootstrap_ci_high": ci_high,
        "block_length": block_length,
        "bootstrap_replications": 2000,
        "windows_with_boundary_tie": windows_with_boundary_tie,
        "windows_where_m2_changes_choice": windows_where_m2_changes_choice,
        "mean_boundary_tie_group_size": fmean(tie_group_sizes),
        "mean_slots_selected_from_tie": fmean(slots_list),
        "scientific_conclusion": conclusion,
        "predictive_evidence": "NOT_ESTABLISHED",
        "limitations": [
            "A avaliação usa histórico revisado e é retrospectiva.",
            "O bootstrap em blocos é análise de sensibilidade para dependência serial; o tamanho de bloco 20 é fixado por este protocolo e não foi otimizado após o resultado.",
            "Mesmo um sinal positivo não autorizaria promoção sem confirmação prospectiva.",
        ],
    }
