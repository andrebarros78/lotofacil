from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from sare_lotofacil.api.idempotency import execute_idempotent
from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.jobs import (
    LeaseHeartbeat,
    StaleLeaseError,
    claim_next_job,
    complete_job,
    enqueue_job,
)
from sare_lotofacil.persistence.operations import (
    complete_idempotency,
    get_idempotency,
    payload_hash,
    reserve_idempotency,
)


def test_concurrent_idempotency_reservation_allows_one_owner(tmp_path) -> None:
    db = tmp_path / "sare.db"
    initialize_database(db)
    digest = payload_hash({"value": 1})
    barrier = threading.Barrier(12)

    def reserve():
        barrier.wait()
        return reserve_idempotency(db, "TEST", "same-key", digest)

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda _: reserve(), range(12)))

    acquired = [item for item in results if item.outcome == "ACQUIRED"]
    in_progress = [item for item in results if item.outcome == "IN_PROGRESS"]
    assert len(acquired) == 1
    assert len(in_progress) == 11

    owner = acquired[0]
    complete_idempotency(
        db,
        "TEST",
        "same-key",
        digest,
        int(owner.reservation_token),
        {"ok": True},
        201,
    )
    replay = reserve_idempotency(db, "TEST", "same-key", digest)
    assert replay.outcome == "REPLAY"
    assert replay.status_code == 201

    conflict = reserve_idempotency(db, "TEST", "same-key", payload_hash({"value": 2}))
    assert conflict.outcome == "CONFLICT"


def test_api_idempotent_executor_never_runs_concurrent_effect_twice(tmp_path) -> None:
    db = tmp_path / "sare.db"
    initialize_database(db)
    barrier = threading.Barrier(8)
    lock = threading.Lock()
    calls = 0

    def callback():
        nonlocal calls
        with lock:
            calls += 1
        time.sleep(0.15)
        return {"effect": "once"}, 201

    def invoke():
        barrier.wait()
        return execute_idempotent(
            db,
            "CREATE_TEST",
            "same-key",
            {"value": 1},
            callback,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        responses = list(pool.map(lambda _: invoke(), range(8)))

    assert calls == 1
    assert sum(response.status_code == 201 for response in responses) >= 1
    assert all(response.status_code in {201, 409} for response in responses)

    record = get_idempotency(db, "CREATE_TEST", "same-key")
    assert record is not None
    assert record.state == "COMPLETED"
    assert record.status_code == 201


def test_failed_effect_is_completed_fail_closed_and_not_reexecuted(tmp_path) -> None:
    db = tmp_path / "sare.db"
    initialize_database(db)
    calls = 0

    def callback():
        nonlocal calls
        calls += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        execute_idempotent(db, "FAIL_TEST", "same-key", {"x": 1}, callback)

    replay = execute_idempotent(
        db,
        "FAIL_TEST",
        "same-key",
        {"x": 1},
        callback,
    )
    assert replay.status_code == 500
    assert calls == 1


def test_heartbeat_keeps_live_worker_from_being_reclaimed(tmp_path) -> None:
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 88})
    lease_seconds = 3
    claimed = claim_next_job(db, "worker-a", lease_seconds=lease_seconds)
    assert claimed is not None

    heartbeat = LeaseHeartbeat(
        db,
        job.job_id,
        "worker-a",
        claimed.lease_token,
        lease_seconds=lease_seconds,
        interval_seconds=0.10,
    )
    heartbeat.start()
    try:
        time.sleep(3.25)
        heartbeat.ensure_valid()
        assert claim_next_job(db, "worker-b", lease_seconds=lease_seconds) is None
    finally:
        heartbeat.stop()
    heartbeat.ensure_valid()

    completed = complete_job(
        db,
        job.job_id,
        "worker-a",
        claimed.lease_token,
        {"ok": True},
    )
    assert completed.state == "COMPLETED"


def test_reclaimed_worker_token_fences_stale_completion(tmp_path) -> None:
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 99})
    t0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    first = claim_next_job(db, "worker-a", lease_seconds=5, now=t0)
    assert first is not None

    second = claim_next_job(
        db,
        "worker-b",
        lease_seconds=5,
        now=t0 + timedelta(seconds=6),
    )
    assert second is not None
    assert second.lease_token == first.lease_token + 1

    with pytest.raises(StaleLeaseError):
        complete_job(
            db,
            job.job_id,
            "worker-a",
            first.lease_token,
            {"stale": True},
            now=t0 + timedelta(seconds=6),
        )
    completed = complete_job(
        db,
        job.job_id,
        "worker-b",
        second.lease_token,
        {"ok": True},
        now=t0 + timedelta(seconds=6),
    )
    assert completed.state == "COMPLETED"

    with connect(db) as connection:
        row = connection.execute(
            "SELECT lease_owner, lease_token, lease_expires_at, lease_heartbeat_at "
            "FROM jobs WHERE job_id=?",
            (job.job_id,),
        ).fetchone()
    assert row[0] is None
    assert row[1] == second.lease_token
    assert row[2] is None
    assert row[3] is None
