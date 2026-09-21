from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sare_lotofacil.persistence.db import initialize_database
from sare_lotofacil.persistence.jobs import (
    StaleLeaseError,
    claim_next_job,
    complete_job,
    enqueue_job,
    renew_lease,
)
from sare_lotofacil.persistence.operations import (
    complete_idempotency,
    payload_hash,
    reserve_idempotency,
)


def prove(work_dir: Path) -> dict[str, object]:
    work_dir.mkdir(parents=True, exist_ok=True)
    db = work_dir / "f4-proof.db"
    db.unlink(missing_ok=True)
    initialize_database(db)

    digest = payload_hash({"operation": "effect", "value": 1})
    barrier = threading.Barrier(16)

    def reserve():
        barrier.wait()
        return reserve_idempotency(db, "F4_PROOF", "shared-key", digest)

    with ThreadPoolExecutor(max_workers=16) as pool:
        reservations = list(pool.map(lambda _: reserve(), range(16)))

    acquired = [item for item in reservations if item.outcome == "ACQUIRED"]
    in_progress = [item for item in reservations if item.outcome == "IN_PROGRESS"]
    if len(acquired) != 1 or len(in_progress) != 15:
        raise RuntimeError(
            f"idempotency ownership failure: acquired={len(acquired)} in_progress={len(in_progress)}"
        )
    owner = acquired[0]
    complete_idempotency(
        db,
        "F4_PROOF",
        "shared-key",
        digest,
        int(owner.reservation_token),
        {"effect_count": 1},
        201,
    )
    replay = reserve_idempotency(db, "F4_PROOF", "shared-key", digest)
    if replay.outcome != "REPLAY":
        raise RuntimeError(f"idempotency replay failure: {replay.outcome}")
    conflict = reserve_idempotency(
        db,
        "F4_PROOF",
        "shared-key",
        payload_hash({"operation": "effect", "value": 2}),
    )
    if conflict.outcome != "CONFLICT":
        raise RuntimeError(f"idempotency conflict failure: {conflict.outcome}")

    t0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    renewed_job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 401})
    lease_a = claim_next_job(db, "worker-a", lease_seconds=30, now=t0)
    if lease_a is None:
        raise RuntimeError("worker-a failed to claim renewal proof job")
    renewed = renew_lease(
        db,
        renewed_job.job_id,
        "worker-a",
        lease_a.lease_token,
        lease_seconds=30,
        now=t0 + timedelta(seconds=20),
    )
    if renewed.lease_token != lease_a.lease_token:
        raise RuntimeError("lease renewal changed fencing token")
    if claim_next_job(
        db,
        "worker-b",
        lease_seconds=30,
        now=t0 + timedelta(seconds=31),
    ) is not None:
        raise RuntimeError("renewed live lease was reclaimed")
    complete_job(
        db,
        renewed_job.job_id,
        "worker-a",
        lease_a.lease_token,
        {"renewed": True},
        now=t0 + timedelta(seconds=40),
    )

    stale_job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 402})
    first = claim_next_job(db, "worker-a", lease_seconds=5, now=t0)
    if first is None:
        raise RuntimeError("worker-a failed to claim fencing proof job")
    second = claim_next_job(
        db,
        "worker-b",
        lease_seconds=5,
        now=t0 + timedelta(seconds=6),
    )
    if second is None or second.lease_token != first.lease_token + 1:
        raise RuntimeError("expired lease was not reclaimed with a new fencing token")
    stale_blocked = False
    try:
        complete_job(
            db,
            stale_job.job_id,
            "worker-a",
            first.lease_token,
            {"stale": True},
            now=t0 + timedelta(seconds=6),
        )
    except StaleLeaseError:
        stale_blocked = True
    if not stale_blocked:
        raise RuntimeError("stale worker completed after fencing token changed")
    completed = complete_job(
        db,
        stale_job.job_id,
        "worker-b",
        second.lease_token,
        {"fenced": True},
        now=t0 + timedelta(seconds=6),
    )
    if completed.state != "COMPLETED":
        raise RuntimeError("current fenced worker failed to complete")

    return {
        "status": "F4_CONCURRENCY_FENCING_PASS",
        "idempotency": {
            "contenders": 16,
            "acquired": 1,
            "in_progress": 15,
            "replay": True,
            "conflict": True,
        },
        "leases": {
            "renewal_preserved_token": True,
            "renewed_lease_not_reclaimed": True,
            "reclaim_incremented_token": True,
            "stale_completion_blocked": True,
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
