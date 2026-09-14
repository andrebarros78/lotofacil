from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

VOLATILE_KEYS = frozenset(
    {
        "run_id",
        "created_at",
        "created_at_utc",
        "updated_at",
        "updated_at_utc",
        "finished_at",
        "timestamp",
        "captured_at_utc",
        "workflow_run_id",
    }
)


def _normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _normalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize(item) for item in value)
    if isinstance(value, float):
        if value == 0.0:
            return 0.0
        return float(format(value, ".17g"))
    return value


def normalized_scientific_json(payload: Any) -> str:
    return json.dumps(
        _normalize(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@dataclass(frozen=True, slots=True)
class ScientificRunIdentity:
    seed: int
    data_hash: str
    code_commit: str
    environment_hash: str
    protocol_hash: str
    scientific_payload: Any

    @property
    def normalized_content(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "data_hash": self.data_hash,
            "code_commit": self.code_commit,
            "environment_hash": self.environment_hash,
            "protocol_hash": self.protocol_hash,
            "scientific_payload": _normalize(self.scientific_payload),
        }

    @property
    def normalized_json(self) -> str:
        return normalized_scientific_json(self.normalized_content)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.normalized_json.encode("utf-8")).hexdigest()
