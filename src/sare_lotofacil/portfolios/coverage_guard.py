from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES

COVERAGE_GUARD_METHOD = "TWO_CARD_BALANCED_PARTITION_MAXIMIN_V1"
GUARANTEED_MIN_BEST_HITS = 8
CORE_SIZE = 5


@dataclass(frozen=True, slots=True)
class CoverageGuardDecision:
    target_contest: int
    lead_card: tuple[int, ...]
    guard_card: tuple[int, ...]
    retained_core: tuple[int, ...]
    overlap: int
    union_size: int
    guaranteed_min_best_hits: int
    method: str
    decision_sha256: str

    @property
    def cards(self) -> tuple[tuple[int, ...], tuple[int, ...]]:
        return (self.lead_card, self.guard_card)

    def to_dict(self) -> dict[str, object]:
        return {
            "target_contest": self.target_contest,
            "lead_card": list(self.lead_card),
            "guard_card": list(self.guard_card),
            "cards": [list(card) for card in self.cards],
            "retained_core": list(self.retained_core),
            "overlap": self.overlap,
            "union_size": self.union_size,
            "guaranteed_min_best_hits": self.guaranteed_min_best_hits,
            "method": self.method,
            "decision_sha256": self.decision_sha256,
        }


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_probabilities(probabilities: Sequence[float]) -> tuple[float, ...]:
    if len(probabilities) != DEFAULT_RULES.universe_size:
        raise ValueError("coverage guard probabilities must contain 25 values")
    normalized = tuple(float(value) for value in probabilities)
    if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in normalized):
        raise ValueError("coverage guard probabilities contain invalid value")
    return normalized


def _retained_core(
    lead_card: tuple[int, ...],
    probabilities: Sequence[float] | None,
) -> tuple[int, ...]:
    if probabilities is None:
        return tuple(lead_card[:CORE_SIZE])
    scores = _validate_probabilities(probabilities)
    ranked = sorted(lead_card, key=lambda number: (-scores[number - 1], number))
    return tuple(sorted(ranked[:CORE_SIZE]))


def build_two_card_coverage_guard(
    lead_card: Iterable[int],
    *,
    target_contest: int,
    probabilities: Sequence[float] | None = None,
) -> CoverageGuardDecision:
    """Preserva o cartão líder e adiciona um cartão de guarda com piso exato de 8.

    Os dois cartões têm 15 dezenas, interseção 5 e união igual ao universo de
    25 dezenas. Para qualquer resultado R de 15 dezenas, particione o universo
    em core C (5), ala A exclusiva do cartão líder (10) e ala B exclusiva do
    cartão de guarda (10). Se x=|R∩C|, a=|R∩A| e b=|R∩B|, então x+a+b=15.
    Os acertos são h1=x+a e h2=x+b, logo h1+h2=15+x>=15 e
    max(h1,h2)>=ceil((15+x)/2)>=8. A garantia não depende de previsão.
    """
    if target_contest <= 0:
        raise ValueError("target_contest deve ser positivo")

    lead = normalize_numbers(lead_card)
    core = _retained_core(lead, probabilities)
    lead_set = set(lead)
    complement = tuple(
        number
        for number in range(1, DEFAULT_RULES.universe_size + 1)
        if number not in lead_set
    )
    guard = normalize_numbers((*complement, *core))

    overlap = len(set(lead).intersection(guard))
    union_size = len(set(lead).union(guard))
    if overlap != CORE_SIZE or union_size != DEFAULT_RULES.universe_size:
        raise RuntimeError("COVERAGE_GUARD_CONSTRUCTION_INVARIANT_FAILED")

    payload = {
        "target_contest": target_contest,
        "lead_card": list(lead),
        "guard_card": list(guard),
        "retained_core": list(core),
        "overlap": overlap,
        "union_size": union_size,
        "guaranteed_min_best_hits": GUARANTEED_MIN_BEST_HITS,
        "method": COVERAGE_GUARD_METHOD,
    }
    digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
    return CoverageGuardDecision(
        target_contest=target_contest,
        lead_card=lead,
        guard_card=guard,
        retained_core=core,
        overlap=overlap,
        union_size=union_size,
        guaranteed_min_best_hits=GUARANTEED_MIN_BEST_HITS,
        method=COVERAGE_GUARD_METHOD,
        decision_sha256=digest,
    )
