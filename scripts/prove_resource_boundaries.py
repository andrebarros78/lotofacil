from __future__ import annotations

import json
from pathlib import Path

from sare_lotofacil.persistence.jobs import enqueue_job
from sare_lotofacil.portfolios.authority import build_card_artifact
from sare_lotofacil.portfolios.core import generate_uniform_portfolio
from sare_lotofacil.portfolios.frozen import (
    card_for_generation_index,
    empty_operator_card_ledger,
    freeze_operator_cards,
)
from sare_lotofacil.resource_limits import (
    MAX_ARTIFACT_BYTES,
    MAX_CARDS_PER_REQUEST,
    MAX_GENERATION_ATTEMPTS,
    MAX_JOB_ATTEMPTS,
    MAX_JOB_PAYLOAD_BYTES,
    MAX_OPERATOR_CARDS_PER_REQUEST,
    MAX_PENDING_JOBS,
    MAX_REQUEST_BODY_BYTES,
    MAX_RUNTIME_SECONDS,
    ResourceLimitError,
)


def prove(work_dir: Path) -> dict[str, object]:
    work_dir.mkdir(parents=True, exist_ok=True)

    maximum = generate_uniform_portfolio(MAX_CARDS_PER_REQUEST, seed=20260921)
    if len(maximum.cards) != MAX_CARDS_PER_REQUEST:
        raise RuntimeError("MAX_CARD_GENERATION_COUNT_MISMATCH")
    if len(set(maximum.cards)) != MAX_CARDS_PER_REQUEST:
        raise RuntimeError("MAX_CARD_GENERATION_DUPLICATE")

    cardinality_blocked = False
    try:
        generate_uniform_portfolio(MAX_CARDS_PER_REQUEST + 1, seed=1)
    except ValueError:
        cardinality_blocked = True
    if not cardinality_blocked:
        raise RuntimeError("MAX_CARD_LIMIT_NOT_ENFORCED")

    artifact_blocked = False
    try:
        build_card_artifact(
            status="PREVIEW",
            policy_id="F5_PROOF",
            policy_version="1",
            cards=(range(1, 16),),
            metadata={"oversized": "x" * (MAX_ARTIFACT_BYTES + 1)},
        )
    except ResourceLimitError:
        artifact_blocked = True
    if not artifact_blocked:
        raise RuntimeError("MAX_ARTIFACT_BYTES_NOT_ENFORCED")

    ledger = empty_operator_card_ledger()
    reserved = tuple(
        card_for_generation_index(3785, index)
        for index in range(MAX_GENERATION_ATTEMPTS)
    )
    attempts_blocked = False
    try:
        freeze_operator_cards(
            ledger,
            target_contest=3785,
            requested_card_count=1,
            state_snapshot_hash="f5-proof-storage",
            created_at_utc="2026-09-21T17:00:00+00:00",
            idempotency_key="f5-attempt-bound",
            source_commit="F5_PROOF",
            workflow_run_id="F5_PROOF",
            reserved_cards=reserved,
        )
    except ResourceLimitError:
        attempts_blocked = True
    if not attempts_blocked or ledger["requests"]:
        raise RuntimeError("OPERATOR_GENERATION_BOUNDARY_NOT_ATOMIC")

    db = work_dir / "f5-resource-boundaries.db"
    db.unlink(missing_ok=True)
    first = None
    for seed in range(MAX_PENDING_JOBS):
        record = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": seed})
        first = first or record

    queue_blocked = False
    try:
        enqueue_job(
            db,
            "PORTFOLIO",
            {"card_count": 1, "seed": MAX_PENDING_JOBS + 1},
        )
    except ResourceLimitError:
        queue_blocked = True
    if not queue_blocked:
        raise RuntimeError("MAX_PENDING_JOBS_NOT_ENFORCED")

    if first is None:
        raise RuntimeError("QUEUE_PROOF_DID_NOT_CREATE_FIRST_JOB")
    replay = enqueue_job(db, "PORTFOLIO", first.payload)
    if replay.job_id != first.job_id:
        raise RuntimeError("QUEUE_LIMIT_BROKE_IDEMPOTENT_DUPLICATE")

    return {
        "status": "RESOURCE_BOUNDARY_PROOF_PASS",
        "limits": {
            "MAX_CARDS_PER_REQUEST": MAX_CARDS_PER_REQUEST,
            "MAX_GENERATION_ATTEMPTS": MAX_GENERATION_ATTEMPTS,
            "MAX_RUNTIME_SECONDS": MAX_RUNTIME_SECONDS,
            "MAX_ARTIFACT_BYTES": MAX_ARTIFACT_BYTES,
            "MAX_REQUEST_BODY_BYTES": MAX_REQUEST_BODY_BYTES,
            "MAX_PENDING_JOBS": MAX_PENDING_JOBS,
            "MAX_OPERATOR_CARDS_PER_REQUEST": MAX_OPERATOR_CARDS_PER_REQUEST,
            "MAX_JOB_PAYLOAD_BYTES": MAX_JOB_PAYLOAD_BYTES,
            "MAX_JOB_ATTEMPTS": MAX_JOB_ATTEMPTS,
        },
        "proof": {
            "maximum_card_generation": True,
            "cardinality_overflow_blocked": cardinality_blocked,
            "oversized_artifact_blocked": artifact_blocked,
            "operator_attempt_exhaustion_blocked_without_ledger_mutation": attempts_blocked,
            "pending_queue_saturation_blocked": queue_blocked,
            "duplicate_job_allowed_at_queue_capacity": True,
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    result = prove(args.work_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
