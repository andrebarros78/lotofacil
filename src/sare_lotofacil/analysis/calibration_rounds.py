from __future__ import annotations

import math
from collections import Counter
from statistics import fmean, median
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER

M1_LAMBDA_GRID = (25.0, 50.0, 100.0, 200.0, 400.0)
M2_ALPHA_GRID = (0.005, 0.01, 0.02, 0.05, 0.10)
DEFAULT_ROUNDS = 20
ECE_BINS = 10


def _normalize_draws(draws: Sequence[Iterable[int]]) -> tuple[tuple[int, ...], ...]:
    return tuple(normalize_numbers(draw) for draw in draws)


def _target_vector(draw: Iterable[int]) -> tuple[float, ...]:
    observed = set(draw)
    return tuple(1.0 if number in observed else 0.0 for number in range(1, 26))


def _brier(probabilities: Sequence[float], draw: Iterable[int]) -> float:
    target = _target_vector(draw)
    return sum((float(probability) - observed) ** 2 for probability, observed in zip(probabilities, target)) / 25.0


def _m1_probabilities(counts: Sequence[int], n: int, lam: float) -> tuple[float, ...]:
    denominator = n + lam
    if denominator <= 0:
        raise ValueError("M1 denominator must be positive")
    return tuple((count + 0.6 * lam) / denominator for count in counts)


def _m2_update(probabilities: Sequence[float], draw: Iterable[int], alpha: float) -> tuple[float, ...]:
    observed = set(draw)
    return tuple(
        (1.0 - alpha) * float(probability) + alpha * (1.0 if number in observed else 0.0)
        for number, probability in enumerate(probabilities, start=1)
    )


def _m1_mean_brier(draws: tuple[tuple[int, ...], ...], start: int, stop: int, lam: float) -> float:
    counts = [0] * 25
    for draw in draws[:start]:
        for number in draw:
            counts[number - 1] += 1
    scores: list[float] = []
    for target_index in range(start, stop):
        probabilities = _m1_probabilities(counts, target_index, lam)
        target = draws[target_index]
        scores.append(_brier(probabilities, target))
        for number in target:
            counts[number - 1] += 1
    return fmean(scores)


def _m2_mean_brier(draws: tuple[tuple[int, ...], ...], start: int, stop: int, alpha: float) -> float:
    probabilities: tuple[float, ...] = (0.6,) * 25
    for draw in draws[:start]:
        probabilities = _m2_update(probabilities, draw, alpha)
    scores: list[float] = []
    for target_index in range(start, stop):
        target = draws[target_index]
        scores.append(_brier(probabilities, target))
        probabilities = _m2_update(probabilities, target, alpha)
    return fmean(scores)


def _error_metrics(
    draws: tuple[tuple[int, ...], ...],
    *,
    start: int,
    stop: int,
    family: str,
    parameter: float,
) -> dict[str, float | int]:
    if not 0 <= start < stop <= len(draws):
        raise ValueError("invalid evaluation interval")

    brier_sum = 0.0
    absolute_error_sum = 0.0
    observations = 0
    bin_count = [0] * ECE_BINS
    bin_probability_sum = [0.0] * ECE_BINS
    bin_observed_sum = [0.0] * ECE_BINS

    if family == "M1":
        counts = [0] * 25
        for draw in draws[:start]:
            for number in draw:
                counts[number - 1] += 1

        def predict(index: int) -> tuple[float, ...]:
            return _m1_probabilities(counts, index, parameter)

        def update(draw: tuple[int, ...]) -> None:
            for number in draw:
                counts[number - 1] += 1

    elif family == "M2":
        probabilities: tuple[float, ...] = (0.6,) * 25
        for draw in draws[:start]:
            probabilities = _m2_update(probabilities, draw, parameter)

        def predict(index: int) -> tuple[float, ...]:
            del index
            return probabilities

        def update(draw: tuple[int, ...]) -> None:
            nonlocal probabilities
            probabilities = _m2_update(probabilities, draw, parameter)

    else:
        raise ValueError(f"unknown family: {family}")

    for target_index in range(start, stop):
        target = draws[target_index]
        target_vector = _target_vector(target)
        predicted = predict(target_index)
        for probability, observed in zip(predicted, target_vector):
            probability = min(max(float(probability), 0.0), 1.0)
            error = probability - observed
            brier_sum += error * error
            absolute_error_sum += abs(error)
            bucket = min(int(probability * ECE_BINS), ECE_BINS - 1)
            bin_count[bucket] += 1
            bin_probability_sum[bucket] += probability
            bin_observed_sum[bucket] += observed
            observations += 1
        update(target)

    mean_brier = brier_sum / observations
    mae = absolute_error_sum / observations
    rmse = math.sqrt(mean_brier)
    ece = 0.0
    for count, probability_sum, observed_sum in zip(bin_count, bin_probability_sum, bin_observed_sum):
        if count == 0:
            continue
        mean_probability = probability_sum / count
        observed_rate = observed_sum / count
        ece += (count / observations) * abs(mean_probability - observed_rate)

    return {
        "windows": stop - start,
        "observations": observations,
        "brier": mean_brier,
        "delta_brier_vs_m0": UNIFORM_BRIER - mean_brier,
        "mae": mae,
        "rmse": rmse,
        "calibration_ece_10": ece,
    }


def _prefix_lengths(total: int, rounds: int) -> tuple[int, ...]:
    if rounds <= 0:
        raise ValueError("rounds must be positive")
    minimum = max(600, total // 2)
    if total < minimum or minimum < 300:
        raise ValueError("20-round calibration requires at least 600 draws")
    if rounds == 1:
        return (total,)
    points = []
    span = total - minimum
    for index in range(rounds):
        point = minimum + round(span * index / (rounds - 1))
        if points and point <= points[-1]:
            point = points[-1] + 1
        points.append(min(point, total))
    if len(set(points)) != rounds or points[-1] != total:
        raise ValueError("history is too short for distinct calibration rounds")
    return tuple(points)


def run_calibration_error_rounds(
    draws: Sequence[Iterable[int]],
    *,
    rounds: int = DEFAULT_ROUNDS,
) -> dict[str, object]:
    """Executa rodadas temporais 60/20/20 sem usar o holdout para escolher parâmetros.

    As rodadas são prefixes temporais ancorados, portanto se sobrepõem e servem como
    diagnóstico de estabilidade retrospectiva. Elas não são replicações independentes
    e não promovem evidência preditiva.
    """
    normalized = _normalize_draws(draws)
    prefixes = _prefix_lengths(len(normalized), rounds)
    round_payloads: list[dict[str, object]] = []

    for round_index, prefix_len in enumerate(prefixes, start=1):
        train_end = max(100, (prefix_len * 60) // 100)
        calibration_end = max(train_end + 30, (prefix_len * 80) // 100)
        if calibration_end >= prefix_len or prefix_len - calibration_end < 30:
            raise ValueError("round requires at least 30 calibration and 30 holdout windows")

        candidates: list[dict[str, object]] = []
        for lam in M1_LAMBDA_GRID:
            score = _m1_mean_brier(normalized, train_end, calibration_end, lam)
            candidates.append(
                {
                    "family": "M1",
                    "parameter": lam,
                    "calibration_brier": score,
                    "calibration_delta_brier_vs_m0": UNIFORM_BRIER - score,
                }
            )
        for alpha in M2_ALPHA_GRID:
            score = _m2_mean_brier(normalized, train_end, calibration_end, alpha)
            candidates.append(
                {
                    "family": "M2",
                    "parameter": alpha,
                    "calibration_brier": score,
                    "calibration_delta_brier_vs_m0": UNIFORM_BRIER - score,
                }
            )

        selected = min(
            candidates,
            key=lambda item: (
                float(item["calibration_brier"]),
                str(item["family"]),
                float(item["parameter"]),
            ),
        )
        holdout = _error_metrics(
            normalized,
            start=calibration_end,
            stop=prefix_len,
            family=str(selected["family"]),
            parameter=float(selected["parameter"]),
        )
        round_payloads.append(
            {
                "round": round_index,
                "prefix_draws": prefix_len,
                "train_end": train_end,
                "calibration_end": calibration_end,
                "holdout_windows": prefix_len - calibration_end,
                "candidate_count": len(candidates),
                "selected": selected,
                "holdout_error_metrics": holdout,
                "leakage_safe": True,
            }
        )

    briers = [float(item["holdout_error_metrics"]["brier"]) for item in round_payloads]
    deltas = [float(item["holdout_error_metrics"]["delta_brier_vs_m0"]) for item in round_payloads]
    maes = [float(item["holdout_error_metrics"]["mae"]) for item in round_payloads]
    rmses = [float(item["holdout_error_metrics"]["rmse"]) for item in round_payloads]
    eces = [float(item["holdout_error_metrics"]["calibration_ece_10"]) for item in round_payloads]
    selected_models = Counter(
        f"{item['selected']['family']}:{float(item['selected']['parameter']):g}" for item in round_payloads
    )

    best_index = max(range(len(round_payloads)), key=lambda index: deltas[index])
    worst_index = min(range(len(round_payloads)), key=lambda index: deltas[index])
    return {
        "status": "PASS",
        "protocol": "RETROSPECTIVE_ANCHORED_PREFIX_60_20_20_CALIBRATION_ERROR_V1",
        "round_count": len(round_payloads),
        "history_draw_count": len(normalized),
        "m0_brier": UNIFORM_BRIER,
        "m0_mae": 0.48,
        "m0_rmse": math.sqrt(UNIFORM_BRIER),
        "m0_calibration_ece_10": 0.0,
        "parameter_grids": {
            "m1_lambda": list(M1_LAMBDA_GRID),
            "m2_alpha": list(M2_ALPHA_GRID),
        },
        "rounds": round_payloads,
        "summary": {
            "mean_brier": fmean(briers),
            "median_brier": median(briers),
            "min_brier": min(briers),
            "max_brier": max(briers),
            "mean_delta_brier_vs_m0": fmean(deltas),
            "median_delta_brier_vs_m0": median(deltas),
            "positive_delta_rounds": sum(1 for value in deltas if value > 0.0),
            "non_positive_delta_rounds": sum(1 for value in deltas if value <= 0.0),
            "mean_mae": fmean(maes),
            "mean_rmse": fmean(rmses),
            "mean_calibration_ece_10": fmean(eces),
            "max_calibration_ece_10": max(eces),
            "selected_model_counts": dict(sorted(selected_models.items())),
            "best_round": round_payloads[best_index]["round"],
            "best_round_delta_brier": deltas[best_index],
            "worst_round": round_payloads[worst_index]["round"],
            "worst_round_delta_brier": deltas[worst_index],
        },
        "rounds_are_independent": False,
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": "EVIDENCIA_PREDITIVA_INSUFICIENTE",
        "limitations": [
            "Rodadas retrospectivas ancoradas compartilham dados e não são replicações independentes.",
            "Parâmetros são escolhidos somente na janela de calibração de cada rodada; o holdout não participa da seleção.",
            "Nenhum resultado desta auditoria altera automaticamente o modelo prospectivo ou a política operacional.",
        ],
    }
