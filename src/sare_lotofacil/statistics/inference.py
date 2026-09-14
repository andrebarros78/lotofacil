from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import intersection_hits, numbers_to_mask, normalize_numbers
from sare_lotofacil.statistics.descriptive import marginal_uniformity, pair_counts, repetition_counts
from sare_lotofacil.statistics.multiplicity import holm_adjust


@dataclass(frozen=True, slots=True)
class HypothesisStat:
    label: str
    observed: float
    expected: float
    effect: float
    p_value: float
    p_holm: float


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    statistic: float
    null_expected: float
    p_value: float
    replications: int
    seed: int


@dataclass(frozen=True, slots=True)
class TemporalLagStat:
    lag: int
    observed: float
    expected: float
    effect: float
    p_value: float
    p_holm: float
    replications: int
    seed: int


def _binomial_logpmf(k: int, n: int, p: float) -> float:
    if k < 0 or k > n:
        return float("-inf")
    if p == 0.0:
        return 0.0 if k == 0 else float("-inf")
    if p == 1.0:
        return 0.0 if k == n else float("-inf")
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def binomial_two_sided_pvalue(k: int, n: int, p: float) -> float:
    if n <= 0:
        raise ValueError("n deve ser positivo")
    if not 0.0 <= p <= 1.0:
        raise ValueError("p deve estar entre 0 e 1")
    if not 0 <= k <= n:
        raise ValueError("k deve estar entre 0 e n")
    observed_logp = _binomial_logpmf(k, n, p)
    total = 0.0
    tolerance = 1e-12
    for candidate in range(n + 1):
        candidate_logp = _binomial_logpmf(candidate, n, p)
        if candidate_logp <= observed_logp + tolerance:
            total += math.exp(candidate_logp)
    return min(1.0, total)


def marginal_tests(draws: Sequence[Iterable[int]]) -> tuple[HypothesisStat, ...]:
    stats = marginal_uniformity(draws)
    n = len(draws)
    raw = tuple(binomial_two_sided_pvalue(stat.observed, n, 0.6) for stat in stats)
    adjusted = holm_adjust(raw)
    return tuple(
        HypothesisStat(
            label=f"number_{stat.number:02d}",
            observed=stat.frequency,
            expected=0.6,
            effect=stat.frequency - 0.6,
            p_value=p_value,
            p_holm=p_holm,
        )
        for stat, p_value, p_holm in zip(stats, raw, adjusted)
    )


def pair_tests(draws: Sequence[Iterable[int]]) -> tuple[HypothesisStat, ...]:
    if not draws:
        raise ValueError("é necessário pelo menos um concurso")
    counts = pair_counts(draws)
    n = len(draws)
    ordered_pairs = tuple(sorted(counts))
    raw = tuple(binomial_two_sided_pvalue(counts[pair], n, 0.35) for pair in ordered_pairs)
    adjusted = holm_adjust(raw)
    return tuple(
        HypothesisStat(
            label=f"pair_{left:02d}_{right:02d}",
            observed=counts[(left, right)] / n,
            expected=0.35,
            effect=counts[(left, right)] / n - 0.35,
            p_value=p_value,
            p_holm=p_holm,
        )
        for (left, right), p_value, p_holm in zip(ordered_pairs, raw, adjusted)
    )


def temporal_repetition_monte_carlo(
    draws: Sequence[Iterable[int]], *, replications: int = 999, seed: int = 0
) -> MonteCarloResult:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if len(normalized) < 2:
        raise ValueError("são necessários ao menos dois concursos")
    if replications <= 0:
        raise ValueError("replications deve ser positivo")
    observed = fmean(repetition_counts(normalized))
    deviation = abs(observed - 9.0)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(replications):
        masks = [numbers_to_mask(rng.sample(range(1, 26), 15)) for _ in range(len(normalized))]
        simulated = fmean(intersection_hits(left, right) for left, right in zip(masks, masks[1:]))
        if abs(simulated - 9.0) >= deviation - 1e-15:
            extreme += 1
    return MonteCarloResult(
        statistic=observed,
        null_expected=9.0,
        p_value=(extreme + 1) / (replications + 1),
        replications=replications,
        seed=seed,
    )


def temporal_lag_permutation_tests(
    draws: Sequence[Iterable[int]],
    *,
    lags: Sequence[int] = (1, 2, 3, 5, 10),
    replications: int = 999,
    seed: int = 0,
) -> tuple[TemporalLagStat, ...]:
    """Testa repetição temporal em lags predefinidos por permutação de concursos completos.

    A permutação opera sobre linhas completas, preservando cada concurso e sua
    estrutura intraconcurso. A família de lags é corrigida por Holm.
    """
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if len(normalized) < 2:
        raise ValueError("são necessários ao menos dois concursos")
    if replications <= 0:
        raise ValueError("replications deve ser positivo")
    ordered_lags = tuple(dict.fromkeys(int(lag) for lag in lags))
    if not ordered_lags:
        raise ValueError("é necessário ao menos um lag")
    if any(lag <= 0 or lag >= len(normalized) for lag in ordered_lags):
        raise ValueError("lags devem estar entre 1 e n-1")

    masks = tuple(numbers_to_mask(draw) for draw in normalized)

    def lag_mean(sequence: Sequence[int], lag: int) -> float:
        return fmean(
            intersection_hits(sequence[index], sequence[index + lag])
            for index in range(len(sequence) - lag)
        )

    observed = tuple(lag_mean(masks, lag) for lag in ordered_lags)
    simulated_by_lag: list[list[float]] = [[] for _ in ordered_lags]
    rng = random.Random(seed)
    shuffled = list(masks)
    for _ in range(replications):
        shuffled[:] = masks
        rng.shuffle(shuffled)
        for index, lag in enumerate(ordered_lags):
            simulated_by_lag[index].append(lag_mean(shuffled, lag))

    expected = tuple(fmean(values) for values in simulated_by_lag)
    raw: list[float] = []
    for observed_value, expected_value, simulated in zip(observed, expected, simulated_by_lag):
        deviation = abs(observed_value - expected_value)
        extreme = sum(abs(value - expected_value) >= deviation - 1e-15 for value in simulated)
        raw.append((extreme + 1) / (replications + 1))
    adjusted = holm_adjust(raw)

    return tuple(
        TemporalLagStat(
            lag=lag,
            observed=observed_value,
            expected=expected_value,
            effect=observed_value - expected_value,
            p_value=p_value,
            p_holm=p_holm,
            replications=replications,
            seed=seed,
        )
        for lag, observed_value, expected_value, p_value, p_holm in zip(
            ordered_lags, observed, expected, raw, adjusted
        )
    )


def fixed_split_frequency_shift(
    draws: Sequence[Iterable[int]], *, split_index: int
) -> tuple[HypothesisStat, ...]:
    normalized = tuple(normalize_numbers(draw) for draw in draws)
    if not 1 <= split_index < len(normalized):
        raise ValueError("split_index deve dividir o histórico em duas partes não vazias")
    before = marginal_uniformity(normalized[:split_index])
    after = marginal_uniformity(normalized[split_index:])
    n1 = split_index
    n2 = len(normalized) - split_index
    raw: list[float] = []
    effects: list[float] = []
    for first, second in zip(before, after):
        pooled = (first.observed + second.observed) / (n1 + n2)
        se = math.sqrt(pooled * (1.0 - pooled) * (1.0 / n1 + 1.0 / n2)) if 0.0 < pooled < 1.0 else 0.0
        effect = second.frequency - first.frequency
        z = effect / se if se else 0.0
        p_value = math.erfc(abs(z) / math.sqrt(2.0))
        raw.append(p_value)
        effects.append(effect)
    adjusted = holm_adjust(raw)
    return tuple(
        HypothesisStat(
            label=f"number_{index:02d}_split",
            observed=after[index - 1].frequency,
            expected=before[index - 1].frequency,
            effect=effects[index - 1],
            p_value=raw[index - 1],
            p_holm=adjusted[index - 1],
        )
        for index in range(1, 26)
    )
