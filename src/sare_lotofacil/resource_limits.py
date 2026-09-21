from __future__ import annotations

import json
import time
from typing import Any

MAX_CARDS_PER_REQUEST = 100
MAX_OPERATOR_CARDS_PER_REQUEST = 200
MAX_CARD_ARTIFACT_CARDS = MAX_OPERATOR_CARDS_PER_REQUEST
MAX_GENERATION_ATTEMPTS = 1_000
MAX_RUNTIME_SECONDS = 30.0
MAX_ARTIFACT_BYTES = 131_072
MAX_REQUEST_BODY_BYTES = 65_536
MAX_PENDING_JOBS = 200
MAX_JOB_PAYLOAD_BYTES = 32_768
MAX_JOB_ATTEMPTS = 8


class ResourceLimitError(RuntimeError):
    """Raised when an operation would exceed a declared resource boundary."""


def canonical_size_bytes(payload: Any) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def require_artifact_size(payload: Any) -> int:
    size = canonical_size_bytes(payload)
    if size > MAX_ARTIFACT_BYTES:
        raise ResourceLimitError(
            f"ARTIFACT_BYTES_LIMIT_EXCEEDED observed={size} limit={MAX_ARTIFACT_BYTES}"
        )
    return size


def require_job_payload_size(payload: Any) -> int:
    size = canonical_size_bytes(payload)
    if size > MAX_JOB_PAYLOAD_BYTES:
        raise ResourceLimitError(
            f"JOB_PAYLOAD_BYTES_LIMIT_EXCEEDED observed={size} limit={MAX_JOB_PAYLOAD_BYTES}"
        )
    return size


def require_runtime(started_monotonic: float, *, now_monotonic: float | None = None) -> None:
    current = time.monotonic() if now_monotonic is None else now_monotonic
    elapsed = current - started_monotonic
    if elapsed > MAX_RUNTIME_SECONDS:
        raise ResourceLimitError(
            f"RUNTIME_LIMIT_EXCEEDED elapsed={elapsed:.6f} limit={MAX_RUNTIME_SECONDS:.6f}"
        )
