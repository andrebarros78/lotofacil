from __future__ import annotations

import hashlib
import json
import math
from typing import Iterable, Sequence

from sare_lotofacil.domain.masks import normalize_numbers
from sare_lotofacil.domain.rules import DEFAULT_RULES
from sare_lotofacil.portfolios.core import UNPROVEN_LABEL

POLICY_NAME = "operator-multi-freeze-v1"
NUMBER_MIN = 1
NUMBER_MAX = 25
CARD_SIZE = 15
COMBINATION_SPACE = math.comb(NUMBER_MAX, CARD_SIZE)


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
    }


def empty_operator_card_ledger() -> dict[str, object]:
    return {
        "schema_version": 1,
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
    if target_contest <= 0:
        raise ValueError("target_contest deve ser positivo")
    if not 0 <= generation_index < COMBINATION_SPACE:
        raise ValueError("generation_index fora do espaço combinatório")
    offset, step = _permutation_parameters(target_contest)
    rank = (offset + generation_index * step) % COMBINATION_SPACE
    return _unrank_combination(rank)


def card_sha256(card: Iterable[int]) -> str:
    normalized = normalize_numbers(card)
    return _sha256(list(normalized))


def _request_hash_payload(request: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in request.items() if key != "request_sha256"}


def _operator_cards_for_target(ledger: dict[str, object], target_contest: int) -> set[tuple[int, ...]]:
    cards: set[tuple[int, ...]] = set()
    for request in ledger.get("requests", []):
        if int(request["target_contest"]) != target_contest:
            continue
        for item in request.get("cards", []):
            cards.add(normalize_numbers(item["card"]))
    return cards


def _recompute_summary(ledger: dict[str, object]) -> dict[str, object]:
    by_target: dict[str, dict[str, int]] = {}
    for request in ledger.get("requests", []):
        key = str(int(request["target_contest"]))
        target = by_target.setdefault(key, {"requests": 0, "operator_frozen_cards": 0})
        target["requests"] += 1
        target["operator_frozen_cards"] += int(request["generated_card_count"])
    return {"by_target": by_target}


def validate_operator_card_ledger(ledger: dict[str, object]) -> dict[str, object]:
    if int(ledger.get("schema_version", 0)) != 1:
        raise RuntimeError("OPERATOR_CARD_LEDGER_SCHEMA_MISMATCH")
    if ledger.get("policy") != _policy():
        raise RuntimeError("OPERATOR_CARD_POLICY_MISMATCH")

    seen_by_target: dict[int, set[tuple[int, ...]]] = {}
    next_index_by_target: dict[int, int] = {}
    request_count = 0
    card_count = 0
    for request in ledger.get("requests", []):
        request_count += 1
        target = int(request["target_contest"])
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
        seen = seen_by_target.setdefault(target, set())
        for item in items:
            index = int(item["generation_index"])
            if not start <= index < stop:
                raise RuntimeError("OPERATOR_CARD_GENERATION_INDEX_MISMATCH")
            card = normalize_numbers(item["card"])
            if card != card_for_generation_index(target, index):
                raise RuntimeError("OPERATOR_CARD_GENERATION_PROOF_MISMATCH")
            if item.get("card_sha256") != card_sha256(card):
                raise RuntimeError("OPERATOR_CARD_HASH_MISMATCH")
            if card in seen:
                raise RuntimeError("OPERATOR_CARD_DUPLICATE_FOR_TARGET")
            seen.add(card)
            card_count += 1
        next_index_by_target[target] = stop

    expected_summary = _recompute_summary(ledger)
    if ledger.get("summary") != expected_summary:
        raise RuntimeError("OPERATOR_CARD_SUMMARY_MISMATCH")
    return {
        "status": "OPERATOR_CARD_LEDGER_PASS",
        "requests": request_count,
        "operator_frozen_cards": card_count,
        "targets": len(seen_by_target),
    }


def freeze_operator_cards(
    ledger: dict[str, object],
    *,
    target_contest: int,
    requested_card_count: int,
    state_snapshot_hash: str,
    created_at_utc: str,
    reserved_cards: Sequence[Iterable[int]] = (),
) -> tuple[dict[str, object], dict[str, object]]:
    if requested_card_count <= 0:
        raise ValueError("requested_card_count deve ser positivo")
    validate_operator_card_ledger(ledger)

    requests = ledger["requests"]
    existing = _operator_cards_for_target(ledger, target_contest)
    reserved = {normalize_numbers(card) for card in reserved_cards}
    occupied = existing | reserved
    remaining = COMBINATION_SPACE - len(occupied)
    if requested_card_count > remaining:
        raise RuntimeError("OPERATOR_CARD_COMBINATION_SPACE_EXHAUSTED")

    previous = [item for item in requests if int(item["target_contest"]) == target_contest]
    cursor = int(previous[-1]["generation_index_next"]) if previous else 0
    start = cursor
    generated: list[dict[str, object]] = []
    while len(generated) < requested_card_count:
        if cursor >= COMBINATION_SPACE:
            raise RuntimeError("OPERATOR_CARD_COMBINATION_SPACE_EXHAUSTED")
        card = card_for_generation_index(target_contest, cursor)
        generation_index = cursor
        cursor += 1
        if card in occupied:
            continue
        occupied.add(card)
        generated.append(
            {
                "generation_index": generation_index,
                "card": list(card),
                "card_sha256": card_sha256(card),
            }
        )

    request = {
        "target_contest": int(target_contest),
        "created_at_utc": created_at_utc,
        "request_sequence": len(previous) + 1,
        "requested_card_count": int(requested_card_count),
        "generated_card_count": len(generated),
        "generation_index_start": start,
        "generation_index_next": cursor,
        "state_snapshot_hash": state_snapshot_hash,
        "evidence_label": UNPROVEN_LABEL,
        "cards": generated,
    }
    request["request_sha256"] = _sha256(_request_hash_payload(request))
    requests.append(request)
    ledger["summary"] = _recompute_summary(ledger)
    validate_operator_card_ledger(ledger)

    operator_total = len(_operator_cards_for_target(ledger, target_contest))
    total_distinct = len(_operator_cards_for_target(ledger, target_contest) | reserved)
    result = {
        "status": "GITHUB_OPERATOR_CARD_FREEZE_PASS",
        "target_contest": int(target_contest),
        "requested_card_count": int(requested_card_count),
        "generated_card_count": len(generated),
        "operator_frozen_cards_for_target": operator_total,
        "reserved_frozen_cards_for_target": len(reserved),
        "total_distinct_frozen_cards_for_target": total_distinct,
        "cost_cents_this_request": len(generated) * DEFAULT_RULES.simple_bet_cost_cents,
        "evidence_label": UNPROVEN_LABEL,
        "request_sha256": request["request_sha256"],
        "cards": [item["card"] for item in generated],
        "cards_display": [" ".join(f"{number:02d}" for number in item["card"]) for item in generated],
    }
    return ledger, result
