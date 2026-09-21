from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from sare_lotofacil.persistence.operations import (
    complete_idempotency,
    get_idempotency,
    payload_hash,
    reserve_idempotency,
)


def execute_idempotent(
    path: str | Path,
    operation: str,
    key: str | None,
    request_payload: dict[str, Any],
    callback: Callable[[], tuple[dict[str, Any], int]],
) -> JSONResponse:
    if key is None or not key.strip():
        raise HTTPException(status_code=400, detail="IDEMPOTENCY_KEY_REQUIRED")
    if len(key) > 128:
        raise HTTPException(status_code=400, detail="IDEMPOTENCY_KEY_TOO_LONG")

    digest = payload_hash(request_payload)
    reservation = reserve_idempotency(path, operation, key, digest)
    if reservation.outcome == "CONFLICT":
        raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_CONFLICT")
    if reservation.outcome == "IN_PROGRESS":
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            record = get_idempotency(path, operation, key)
            if record is not None and record.state == "COMPLETED":
                if record.response_json is None or record.status_code is None:
                    raise RuntimeError("IDEMPOTENCY_REPLAY_MISSING_RESPONSE")
                return JSONResponse(
                    json.loads(record.response_json),
                    status_code=record.status_code,
                    headers={"Idempotency-Replayed": "true"},
                )
            time.sleep(0.01)
        return JSONResponse(
            {"detail": "IDEMPOTENCY_IN_PROGRESS"},
            status_code=409,
            headers={"Retry-After": "1"},
        )
    if reservation.outcome == "REPLAY":
        if reservation.response_json is None or reservation.status_code is None:
            raise RuntimeError("IDEMPOTENCY_REPLAY_MISSING_RESPONSE")
        return JSONResponse(
            json.loads(reservation.response_json),
            status_code=reservation.status_code,
            headers={"Idempotency-Replayed": "true"},
        )
    if reservation.outcome != "ACQUIRED" or reservation.reservation_token is None:
        raise RuntimeError("IDEMPOTENCY_RESERVATION_INVALID")

    token = reservation.reservation_token
    try:
        response_payload, status_code = callback()
    except HTTPException as exc:
        failure_payload = {"detail": exc.detail}
        complete_idempotency(
            path,
            operation,
            key,
            digest,
            token,
            failure_payload,
            exc.status_code,
        )
        raise
    except Exception as exc:
        complete_idempotency(
            path,
            operation,
            key,
            digest,
            token,
            {
                "detail": "IDEMPOTENCY_EFFECT_FAILED",
                "error_type": type(exc).__name__,
            },
            500,
        )
        raise

    complete_idempotency(
        path,
        operation,
        key,
        digest,
        token,
        response_payload,
        status_code,
    )
    return JSONResponse(response_payload, status_code=status_code)
