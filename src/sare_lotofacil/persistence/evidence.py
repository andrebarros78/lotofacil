from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from sare_lotofacil.persistence.db import connect


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    artifact_id: str
    expected_sha256: str
    actual_sha256: str | None
    valid: bool
    error: str | None = None


def _actual_digest(raw_json: str) -> str:
    try:
        envelope = json.loads(raw_json)
    except json.JSONDecodeError:
        return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()
    if isinstance(envelope, dict) and envelope.get("encoding") == "base64" and "raw_base64" in envelope:
        raw = base64.b64decode(envelope["raw_base64"], validate=True)
        return hashlib.sha256(raw).hexdigest()
    return hashlib.sha256(raw_json.encode("utf-8")).hexdigest()


def verify_source_artifacts(path: str | Path) -> tuple[EvidenceCheck, ...]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT artifact_id, sha256, raw_json FROM source_artifacts ORDER BY artifact_id"
        ).fetchall()
    checks = []
    for artifact_id, expected, raw_json in rows:
        try:
            actual = _actual_digest(raw_json)
            checks.append(EvidenceCheck(artifact_id, expected, actual, actual == expected, None))
        except Exception as exc:
            checks.append(EvidenceCheck(artifact_id, expected, None, False, f"{type(exc).__name__}: {exc}"))
    return tuple(checks)
