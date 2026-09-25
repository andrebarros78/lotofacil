from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from statistics import fmean, pstdev
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL

SELECTION_METHOD = "ADAPTIVE_MULTI_HORIZON_TOP15_V2"
DEFAULT_VALIDATION_WINDOWS = 240
DEFAULT_MIN_TRAIN = 300
UNIFORM_PROBABILITY = 0.6
UNIFORM_BRIER = 0.24


@dataclass(frozen=True, slots=True)
class AdaptiveCandidateSpec:
    model_id: str
    family: str
    parameter: float
    window: int | None = None
    recent_weight: float | None = None


@dataclass(frozen=True, slots=True)
class AdaptiveCandidateMetrics:
    model_id: str
    windows: int
    mean_hits: float
    hit_stddev: float
    min_hits: int
    max_hits: int
    hits_ge_11: int
    hits_ge_12: int
    hits_ge_13: int
    hits_ge_14: int
    hits_15: int
    mean_brier: float
    delta_brier_vs_uniform: float


@dataclass(frozen=True, slots=True)
class AdaptivePrimaryDecision:
    target_contest: int
    training_last_contest: int
    card: tuple[int, ...]
    ranking: tuple[int, ...]
    probabilities: tuple[float, ...]
    selected_model: AdaptiveCandidateSpec
    selected_metrics: AdaptiveCandidateMetrics
    leaderboard: tuple[AdaptiveCandidateMetrics, ...]
    selection_method: str
    validation_windows: int
    evidence_label: str
    decision_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "target_contest": self.target_contest,
            "training_last_contest": self.training_last_contest,
            "card": list(self.card),
            "ranking": list(self.ranking),
            "probabilities": list(self.probabilities),
            "selected_model": asdict(self.selected_model),
            "selected_metrics": asdict(self.selected_metrics),
            "leaderboard": [asdict(item) for item in self.leaderboard],
            "selection_method": self.selection_method,
            "validation_windows": self.validation_windows,
            "evidence_label": self.evidence_label,
            "decision_sha256": self.decision_sha256,
        }


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _normalized(draws: Sequence[Iterable[int]]) -> tuple[tuple[int, ...], ...]:
    return tuple(normalize_numbers(draw) for draw in draws)


def _frequency_probabilities(
    draws: Sequence[tuple[int, ...]],
    *,
    lam: float,
) -> tuple[float, ...]:
    if lam < 0:
        raise ValueError("lam must be non-negative")
    if not draws:
        return (UNIFORM_PROBABILITY,) * 25
    counts = [0] * 25
    for draw in draws:
        for number in draw:
            counts[number - 1] += 1
    n = len(draws)
    return tuple(
        (count + UNIFORM_PROBABILITY * lam) / (n + lam)
        for count in counts
    )


def _rolling_probabilities(
    draws: Sequence[tuple[int, ...]],
    *,
    window: int,
    shrink: float,
) -> tuple[float, ...]:
    if window <= 0:
        raise ValueError("window must be positive")
    recent = tuple(draws[-window:])
    return _frequency_probabilities(recent, lam=shrink)


def _exponential_probabilities(
    draws: Sequence[tuple[int, ...]],
    *,
    alpha: float,
) -> tuple[float, ...]:
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    probabilities = [UNIFORM_PROBABILITY] * 25
    for draw in draws:
        observed = set(draw)
        probabilities = [
            (1.0 - alpha) * probability + alpha * (1.0 if number in observed else 0.0)
            for number, probability in enumerate(probabilities, start=1)
        ]
    return tuple(probabilities)


def _blend_probabilities(
    draws: Sequence[tuple[int, ...]],
    *,
    window: int,
    recent_weight: float,
) -> tuple[float, ...]:
    if not 0.0 < recent_weight < 1.0:
        raise ValueError("recent_weight must be in (0, 1)")
    global_scores = _frequency_probabilities(draws, lam=100.0)
    recent_scores = _rolling_probabilities(draws, window=window, shrink=25.0)
    return tuple(
        (1.0 - recent_weight) * global_score + recent_weight * recent_score
        for global_score, recent_score in zip(global_scores, recent_scores)
    )


def candidate_specs() -> tuple[AdaptiveCandidateSpec, ...]:
    specs: list[AdaptiveCandidateSpec] = []
    for lam in (50.0, 100.0, 200.0):
        specs.append(AdaptiveCandidateSpec(f"global_lam_{lam:g}", "global", lam))
    for window in (20, 50, 100, 250, 500):
        specs.append(
            AdaptiveCandidateSpec(
                f"rolling_{window}_shrink_25",
                "rolling",
                25.0,
                window=window,
            )
        )
    for alpha in (0.02, 0.05, 0.10):
        specs.append(AdaptiveCandidateSpec(f"exp_alpha_{alpha:g}", "exponential", alpha))
    for window in (50, 100):
        for recent_weight in (0.25, 0.50, 0.75):
            specs.append(
                AdaptiveCandidateSpec(
                    f"blend_global100_recent{window}_w{recent_weight:g}",
                    "blend",
                    100.0,
                    window=window,
                    recent_weight=recent_weight,
                )
            )
    return tuple(specs)


def _predict(spec: AdaptiveCandidateSpec, history: Sequence[tuple[int, ...]]) -> tuple[float, ...]:
    if spec.family == "global":
        return _frequency_probabilities(history, lam=spec.parameter)
    if spec.family == "rolling":
        if spec.window is None:
            raise ValueError("rolling model requires window")
        return _rolling_probabilities(history, window=spec.window, shrink=spec.parameter)
    if spec.family == "exponential":
        return _exponential_probabilities(history, alpha=spec.parameter)
    if spec.family == "blend":
        if spec.window is None or spec.recent_weight is None:
            raise ValueError("blend model requires window and recent_weight")
        return _blend_probabilities(
            history,
            window=spec.window,
            recent_weight=spec.recent_weight,
        )
    raise ValueError(f"unsupported adaptive family: {spec.family}")


def _rank(probabilities: Sequence[float]) -> tuple[int, ...]:
    if len(probabilities) != 25:
        raise ValueError("adaptive probabilities must contain 25 values")
    if any(not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0 for value in probabilities):
        raise ValueError("adaptive probabilities contain invalid value")
    return tuple(
        sorted(
            range(1, 26),
            key=lambda number: (-float(probabilities[number - 1]), number),
        )
    )


def _brier(probabilities: Sequence[float], draw: Sequence[int]) -> float:
    observed = set(draw)
    return sum(
        (float(probability) - (1.0 if number in observed else 0.0)) ** 2
        for number, probability in enumerate(probabilities, start=1)
    ) / 25.0


def _evaluate_spec(
    draws: tuple[tuple[int, ...], ...],
    spec: AdaptiveCandidateSpec,
    *,
    start: int,
) -> AdaptiveCandidateMetrics:
    hits: list[int] = []
    briers: list[float] = []
    for target_index in range(start, len(draws)):
        history = draws[:target_index]
        probabilities = _predict(spec, history)
        card = set(_rank(probabilities)[:15])
        observed = set(draws[target_index])
        hits.append(len(card.intersection(observed)))
        briers.append(_brier(probabilities, draws[target_index]))
    if not hits:
        raise ValueError("adaptive evaluation requires at least one validation window")
    mean_brier = fmean(briers)
    return AdaptiveCandidateMetrics(
        model_id=spec.model_id,
        windows=len(hits),
        mean_hits=fmean(hits),
        hit_stddev=pstdev(hits),
        min_hits=min(hits),
        max_hits=max(hits),
        hits_ge_11=sum(value >= 11 for value in hits),
        hits_ge_12=sum(value >= 12 for value in hits),
        hits_ge_13=sum(value >= 13 for value in hits),
        hits_ge_14=sum(value >= 14 for value in hits),
        hits_15=sum(value == 15 for value in hits),
        mean_brier=mean_brier,
        delta_brier_vs_uniform=UNIFORM_BRIER - mean_brier,
    )


def _selection_key(metrics: AdaptiveCandidateMetrics) -> tuple[float, int, int, float, float, str]:
    return (
        -metrics.mean_hits,
        -metrics.hits_ge_12,
        -metrics.hits_ge_11,
        metrics.mean_brier,
        metrics.hit_stddev,
        metrics.model_id,
    )


def build_adaptive_primary_card(
    training_draws: Sequence[Iterable[int]],
    *,
    target_contest: int,
    training_last_contest: int,
    validation_windows: int = DEFAULT_VALIDATION_WINDOWS,
    min_train: int = DEFAULT_MIN_TRAIN,
) -> AdaptivePrimaryDecision:
    if target_contest != training_last_contest + 1:
        raise ValueError("ADAPTIVE_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE")
    draws = _normalized(training_draws)
    if len(draws) != training_last_contest:
        raise ValueError("ADAPTIVE_HISTORY_LENGTH_MUST_MATCH_TRAINING_LAST_CONTEST")
    if validation_windows < 30:
        raise ValueError("adaptive validation requires at least 30 windows")
    start = max(min_train, len(draws) - validation_windows)
    if start >= len(draws):
        raise ValueError("adaptive model requires more training history")

    specs = candidate_specs()
    metrics = tuple(_evaluate_spec(draws, spec, start=start) for spec in specs)
    ordered_metrics = tuple(sorted(metrics, key=_selection_key))
    selected_metrics = ordered_metrics[0]
    selected_spec = next(spec for spec in specs if spec.model_id == selected_metrics.model_id)

    probabilities = _predict(selected_spec, draws)
    probability_sum = sum(probabilities)
    if not math.isclose(probability_sum, 15.0, rel_tol=0.0, abs_tol=1e-9):
        raise RuntimeError(f"ADAPTIVE_PROBABILITY_MASS_INVALID:{probability_sum}")
    ranking = _rank(probabilities)
    card = tuple(sorted(ranking[:15]))
    payload = {
        "target_contest": target_contest,
        "training_last_contest": training_last_contest,
        "card": list(card),
        "ranking": list(ranking),
        "probabilities": list(probabilities),
        "selected_model": asdict(selected_spec),
        "selected_metrics": asdict(selected_metrics),
        "leaderboard": [asdict(item) for item in ordered_metrics],
        "selection_method": SELECTION_METHOD,
        "validation_windows": len(draws) - start,
    }
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return AdaptivePrimaryDecision(
        target_contest=target_contest,
        training_last_contest=training_last_contest,
        card=card,
        ranking=ranking,
        probabilities=probabilities,
        selected_model=selected_spec,
        selected_metrics=selected_metrics,
        leaderboard=ordered_metrics,
        selection_method=SELECTION_METHOD,
        validation_windows=len(draws) - start,
        evidence_label=UNPROVEN_LABEL,
        decision_sha256=digest,
    )
