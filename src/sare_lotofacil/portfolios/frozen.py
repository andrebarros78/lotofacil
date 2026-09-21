from __future__ import annotations

import hashlib
import json
import math
import time
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.authority import (
    POLICY_OPERATOR,
    STATUS_FROZEN,
    CardGenerationService,
    operator_card_for_generation_index,
    validate_card_artifact,
)
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL
from sare_lotofacil.resource_limits import (
    MAX_CARDS_PER_REQUEST,
    MAX_GENERATION_ATTEMPTS,
    ResourceLimitError,
    require_artifact_size,
    require_runtime,
)

POLICY_NAME = "operator-multi-freeze-v2"
NUMBER_MIN = 1
NUMBER_MAX = 25
CARD_SIZE = 15
COMBINATION_SPACE = math.comb(NUMBER_MAX, CARD_SIZE)
FREEZE_TYPE = "OPERATOR_CARD"


def _canonical(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(payload: object) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _policy() -> dict[str, object]:
    return {
        "policy_name": POLICY_NAME,
        "number_min": NUMBER_MIN,
        "number_max": NUMBER_MAX,
        "card_size": CARD_SIZE,
        "combination_space": COMBINATION_SPACE,
        "append_only": True,
        "duplicate_cards_for_same_target_forbidden": True,
        "operator_requests_must_generate": True,
        "idempotency_required": True,
        "freeze_provenance_required": True,
    }


def empty_operator_card_ledger() -> dict[str, object]:
    return {
        "schema_version": 2,
        "policy": _policy(),
        "requests": [],
        "summary": {"by_target": {}},
    }


def _unrank_combination(rank: int) -> tuple[int, ...]:
    if not 0 <= rank < COMBINATION_SPACE:
        raise ValueError("combination rank out of range")
    values: list[int] = []
    next_value = NUMBER_MIN
    remainder = rank
    for slots_left in range(CARD_SIZE, 0, -1):
        for candidate in range(next_value, NUMBER_MAX + 1):
            count = math.comb(NUMBER_MAX - candidate, slots_left - 1)
            if remainder < count:
                values.append(candidate)
                next_value = candidate + 1
                break
            remainder -= count
    return tuple(values)


def _permutation_parameters(target_contest: int) -> tuple[int, int]:
    digest = hashlib.sha256(f"{POLICY_NAME}:{target_contest}".encode("utf-8")).digest()
    offset = int.from_bytes(digest[:8], "big") % COMBINATION_SPACE
    step = int.from_bytes(digest[8:16], "big") % COMBINATION_SPACE or 1
    while math.gcd(step, COMBINATION_SPACE) != 1:
        step = (step + 1) % COMBINATION_SPACE or 1
    return offset, step


def card_for_generation_index(target_contest: int, generation_index: int) -> tuple[int, ...]:
    return operator_card_for_generation_index(target_contest, generation_index)


def card_sha256(card: Iterable[int]) -> str:
    return _sha256(list(normalize_numbers(card)))


def _request_hash_payload(request: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in request.items() if key != "request_sha256"}


def _request_fingerprint(
    *,
    target_contest: int,
    requested_card_count: int,
    state_snapshot_hash: str,
    idempotency_key: str,
    state_data_snapshot_hash: str | None = None,
) -> str:
    payload: dict[str, object] = {
        "target_contest": int(target_contest),
        "requested_card_count": int(requested_card_count),
        "state_snapshot_hash": state_snapshot_hash,
        "idempotency_key": idempotency_key,
    }
    if state_data_snapshot_hash is not None:
        payload["state_data_snapshot_hash"] = state_data_snapshot_hash
    return _sha256(payload)


def _operator_cards_for_target(ledger: dict[str, object], target_contest: int) -> set[tuple[int, ...]]:
    cards: set[tuple[int, ...]] = set()
    for request in ledger.get("requests", []):
        if int(request["target_contest"]) != target_contest:
            continue
        for item in request.get("cards", []):
            cards.add(normalize_numbers(item["card"]))
    return cards


def recover_operator_freezes(
    ledger: dict[str, object], *, target_contest: int, expected_card_count: int
) -> tuple[dict[str, object], ...]:
    if expected_card_count < 0:
        raise ValueError("expected_card_count deve ser >= 0")
    validate_operator_card_ledger(ledger)
    records = tuple(
        item
        for request in ledger.get("requests", [])
        if int(request["target_contest"]) == target_contest
        for item in request.get("cards", [])
    )
    if len(records) != expected_card_count:
        raise RuntimeError(
            f"FROZEN_CARD_COUNT_MISMATCH expected={expected_card_count} observed={len(records)}"
        )
    return records


def _recompute_summary(ledger: dict[str, object]) -> dict[str, object]:
    by_target: dict[str, dict[str, int]] = {}
    for request in ledger.get("requests", []):
        key = str(int(request["target_contest"]))
        target = by_target.setdefault(key, {"requests": 0, "operator_frozen_cards": 0})
        target["requests"] += 1
        target["operator_frozen_cards"] += int(request["generated_card_count"])
    return {"by_target": by_target}


def validate_operator_card_ledger(ledger: dict[str, object]) -> dict[str, object]:
    if int(ledger.get("schema_version", 0)) != 2:
        raise RuntimeError("OPERATOR_CARD_LEDGER_SCHEMA_MISMATCH")
    if ledger.get("policy") != _policy():
        raise RuntimeError("OPERATOR_CARD_POLICY_MISMATCH")

    seen_by_target: dict[int, set[tuple[int, ...]]] = {}
    next_index_by_target: dict[int, int] = {}
    idempotency_keys: set[str] = set()
    freeze_ids: set[str] = set()
    request_count = 0
    card_count = 0
    for request in ledger.get("requests", []):
        request_count += 1
        target = int(request["target_contest"])
        key = str(request.get("idempotency_key", "")).strip()
        if not key:
            raise RuntimeError("OPERATOR_CARD_IDEMPOTENCY_KEY_MISSING")
        if key in idempotency_keys:
            raise RuntimeError("OPERATOR_CARD_IDEMPOTENCY_KEY_DUPLICATE")
        idempotency_keys.add(key)
        expected_fingerprint = _request_fingerprint(
            target_contest=target,
            requested_card_count=int(request["requested_card_count"]),
            state_snapshot_hash=str(request["state_snapshot_hash"]),
            idempotency_key=key,
            state_data_snapshot_hash=(
                str(request["state_data_snapshot_hash"])
                if request.get("state_data_snapshot_hash") is not None
                else None
            ),
        )
        if request.get("request_fingerprint") != expected_fingerprint:
            raise RuntimeError("OPERATOR_CARD_REQUEST_FINGERPRINT_MISMATCH")
        expected_hash = _sha256(_request_hash_payload(request))
        if request.get("request_sha256") != expected_hash:
            raise RuntimeError("OPERATOR_CARD_REQUEST_HASH_MISMATCH")
        start = int(request["generation_index_start"])
        stop = int(request["generation_index_next"])
        if start != next_index_by_target.get(target, 0) or stop < start:
            raise RuntimeError("OPERATOR_CARD_GENERATION_CURSOR_MISMATCH")
        items = request.get("cards", [])
        if int(request["generated_card_count"]) != len(items):
            raise RuntimeError("OPERATOR_CARD_REQUEST_COUNT_MISMATCH")
        if int(request["requested_card_count"]) != len(items):
            raise RuntimeError("OPERATOR_CARD_REQUEST_NOT_FULFILLED")
        artifact_payload = request.get("card_artifact")
        if artifact_payload is not None:
            artifact = validate_card_artifact(
                artifact_payload,
                expected_status=STATUS_FROZEN,
                expected_cards=[item["card"] for item in items],
                require_operational=True,
            )
            if artifact.policy_id != POLICY_OPERATOR or artifact.target_contest != target:
                raise RuntimeError("OPERATOR_CARD_ARTIFACT_POLICY_MISMATCH")
            if request.get("state_data_snapshot_hash") is not None and (
                artifact.data_snapshot_hash != str(request["state_data_snapshot_hash"])
            ):
                raise RuntimeError("OPERATOR_CARD_ARTIFACT_DATA_SNAPSHOT_MISMATCH")
            if artifact.storage_snapshot_hash != str(request["state_snapshot_hash"]):
                raise RuntimeError("OPERATOR_CARD_ARTIFACT_STORAGE_SNAPSHOT_MISMATCH")
        seen = seen_by_target.setdefault(target, set())
        for item in items:
            index = int(item["generation_index"])
            if not start <= index < stop:
                raise RuntimeError("OPERATOR_CARD_GENERATION_INDEX_MISMATCH")
            card = normalize_numbers(item["card"])
            if card != card_for_generation_index(target, index):
                raise RuntimeError("OPERATOR_CARD_GENERATION_PROOF_MISMATCH")
            payload_hash = card_sha256(card)
            if item.get("payload_hash") != payload_hash or item.get("card_sha256") != payload_hash:
                raise RuntimeError("OPERATOR_CARD_HASH_MISMATCH")
            if card in seen:
                raise RuntimeError("OPERATOR_CARD_DUPLICATE_FOR_TARGET")
            seen.add(card)
            required = (
                "freeze_id",
                "type",
                "created_at_utc",
                "source_commit",
                "workflow_run_id",
                "model_identity",
                "config_identity",
                "state_ref",
                "idempotency_key",
            )
            if any(not str(item.get(field, "")).strip() for field in required):
                raise RuntimeError("OPERATOR_CARD_FREEZE_PROVENANCE_MISSING")
            if item["type"] != FREEZE_TYPE or item["idempotency_key"] != key:
                raise RuntimeError("OPERATOR_CARD_FREEZE_IDENTITY_MISMATCH")
            freeze_payload = {
                "target_contest": target,
                "type": FREEZE_TYPE,
                "payload_hash": payload_hash,
                "generation_index": index,
                "idempotency_key": key,
            }
            expected_freeze_id = "freeze-" + _sha256(freeze_payload)[:32]
            if item["freeze_id"] != expected_freeze_id:
                raise RuntimeError("OPERATOR_CARD_FREEZE_ID_MISMATCH")
            if item["freeze_id"] in freeze_ids:
                raise RuntimeError("OPERATOR_CARD_FREEZE_ID_DUPLICATE")
            freeze_ids.add(str(item["freeze_id"]))
            card_count += 1
        next_index_by_target[target] = stop

    if ledger.get("summary") != _recompute_summary(ledger):
        raise RuntimeError("OPERATOR_CARD_SUMMARY_MISMATCH")
    return {
        "status": "OPERATOR_CARD_LEDGER_PASS",
        "requests": request_count,
        "operator_frozen_cards": card_count,
        "targets": len(seen_by_target),
    }


def _result_for_request(
    ledger: dict[str, object], request: dict[str, object], reserved: set[tuple[int, ...]], *, replay: bool
) -> dict[str, object]:
    target = int(request["target_contest"])
    operator_total = len(_operator_cards_for_target(ledger, target))
    cards = [item["card"] for item in request["cards"]]
    return {
        "status": "GITHUB_OPERATOR_CARD_FREEZE_IDEMPOTENT_REPLAY" if replay else "GITHUB_OPERATOR_CARD_FREEZE_PASS",
        "target_contest": target,
        "requested_card_count": int(request["requested_card_count"]),
        "generated_card_count": 0 if replay else len(cards),
        "replayed_freeze_count": len(cards) if replay else 0,
        "operator_frozen_cards_for_target": operator_total,
        "reserved_frozen_cards_for_target": len(reserved),
        "total_distinct_frozen_cards_for_target": len(_operator_cards_for_target(ledger, target) | reserved),
        "cost_cents_this_request": (0 if replay else len(cards) * DEFAULT_RULES.simple_bet_cost_cents),
        "evidence_label": UNPROVEN_LABEL,
        "request_sha256": request["request_sha256"],
        "request_fingerprint": request["request_fingerprint"],
        "idempotency_key": request["idempotency_key"],
        "freeze_ids": [item["freeze_id"] for item in request["cards"]],
        "artifact_status": (
            request["card_artifact"]["status"]
            if isinstance(request.get("card_artifact"), dict)
            else "LEGACY_FROZEN"
        ),
        "card_artifact": request.get("card_artifact"),
        "cards": cards,
        "cards_display": [" ".join(f"{number:02d}" for number in card) for card in cards],
    }


def freeze_operator_cards(
    ledger: dict[str, object],
    *,
    target_contest: int,
    requested_card_count: int,
    state_snapshot_hash: str,
    created_at_utc: str,
    idempotency_key: str,
    source_commit: str,
    workflow_run_id: str,
    state_data_snapshot_hash: str | None = None,
    state_snapshot_id: str | None = None,
    state_ref: str = "operations/state",
    model_identity: str = "COMBINATORIAL_UNIFORM_DETERMINISTIC",
    config_identity: str = POLICY_NAME,
    reserved_cards: Sequence[Iterable[int]] = (),
) -> tuple[dict[str, object], dict[str, object]]:
    if not 1 <= requested_card_count <= MAX_CARDS_PER_REQUEST:
        raise ValueError(
            f"requested_card_count deve estar entre 1 e {MAX_CARDS_PER_REQUEST}"
        )
    key = idempotency_key.strip()
    if not key:
        raise ValueError("idempotency_key obrigatório")
    validate_operator_card_ledger(ledger)

    fingerprint = _request_fingerprint(
        target_contest=target_contest,
        requested_card_count=requested_card_count,
        state_snapshot_hash=state_snapshot_hash,
        idempotency_key=key,
        state_data_snapshot_hash=state_data_snapshot_hash,
    )
    reserved = {normalize_numbers(card) for card in reserved_cards}
    for prior in ledger["requests"]:
        if prior["idempotency_key"] != key:
            continue
        if prior["request_fingerprint"] != fingerprint:
            raise RuntimeError("OPERATOR_CARD_IDEMPOTENCY_CONFLICT")
        return ledger, _result_for_request(ledger, prior, reserved, replay=True)

    requests = ledger["requests"]
    existing = _operator_cards_for_target(ledger, target_contest)
    occupied = existing | reserved
    remaining = COMBINATION_SPACE - len(occupied)
    if requested_card_count > remaining:
        raise RuntimeError("OPERATOR_CARD_COMBINATION_SPACE_EXHAUSTED")

    previous = [item for item in requests if int(item["target_contest"]) == target_contest]
    cursor = int(previous[-1]["generation_index_next"]) if previous else 0
    start = cursor
    generated: list[dict[str, object]] = []
    attempts = 0
    started = time.monotonic()
    while len(generated) < requested_card_count:
        if cursor >= COMBINATION_SPACE:
            raise RuntimeError("OPERATOR_CARD_COMBINATION_SPACE_EXHAUSTED")
        if attempts >= MAX_GENERATION_ATTEMPTS:
            raise ResourceLimitError(
                "OPERATOR_CARD_GENERATION_ATTEMPTS_LIMIT_EXCEEDED "
                f"attempts={attempts} limit={MAX_GENERATION_ATTEMPTS}"
            )
        require_runtime(started)
        attempts += 1
        card = card_for_generation_index(target_contest, cursor)
        generation_index = cursor
        cursor += 1
        if card in occupied:
            continue
        occupied.add(card)
        payload_hash = card_sha256(card)
        freeze_payload = {
            "target_contest": int(target_contest),
            "type": FREEZE_TYPE,
            "payload_hash": payload_hash,
            "generation_index": generation_index,
            "idempotency_key": key,
        }
        generated.append(
            {
                "freeze_id": "freeze-" + _sha256(freeze_payload)[:32],
                "target_contest": int(target_contest),
                "type": FREEZE_TYPE,
                "generation_index": generation_index,
                "card": list(card),
                "payload_hash": payload_hash,
                "card_sha256": payload_hash,
                "created_at_utc": created_at_utc,
                "source_commit": source_commit,
                "workflow_run_id": workflow_run_id,
                "model_identity": model_identity,
                "config_identity": config_identity,
                "state_ref": state_ref,
                "idempotency_key": key,
            }
        )

    request = {
        "target_contest": int(target_contest),
        "created_at_utc": created_at_utc,
        "request_sequence": len(previous) + 1,
        "idempotency_key": key,
        "request_fingerprint": fingerprint,
        "requested_card_count": int(requested_card_count),
        "generated_card_count": len(generated),
        "generation_index_start": start,
        "generation_index_next": cursor,
        "state_snapshot_hash": state_snapshot_hash,
        "source_commit": source_commit,
        "workflow_run_id": workflow_run_id,
        "state_ref": state_ref,
        "model_identity": model_identity,
        "config_identity": config_identity,
        "evidence_label": UNPROVEN_LABEL,
        "cards": generated,
    }
    if state_data_snapshot_hash is not None:
        request["state_data_snapshot_hash"] = state_data_snapshot_hash
    artifact = CardGenerationService.freeze_operator_batch(
        cards=[item["card"] for item in generated],
        target_contest=target_contest,
        data_snapshot_hash=state_data_snapshot_hash,
        storage_snapshot_id=state_snapshot_id,
        storage_snapshot_hash=state_snapshot_hash,
        request_fingerprint=fingerprint,
    )
    request["card_artifact"] = artifact.to_dict()
    request["request_sha256"] = _sha256(_request_hash_payload(request))
    require_runtime(started)
    require_artifact_size(request)
    requests.append(request)
    ledger["summary"] = _recompute_summary(ledger)
    validate_operator_card_ledger(ledger)
    return ledger, _result_for_request(ledger, request, reserved, replay=False)
