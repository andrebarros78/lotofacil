from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL, generate_uniform_portfolio

ARTIFACT_SCHEMA_VERSION = "card-artifact-v1"
AUTHORITY_ID = "CARD_GENERATION_SERVICE_V1"

STATUS_PREVIEW = "PREVIEW"
STATUS_FROZEN = "FROZEN"
STATUS_EXPORTED = "EXPORTED"
STATUS_EVALUATED = "EVALUATED"
STATUS_INVALIDATED = "INVALIDATED"

VALID_STATUSES = {
    STATUS_PREVIEW,
    STATUS_FROZEN,
    STATUS_EXPORTED,
    STATUS_EVALUATED,
    STATUS_INVALIDATED,
}
OPERATIONAL_STATUSES = {STATUS_FROZEN, STATUS_EXPORTED, STATUS_EVALUATED}

POLICY_PRIMARY = "PRIMARY_CARD_M1_M2_V1"
POLICY_UNIFORM = "UNIFORM_RANDOM_PORTFOLIO_V1"
POLICY_OPERATOR = "OPERATOR_MULTI_FREEZE_V2"

_OPERATOR_NUMBER_MIN = 1
_OPERATOR_NUMBER_MAX = 25
_OPERATOR_CARD_SIZE = 15
_OPERATOR_COMBINATION_SPACE = math.comb(_OPERATOR_NUMBER_MAX, _OPERATOR_CARD_SIZE)


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _normalize_cards(cards: Sequence[Iterable[int]]) -> tuple[tuple[int, ...], ...]:
    normalized = tuple(normalize_numbers(card) for card in cards)
    if not normalized:
        raise ValueError("CARD_ARTIFACT_REQUIRES_CARDS")
    if len(set(normalized)) != len(normalized):
        raise ValueError("CARD_ARTIFACT_DUPLICATE_CARD")
    return normalized


@dataclass(frozen=True, slots=True)
class CardArtifact:
    artifact_id: str
    artifact_sha256: str
    schema_version: str
    authority_id: str
    status: str
    policy_id: str
    policy_version: str
    target_contest: int | None
    training_last_contest: int | None
    data_snapshot_hash: str | None
    storage_snapshot_id: str | None
    storage_snapshot_hash: str | None
    seed: int | None
    cards: tuple[tuple[int, ...], ...]
    cards_sha256: str
    card_count: int
    cost_cents: int
    predictive_evidence: str
    evidence_label: str
    metadata: dict[str, object]

    @property
    def operational_use_allowed(self) -> bool:
        return self.status in OPERATIONAL_STATUSES

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "artifact_sha256": self.artifact_sha256,
            "schema_version": self.schema_version,
            "authority_id": self.authority_id,
            "status": self.status,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "target_contest": self.target_contest,
            "training_last_contest": self.training_last_contest,
            "data_snapshot_hash": self.data_snapshot_hash,
            "storage_snapshot_id": self.storage_snapshot_id,
            "storage_snapshot_hash": self.storage_snapshot_hash,
            "seed": self.seed,
            "cards": [list(card) for card in self.cards],
            "cards_sha256": self.cards_sha256,
            "card_count": self.card_count,
            "cost_cents": self.cost_cents,
            "predictive_evidence": self.predictive_evidence,
            "evidence_label": self.evidence_label,
            "operational_use_allowed": self.operational_use_allowed,
            "metadata": self.metadata,
        }


def _artifact_payload(
    *,
    status: str,
    policy_id: str,
    policy_version: str,
    target_contest: int | None,
    training_last_contest: int | None,
    data_snapshot_hash: str | None,
    storage_snapshot_id: str | None,
    storage_snapshot_hash: str | None,
    seed: int | None,
    cards: tuple[tuple[int, ...], ...],
    predictive_evidence: str,
    evidence_label: str,
    metadata: Mapping[str, object] | None,
) -> dict[str, object]:
    if status not in VALID_STATUSES:
        raise ValueError("CARD_ARTIFACT_STATUS_INVALID")
    if target_contest is not None and target_contest <= 0:
        raise ValueError("CARD_ARTIFACT_TARGET_INVALID")
    if training_last_contest is not None and training_last_contest <= 0:
        raise ValueError("CARD_ARTIFACT_TRAINING_CUTOFF_INVALID")
    if (
        target_contest is not None
        and training_last_contest is not None
        and target_contest != training_last_contest + 1
    ):
        raise ValueError("CARD_ARTIFACT_TARGET_MUST_EQUAL_TRAINING_LAST_PLUS_ONE")
    normalized_meta = dict(metadata or {})
    cards_payload = [list(card) for card in cards]
    cards_sha256 = _sha256(cards_payload)
    return {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority_id": AUTHORITY_ID,
        "status": status,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "target_contest": target_contest,
        "training_last_contest": training_last_contest,
        "data_snapshot_hash": data_snapshot_hash,
        "storage_snapshot_id": storage_snapshot_id,
        "storage_snapshot_hash": storage_snapshot_hash,
        "seed": seed,
        "cards": cards_payload,
        "cards_sha256": cards_sha256,
        "card_count": len(cards),
        "cost_cents": len(cards) * DEFAULT_RULES.simple_bet_cost_cents,
        "predictive_evidence": predictive_evidence,
        "evidence_label": evidence_label,
        "metadata": normalized_meta,
    }


def build_card_artifact(
    *,
    status: str,
    policy_id: str,
    policy_version: str,
    cards: Sequence[Iterable[int]],
    target_contest: int | None = None,
    training_last_contest: int | None = None,
    data_snapshot_hash: str | None = None,
    storage_snapshot_id: str | None = None,
    storage_snapshot_hash: str | None = None,
    seed: int | None = None,
    predictive_evidence: str = "NOT_ESTABLISHED",
    evidence_label: str = UNPROVEN_LABEL,
    metadata: Mapping[str, object] | None = None,
) -> CardArtifact:
    normalized = _normalize_cards(cards)
    payload = _artifact_payload(
        status=status,
        policy_id=policy_id,
        policy_version=policy_version,
        target_contest=target_contest,
        training_last_contest=training_last_contest,
        data_snapshot_hash=data_snapshot_hash,
        storage_snapshot_id=storage_snapshot_id,
        storage_snapshot_hash=storage_snapshot_hash,
        seed=seed,
        cards=normalized,
        predictive_evidence=predictive_evidence,
        evidence_label=evidence_label,
        metadata=metadata,
    )
    digest = _sha256(payload)
    return CardArtifact(
        artifact_id=f"card-{digest[:24]}",
        artifact_sha256=digest,
        schema_version=ARTIFACT_SCHEMA_VERSION,
        authority_id=AUTHORITY_ID,
        status=status,
        policy_id=policy_id,
        policy_version=policy_version,
        target_contest=target_contest,
        training_last_contest=training_last_contest,
        data_snapshot_hash=data_snapshot_hash,
        storage_snapshot_id=storage_snapshot_id,
        storage_snapshot_hash=storage_snapshot_hash,
        seed=seed,
        cards=normalized,
        cards_sha256=str(payload["cards_sha256"]),
        card_count=len(normalized),
        cost_cents=len(normalized) * DEFAULT_RULES.simple_bet_cost_cents,
        predictive_evidence=predictive_evidence,
        evidence_label=evidence_label,
        metadata=dict(metadata or {}),
    )


def validate_card_artifact(
    payload: object,
    *,
    expected_status: str | None = None,
    expected_cards: Sequence[Iterable[int]] | None = None,
    require_operational: bool = False,
) -> CardArtifact:
    if not isinstance(payload, dict):
        raise RuntimeError("CARD_ARTIFACT_MISSING")
    try:
        artifact = build_card_artifact(
            status=str(payload["status"]),
            policy_id=str(payload["policy_id"]),
            policy_version=str(payload["policy_version"]),
            cards=payload["cards"],
            target_contest=(int(payload["target_contest"]) if payload.get("target_contest") is not None else None),
            training_last_contest=(
                int(payload["training_last_contest"])
                if payload.get("training_last_contest") is not None
                else None
            ),
            data_snapshot_hash=(
                str(payload["data_snapshot_hash"]) if payload.get("data_snapshot_hash") is not None else None
            ),
            storage_snapshot_id=(
                str(payload["storage_snapshot_id"]) if payload.get("storage_snapshot_id") is not None else None
            ),
            storage_snapshot_hash=(
                str(payload["storage_snapshot_hash"]) if payload.get("storage_snapshot_hash") is not None else None
            ),
            seed=(int(payload["seed"]) if payload.get("seed") is not None else None),
            predictive_evidence=str(payload["predictive_evidence"]),
            evidence_label=str(payload["evidence_label"]),
            metadata=(payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("CARD_ARTIFACT_INVALID") from exc

    expected = artifact.to_dict()
    if payload != expected:
        raise RuntimeError("CARD_ARTIFACT_HASH_OR_PAYLOAD_MISMATCH")
    if expected_status is not None and artifact.status != expected_status:
        raise RuntimeError("CARD_ARTIFACT_STATUS_MISMATCH")
    if expected_cards is not None and artifact.cards != _normalize_cards(expected_cards):
        raise RuntimeError("CARD_ARTIFACT_CARDS_MISMATCH")
    if require_operational and not artifact.operational_use_allowed:
        raise RuntimeError("CARD_ARTIFACT_NOT_OPERATIONAL")
    return artifact


def operator_card_for_generation_index(target_contest: int, generation_index: int) -> tuple[int, ...]:
    if target_contest <= 0:
        raise ValueError("target_contest deve ser positivo")
    if not 0 <= generation_index < _OPERATOR_COMBINATION_SPACE:
        raise ValueError("generation_index fora do espaço combinatório")
    digest = hashlib.sha256(f"operator-multi-freeze-v2:{target_contest}".encode("utf-8")).digest()
    offset = int.from_bytes(digest[:8], "big") % _OPERATOR_COMBINATION_SPACE
    step = int.from_bytes(digest[8:16], "big") % _OPERATOR_COMBINATION_SPACE or 1
    while math.gcd(step, _OPERATOR_COMBINATION_SPACE) != 1:
        step = (step + 1) % _OPERATOR_COMBINATION_SPACE or 1

    values: list[int] = []
    next_value = _OPERATOR_NUMBER_MIN
    remainder = (offset + generation_index * step) % _OPERATOR_COMBINATION_SPACE
    for slots_left in range(_OPERATOR_CARD_SIZE, 0, -1):
        for candidate in range(next_value, _OPERATOR_NUMBER_MAX + 1):
            count = math.comb(_OPERATOR_NUMBER_MAX - candidate, slots_left - 1)
            if remainder < count:
                values.append(candidate)
                next_value = candidate + 1
                break
            remainder -= count
    return tuple(values)


class CardGenerationService:
    authority_id = AUTHORITY_ID

    @staticmethod
    def preview_uniform(
        *,
        card_count: int,
        seed: int,
        target_contest: int | None,
        data_snapshot_hash: str | None = None,
        storage_snapshot_id: str | None = None,
        storage_snapshot_hash: str | None = None,
    ) -> CardArtifact:
        portfolio = generate_uniform_portfolio(card_count, seed=seed)
        return build_card_artifact(
            status=STATUS_PREVIEW,
            policy_id=POLICY_UNIFORM,
            policy_version="1",
            cards=portfolio.cards,
            target_contest=target_contest,
            data_snapshot_hash=data_snapshot_hash,
            storage_snapshot_id=storage_snapshot_id,
            storage_snapshot_hash=storage_snapshot_hash,
            seed=seed,
            evidence_label=portfolio.evidence_label,
            metadata={"surface": "READ_ONLY_PREVIEW"},
        )

    @staticmethod
    def freeze_uniform(
        *,
        card_count: int,
        seed: int,
        target_contest: int | None,
        data_snapshot_hash: str | None = None,
        storage_snapshot_id: str | None = None,
        storage_snapshot_hash: str | None = None,
    ) -> CardArtifact:
        portfolio = generate_uniform_portfolio(card_count, seed=seed)
        return build_card_artifact(
            status=STATUS_FROZEN,
            policy_id=POLICY_UNIFORM,
            policy_version="1",
            cards=portfolio.cards,
            target_contest=target_contest,
            data_snapshot_hash=data_snapshot_hash,
            storage_snapshot_id=storage_snapshot_id,
            storage_snapshot_hash=storage_snapshot_hash,
            seed=seed,
            evidence_label=portfolio.evidence_label,
            metadata={"surface": "PERSISTED_PORTFOLIO"},
        )

    @staticmethod
    def freeze_primary(
        *,
        card: Iterable[int],
        target_contest: int,
        training_last_contest: int,
        decision_sha256: str,
        primary_model: str,
        secondary_model: str,
        selection_method: str,
        data_snapshot_hash: str | None = None,
        storage_snapshot_id: str | None = None,
        storage_snapshot_hash: str | None = None,
    ) -> CardArtifact:
        return build_card_artifact(
            status=STATUS_FROZEN,
            policy_id=POLICY_PRIMARY,
            policy_version="1",
            cards=(card,),
            target_contest=target_contest,
            training_last_contest=training_last_contest,
            data_snapshot_hash=data_snapshot_hash,
            storage_snapshot_id=storage_snapshot_id,
            storage_snapshot_hash=storage_snapshot_hash,
            metadata={
                "decision_sha256": decision_sha256,
                "primary_model": primary_model,
                "secondary_model": secondary_model,
                "selection_method": selection_method,
                "surface": "PRIMARY_PREDICTION",
            },
        )

    @staticmethod
    def freeze_operator_batch(
        *,
        cards: Sequence[Iterable[int]],
        target_contest: int,
        data_snapshot_hash: str | None,
        storage_snapshot_id: str | None,
        storage_snapshot_hash: str | None,
        request_fingerprint: str,
    ) -> CardArtifact:
        return build_card_artifact(
            status=STATUS_FROZEN,
            policy_id=POLICY_OPERATOR,
            policy_version="2",
            cards=cards,
            target_contest=target_contest,
            data_snapshot_hash=data_snapshot_hash,
            storage_snapshot_id=storage_snapshot_id,
            storage_snapshot_hash=storage_snapshot_hash,
            metadata={
                "request_fingerprint": request_fingerprint,
                "surface": "OPERATOR_FREEZE",
            },
        )
