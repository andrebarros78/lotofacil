from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass

from sare_lotofacil.domain.masks import normalize_numbers


@dataclass(frozen=True, slots=True)
class PortfolioSearchPolicy:
    max_overlap: int
    max_exposure: float
    max_attempts: int
    seed: int
    policy_name: str = "bounded-random-search-v1"

    def validate(self) -> None:
        if not 0 <= self.max_overlap <= 15:
            raise ValueError("max_overlap deve estar entre 0 e 15")
        if not 0.0 < self.max_exposure <= 1.0:
            raise ValueError("max_exposure deve estar em (0, 1]")
        if self.max_attempts <= 0:
            raise ValueError("max_attempts deve ser positivo")
        if not self.policy_name.strip():
            raise ValueError("policy_name obrigatório")

    @property
    def canonical_json(self) -> str:
        self.validate()
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()

    @property
    def config_id(self) -> str:
        return f"portfolio-policy-{self.config_hash[:24]}"


@dataclass(frozen=True, slots=True)
class PortfolioSearchResult:
    status: str
    policy_id: str
    attempts: int
    requested_card_count: int
    cards: tuple[tuple[int, ...], ...]


def _candidate_allowed(
    candidate: tuple[int, ...],
    selected: tuple[tuple[int, ...], ...],
    *,
    requested_card_count: int,
    policy: PortfolioSearchPolicy,
) -> bool:
    candidate_set = set(candidate)
    if any(len(candidate_set.intersection(card)) > policy.max_overlap for card in selected):
        return False

    exposure_limit = policy.max_exposure * requested_card_count
    counts = {number: 0 for number in range(1, 26)}
    for card in (*selected, candidate):
        for number in card:
            counts[number] += 1
    return all(count <= exposure_limit + 1e-12 for count in counts.values())


def search_bounded_portfolio(
    card_count: int,
    *,
    policy: PortfolioSearchPolicy,
) -> PortfolioSearchResult:
    """Busca uma carteira dentro de um orçamento finito sem confundir limite com prova de inviabilidade."""
    if not 3 <= card_count <= 100:
        raise ValueError("card_count deve estar entre 3 e 100")
    policy.validate()

    rng = random.Random(policy.seed)
    selected: tuple[tuple[int, ...], ...] = ()
    attempts = 0
    while attempts < policy.max_attempts and len(selected) < card_count:
        attempts += 1
        candidate = normalize_numbers(rng.sample(range(1, 26), 15))
        if candidate in selected:
            continue
        if not _candidate_allowed(candidate, selected, requested_card_count=card_count, policy=policy):
            continue
        selected = (*selected, candidate)

    status = "FOUND" if len(selected) == card_count else "SEARCH_LIMIT_REACHED"
    return PortfolioSearchResult(
        status=status,
        policy_id=policy.config_id,
        attempts=attempts,
        requested_card_count=card_count,
        cards=selected if status == "FOUND" else (),
    )
