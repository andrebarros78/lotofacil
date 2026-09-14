from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.experiments.models import exponential_update, frequency_regularized
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL
from sare_lotofacil.statistics.baseline import uniform_baseline

PRIMARY_MODEL_NAME = "M1_frequency_regularized_lambda_100"
SECONDARY_MODEL_NAME = "M2_exponential_alpha_0.05"
SELECTION_METHOD = "M1_TOP15_M2_TIEBREAK_V1"


@dataclass(frozen=True, slots=True)
class PrimaryCardDecision:
    target_contest: int
    training_last_contest: int
    card: tuple[int, ...]
    ranking: tuple[int, ...]
    primary_model: str
    secondary_model: str
    selection_method: str
    primary_model_score_sum: float
    secondary_model_score_sum: float
    evidence_label: str
    decision_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "target_contest": self.target_contest,
            "training_last_contest": self.training_last_contest,
            "card": list(self.card),
            "ranking": list(self.ranking),
            "primary_model": self.primary_model,
            "secondary_model": self.secondary_model,
            "selection_method": self.selection_method,
            "primary_model_score_sum": self.primary_model_score_sum,
            "secondary_model_score_sum": self.secondary_model_score_sum,
            "evidence_label": self.evidence_label,
            "decision_sha256": self.decision_sha256,
        }


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_scores(scores: Sequence[float], *, name: str) -> tuple[float, ...]:
    if len(scores) != 25:
        raise ValueError(f"{name} deve conter 25 escores")
    normalized = tuple(float(value) for value in scores)
    if any(not math.isfinite(value) or value < 0.0 or value > 1.0 for value in normalized):
        raise ValueError(f"{name} contém escore inválido")
    return normalized


def select_primary_card(
    primary_scores: Sequence[float],
    secondary_scores: Sequence[float],
    *,
    target_contest: int,
    training_last_contest: int,
) -> PrimaryCardDecision:
    if training_last_contest < 1:
        raise ValueError("training_last_contest deve ser positivo")
    if target_contest != training_last_contest + 1:
        raise ValueError("PRIMARY_CARD_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE")

    primary = _validate_scores(primary_scores, name="primary_scores")
    secondary = _validate_scores(secondary_scores, name="secondary_scores")
    ranking = tuple(
        sorted(
            range(1, 26),
            key=lambda number: (-primary[number - 1], -secondary[number - 1], number),
        )
    )
    card = tuple(sorted(ranking[:15]))
    payload = {
        "target_contest": target_contest,
        "training_last_contest": training_last_contest,
        "card": list(card),
        "ranking": list(ranking),
        "primary_model": PRIMARY_MODEL_NAME,
        "secondary_model": SECONDARY_MODEL_NAME,
        "selection_method": SELECTION_METHOD,
        "primary_scores": list(primary),
        "secondary_scores": list(secondary),
    }
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return PrimaryCardDecision(
        target_contest=target_contest,
        training_last_contest=training_last_contest,
        card=card,
        ranking=ranking,
        primary_model=PRIMARY_MODEL_NAME,
        secondary_model=SECONDARY_MODEL_NAME,
        selection_method=SELECTION_METHOD,
        primary_model_score_sum=sum(primary[number - 1] for number in card),
        secondary_model_score_sum=sum(secondary[number - 1] for number in card),
        evidence_label=UNPROVEN_LABEL,
        decision_sha256=digest,
    )


def build_primary_card(
    training_draws: Sequence[Iterable[int]],
    *,
    target_contest: int,
    training_last_contest: int,
) -> PrimaryCardDecision:
    if not training_draws:
        raise ValueError("PRIMARY_CARD_REQUIRES_TRAINING_HISTORY")
    primary = frequency_regularized(training_draws, lam=100.0)
    secondary = uniform_baseline()
    for draw in training_draws:
        secondary = exponential_update(secondary, draw, alpha=0.05)
    return select_primary_card(
        primary,
        secondary,
        target_contest=target_contest,
        training_last_contest=training_last_contest,
    )
