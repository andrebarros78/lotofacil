from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from sare_lotofacil.ingestion.validation import ContestRecord, validate_contest

SEMANTIC_SNAPSHOT_SCHEMA = "lotofacil-data-snapshot-v1"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def semantic_snapshot_payload(records: Iterable[ContestRecord]) -> dict[str, object]:
    normalized: list[ContestRecord] = []
    seen: set[int] = set()
    for record in records:
        validated = validate_contest(record.contest_id, record.draw_date, record.numbers)
        if validated.mask != record.mask:
            raise ValueError(f"semantic snapshot mask mismatch for contest {record.contest_id}")
        if validated.contest_id in seen:
            raise ValueError(f"duplicate contest in semantic snapshot: {validated.contest_id}")
        seen.add(validated.contest_id)
        normalized.append(validated)

    if not normalized:
        raise ValueError("semantic snapshot requires at least one contest")

    normalized.sort(key=lambda item: item.contest_id)
    contests = [
        {
            "contest_id": record.contest_id,
            "draw_date": record.draw_date.isoformat(),
            "numbers": list(record.numbers),
        }
        for record in normalized
    ]
    return {
        "schema": SEMANTIC_SNAPSHOT_SCHEMA,
        "contest_count": len(contests),
        "contests": contests,
    }


def semantic_data_snapshot_hash(records: Iterable[ContestRecord]) -> str:
    payload = semantic_snapshot_payload(records)
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def semantic_data_snapshot_id(records: Iterable[ContestRecord]) -> str:
    digest = semantic_data_snapshot_hash(records)
    return f"data-{digest[:20]}"
