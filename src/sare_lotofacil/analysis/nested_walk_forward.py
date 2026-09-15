from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter
from statistics import fmean
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.statistics.baseline import UNIFORM_BRIER

M1_LAMBDA_GRID = (25.0, 50.0, 100.0, 200.0, 400.0)
M2_ALPHA_GRID = (0.005, 0.01, 0.02, 0.05, 0.10)
DEFAULT_OUTER_FOLDS = 8
DEFAULT_INNER_FOLDS = 4
DEFAULT_LOCKBOX_FRACTION = 0.15
DEFAULT_MIN_TRAIN = 300
ECE_BINS = 10
BOOTSTRAP_REPLICATIONS = 2000
BOOTSTRAP_SEED = 20260915
UNIFORM_LOG_LOSS = -(0.6 * math.log(0.6) + 0.4 * math.log(0.4))


def _normalize_draws(draws: Sequence[Iterable[int]]) -> tuple[tuple[int, ...], ...]:
    return tuple(normalize_numbers(draw) for draw in draws)


def _target_vector(draw: Iterable[int]) -> tuple[float, ...]:
    observed = set(draw)
    return tuple(1.0 if number in observed else 0.0 for number in range(1, 26))


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


def _evaluate_candidate(
    draws: tuple[tuple[int, ...], ...],
    *,
    start: int,
    stop: int,
    family: str,
    parameter: float,
) -> dict[str, object]:
    if not 0 <= start < stop <= len(draws):
        raise ValueError("invalid evaluation interval")

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

    squared_error_sum = 0.0
    absolute_error_sum = 0.0
    log_loss_sum = 0.0
    observations = 0
    per_draw_brier: list[float] = []
    bin_count = [0] * ECE_BINS
    bin_probability_sum = [0.0] * ECE_BINS
    bin_observed_sum = [0.0] * ECE_BINS
    epsilon = 1e-15

    for target_index in range(start, stop):
        target = draws[target_index]
        target_vector = _target_vector(target)
        predicted = predict(target_index)
        draw_squared_error = 0.0

        for probability, observed in zip(predicted, target_vector):
            probability = min(max(float(probability), epsilon), 1.0 - epsilon)
            error = probability - observed
            squared_error = error * error
            squared_error_sum += squared_error
            draw_squared_error += squared_error
            absolute_error_sum += abs(error)
            log_loss_sum += -(
                observed * math.log(probability)
                + (1.0 - observed) * math.log(1.0 - probability)
            )
            bucket = min(int(probability * ECE_BINS), ECE_BINS - 1)
            bin_count[bucket] += 1
            bin_probability_sum[bucket] += probability
            bin_observed_sum[bucket] += observed
            observations += 1

        per_draw_brier.append(draw_squared_error / 25.0)
        update(target)

    brier = squared_error_sum / observations
    ece = 0.0
    for count, probability_sum, observed_sum in zip(
        bin_count, bin_probability_sum, bin_observed_sum
    ):
        if count == 0:
            continue
        mean_probability = probability_sum / count
        observed_rate = observed_sum / count
        ece += (count / observations) * abs(mean_probability - observed_rate)

    return {
        "windows": stop - start,
        "observations": observations,
        "brier": brier,
        "delta_brier_vs_m0": UNIFORM_BRIER - brier,
        "mae": absolute_error_sum / observations,
        "rmse": math.sqrt(brier),
        "log_loss": log_loss_sum / observations,
        "delta_log_loss_vs_m0": UNIFORM_LOG_LOSS - (log_loss_sum / observations),
        "calibration_ece_10": ece,
        "_per_draw_brier": tuple(per_draw_brier),
    }


def _partition_interval(start: int, stop: int, blocks: int) -> tuple[tuple[int, int], ...]:
    if blocks <= 0 or start >= stop or stop - start < blocks:
        raise ValueError("interval too short for requested blocks")
    span = stop - start
    boundaries = [start + (span * index) // blocks for index in range(blocks + 1)]
    return tuple((boundaries[index], boundaries[index + 1]) for index in range(blocks))


def _inner_blocks(
    available_end: int,
    *,
    folds: int,
    min_train: int,
) -> tuple[tuple[int, int], ...]:
    validation_start = max(min_train, available_end // 2)
    if available_end - validation_start < folds * 10:
        validation_start = max(min_train, available_end - folds * 10)
    if available_end - validation_start < folds:
        raise ValueError("insufficient inner walk-forward history")
    return _partition_interval(validation_start, available_end, folds)


def _candidate_specs() -> tuple[tuple[str, float], ...]:
    return tuple(
        [("M1", value) for value in M1_LAMBDA_GRID]
        + [("M2", value) for value in M2_ALPHA_GRID]
    )


def _select_inner(
    draws: tuple[tuple[int, ...], ...],
    *,
    available_end: int,
    folds: int,
    min_train: int,
) -> tuple[dict[str, object], list[dict[str, object]], tuple[tuple[int, int], ...]]:
    blocks = _inner_blocks(available_end, folds=folds, min_train=min_train)
    candidates: list[dict[str, object]] = []

    for family, parameter in _candidate_specs():
        weighted_brier = 0.0
        total_windows = 0
        fold_briers: list[float] = []

        for start, stop in blocks:
            metrics = _evaluate_candidate(
                draws,
                start=start,
                stop=stop,
                family=family,
                parameter=parameter,
            )
            brier = float(metrics["brier"])
            windows = int(metrics["windows"])
            fold_briers.append(brier)
            weighted_brier += brier * windows
            total_windows += windows

        mean_inner_brier = weighted_brier / total_windows
        candidates.append(
            {
                "family": family,
                "parameter": parameter,
                "mean_inner_brier": mean_inner_brier,
                "mean_inner_delta_brier_vs_m0": UNIFORM_BRIER - mean_inner_brier,
                "inner_fold_briers": fold_briers,
            }
        )

    selected = min(
        candidates,
        key=lambda item: (
            float(item["mean_inner_brier"]),
            str(item["family"]),
            float(item["parameter"]),
        ),
    )
    return selected, candidates, blocks


def _moving_block_bootstrap_delta_ci(
    per_draw_brier: Sequence[float],
    *,
    replications: int = BOOTSTRAP_REPLICATIONS,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, float | int | str]:
    scores = tuple(float(score) for score in per_draw_brier)
    if len(scores) < 2:
        raise ValueError("bootstrap requires at least two temporal windows")
    deltas = tuple(UNIFORM_BRIER - score for score in scores)
    observed_mean = fmean(deltas)
    block_length = max(2, round(math.sqrt(len(deltas))))
    starts = tuple(range(0, max(1, len(deltas) - block_length + 1)))
    rng = random.Random(seed)
    bootstrap_means: list[float] = []

    for _ in range(replications):
        sample: list[float] = []
        while len(sample) < len(deltas):
            start = rng.choice(starts)
            sample.extend(deltas[start : start + block_length])
        bootstrap_means.append(fmean(sample[: len(deltas)]))

    bootstrap_means.sort()
    low_index = max(0, int(0.025 * replications))
    high_index = min(replications - 1, int(0.975 * replications) - 1)
    return {
        "method": "MOVING_BLOCK_BOOTSTRAP_PERCENTILE_95",
        "mean": observed_mean,
        "low": bootstrap_means[low_index],
        "high": bootstrap_means[high_index],
        "block_length": block_length,
        "replications": replications,
        "seed": seed,
    }


def _public_metrics(metrics: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in metrics.items() if not key.startswith("_")}


def _selection_fingerprint(
    *,
    protocol: str,
    development_end: int,
    selected: dict[str, object],
    validation_blocks: Sequence[tuple[int, int]],
) -> str:
    payload = {
        "protocol": protocol,
        "development_end": development_end,
        "parameter_grids": {
            "m1_lambda": list(M1_LAMBDA_GRID),
            "m2_alpha": list(M2_ALPHA_GRID),
        },
        "selected_family": selected["family"],
        "selected_parameter": selected["parameter"],
        "validation_blocks": [list(block) for block in validation_blocks],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def run_nested_walk_forward(
    draws: Sequence[Iterable[int]],
    *,
    outer_folds: int = DEFAULT_OUTER_FOLDS,
    inner_folds: int = DEFAULT_INNER_FOLDS,
    lockbox_fraction: float = DEFAULT_LOCKBOX_FRACTION,
    min_train: int = DEFAULT_MIN_TRAIN,
) -> dict[str, object]:
    """Nested temporal walk-forward with non-overlapping outer tests and a final untouched lockbox.

    All hyperparameter choices are made from history strictly before the evaluated interval.
    The final lockbox is excluded from every selection step and is opened only after the
    final inner walk-forward has frozen the selected family/parameter.
    """
    normalized = _normalize_draws(draws)
    total = len(normalized)
    if total < 600:
        raise ValueError("nested walk-forward requires at least 600 draws")
    if outer_folds < 3:
        raise ValueError("outer_folds must be at least 3")
    if inner_folds < 2:
        raise ValueError("inner_folds must be at least 2")
    if min_train < 100:
        raise ValueError("min_train must be at least 100")
    if not 0.10 <= lockbox_fraction <= 0.30:
        raise ValueError("lockbox_fraction must be between 0.10 and 0.30")

    protocol = "NESTED_WALK_FORWARD_TEMPORAL_WITH_FINAL_LOCKBOX_V1"
    development_end = int(total * (1.0 - lockbox_fraction))
    lockbox_windows = total - development_end
    if lockbox_windows < 60:
        raise ValueError("final lockbox requires at least 60 draws")

    outer_start = max(min_train * 2, development_end // 2)
    if development_end - outer_start < outer_folds * 20:
        raise ValueError("development history is too short for requested outer folds")
    outer_blocks = _partition_interval(outer_start, development_end, outer_folds)

    outer_payloads: list[dict[str, object]] = []
    outer_per_draw_brier: list[float] = []
    selected_models: Counter[str] = Counter()
    weighted_outer_mae = 0.0
    weighted_outer_log_loss = 0.0
    weighted_outer_ece = 0.0
    outer_observations = 0

    for fold_index, (test_start, test_stop) in enumerate(outer_blocks, start=1):
        selected, candidates, inner_blocks = _select_inner(
            normalized,
            available_end=test_start,
            folds=inner_folds,
            min_train=min_train,
        )
        test_metrics = _evaluate_candidate(
            normalized,
            start=test_start,
            stop=test_stop,
            family=str(selected["family"]),
            parameter=float(selected["parameter"]),
        )
        per_draw_brier = tuple(float(value) for value in test_metrics["_per_draw_brier"])
        outer_per_draw_brier.extend(per_draw_brier)
        observations = int(test_metrics["observations"])
        outer_observations += observations
        weighted_outer_mae += float(test_metrics["mae"]) * observations
        weighted_outer_log_loss += float(test_metrics["log_loss"]) * observations
        weighted_outer_ece += float(test_metrics["calibration_ece_10"]) * observations
        selected_models[f"{selected['family']}:{float(selected['parameter']):g}"] += 1

        outer_payloads.append(
            {
                "fold": fold_index,
                "available_history_end": test_start,
                "inner_validation_blocks": [
                    {"start": start, "stop": stop, "windows": stop - start}
                    for start, stop in inner_blocks
                ],
                "candidate_count": len(candidates),
                "selected": selected,
                "test_start": test_start,
                "test_stop": test_stop,
                "test_windows": test_stop - test_start,
                "test_error_metrics": _public_metrics(test_metrics),
                "leakage_safe": True,
            }
        )

    outer_brier = fmean(outer_per_draw_brier)
    outer_delta_ci = _moving_block_bootstrap_delta_ci(outer_per_draw_brier)
    outer_aggregate = {
        "windows": len(outer_per_draw_brier),
        "observations": outer_observations,
        "brier": outer_brier,
        "delta_brier_vs_m0": UNIFORM_BRIER - outer_brier,
        "delta_brier_ci_95": outer_delta_ci,
        "mae": weighted_outer_mae / outer_observations,
        "rmse": math.sqrt(outer_brier),
        "log_loss": weighted_outer_log_loss / outer_observations,
        "delta_log_loss_vs_m0": UNIFORM_LOG_LOSS - (weighted_outer_log_loss / outer_observations),
        "weighted_mean_fold_ece_10": weighted_outer_ece / outer_observations,
        "selected_model_counts": dict(sorted(selected_models.items())),
    }

    final_inner_folds = max(inner_folds, 5)
    final_selected, final_candidates, final_inner_blocks = _select_inner(
        normalized,
        available_end=development_end,
        folds=final_inner_folds,
        min_train=min_train,
    )
    selection_fingerprint = _selection_fingerprint(
        protocol=protocol,
        development_end=development_end,
        selected=final_selected,
        validation_blocks=final_inner_blocks,
    )

    lockbox_metrics = _evaluate_candidate(
        normalized,
        start=development_end,
        stop=total,
        family=str(final_selected["family"]),
        parameter=float(final_selected["parameter"]),
    )
    lockbox_per_draw_brier = tuple(float(value) for value in lockbox_metrics["_per_draw_brier"])
    lockbox_delta_ci = _moving_block_bootstrap_delta_ci(
        lockbox_per_draw_brier,
        seed=BOOTSTRAP_SEED + 1,
    )

    retrospective_evidence_established = (
        float(outer_delta_ci["low"]) > 0.0
        and float(lockbox_delta_ci["low"]) > 0.0
        and float(outer_aggregate["delta_brier_vs_m0"]) > 0.0
        and float(lockbox_metrics["delta_brier_vs_m0"]) > 0.0
    )

    return {
        "status": "PASS",
        "protocol": protocol,
        "history_draw_count": total,
        "parameter_grids": {
            "m1_lambda": list(M1_LAMBDA_GRID),
            "m2_alpha": list(M2_ALPHA_GRID),
        },
        "baseline": {
            "family": "M0_UNIFORM",
            "probability": 0.6,
            "brier": UNIFORM_BRIER,
            "log_loss": UNIFORM_LOG_LOSS,
            "calibration_ece_10": 0.0,
        },
        "development": {
            "start": 0,
            "stop": development_end,
            "draws": development_end,
        },
        "outer_walk_forward": {
            "fold_count": outer_folds,
            "test_windows_non_overlapping": True,
            "folds": outer_payloads,
            "aggregate": outer_aggregate,
        },
        "final_inner_selection": {
            "available_history_end": development_end,
            "inner_fold_count": final_inner_folds,
            "validation_blocks": [
                {"start": start, "stop": stop, "windows": stop - start}
                for start, stop in final_inner_blocks
            ],
            "candidate_count": len(final_candidates),
            "selected": final_selected,
            "pre_lockbox_selection_fingerprint_sha256": selection_fingerprint,
        },
        "final_lockbox": {
            "start": development_end,
            "stop": total,
            "windows": lockbox_windows,
            "used_for_model_selection": False,
            "selection_frozen_before_evaluation": True,
            "selection_fingerprint_sha256": selection_fingerprint,
            "error_metrics": _public_metrics(lockbox_metrics),
            "delta_brier_ci_95": lockbox_delta_ci,
        },
        "retrospective_predictive_evidence": (
            "ESTABLISHED" if retrospective_evidence_established else "NOT_ESTABLISHED"
        ),
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": (
            "EVIDENCIA_RETROSPECTIVA_REPLICADA_REQUER_CONFIRMACAO_PROSPECTIVA"
            if retrospective_evidence_established
            else "EVIDENCIA_PREDITIVA_INSUFICIENTE"
        ),
        "automatic_model_promotion": False,
        "leakage_safe": True,
        "limitations": [
            "Outer test windows are non-overlapping, but later folds legitimately train on earlier observed outer outcomes.",
            "The final lockbox is retrospective historical data and is never used for hyperparameter selection.",
            "Even a positive retrospective lockbox does not establish prospective predictive advantage.",
            "No result from this audit automatically changes the production model or operational policy.",
        ],
    }
