from datetime import datetime, timedelta, timezone
import threading
import time

import pytest

from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.jobs import (
    StaleLeaseError,
    claim_next_job,
    complete_job,
    enqueue_job,
    get_job,
    renew_lease,
    request_cancel,
    run_worker_once,
    save_checkpoint,
)


def test_fencing_token_blocks_stale_worker(tmp_path):
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 7})
    t0 = datetime(2026, 9, 11, tzinfo=timezone.utc)
    first = claim_next_job(db, "worker-a", lease_seconds=30, now=t0)
    assert first and first.job_id == job.job_id and first.lease_token == 1
    second = claim_next_job(db, "worker-b", lease_seconds=30, now=t0 + timedelta(seconds=31))
    assert second and second.lease_token == 2 and second.attempts == 2
    with pytest.raises(StaleLeaseError):
        complete_job(db, job.job_id, "worker-a", first.lease_token, {"invalid": True})
    completed = complete_job(db, job.job_id, "worker-b", second.lease_token, {"ok": True})
    assert completed.state == "COMPLETED"
    assert completed.result == {"ok": True}


def test_renew_lease_prevents_premature_reclaim(tmp_path):
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 71})
    t0 = datetime(2026, 9, 11, tzinfo=timezone.utc)
    first = claim_next_job(db, "worker-a", lease_seconds=10, now=t0)
    assert first is not None
    renewed_until = renew_lease(
        db,
        job.job_id,
        "worker-a",
        first.lease_token,
        lease_seconds=10,
        now=t0 + timedelta(seconds=8),
    )
    assert renewed_until == (t0 + timedelta(seconds=18)).isoformat()
    assert claim_next_job(db, "worker-b", lease_seconds=10, now=t0 + timedelta(seconds=11)) is None
    reclaimed = claim_next_job(db, "worker-b", lease_seconds=10, now=t0 + timedelta(seconds=19))
    assert reclaimed is not None and reclaimed.lease_token == 2


def test_worker_heartbeat_keeps_lease_during_long_payload(monkeypatch, tmp_path):
    import sare_lotofacil.persistence.jobs as jobs_module

    db = tmp_path / "sare.db"
    queued = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 72})
    original_execute = jobs_module._execute_payload

    def slow_execute(path, job):
        time.sleep(1.2)
        return original_execute(path, job)

    monkeypatch.setattr(jobs_module, "_execute_payload", slow_execute)
    result_holder = []
    errors = []

    def run_owner():
        try:
            result_holder.append(run_worker_once(db, "worker-owner", lease_seconds=0.6))
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_owner)
    thread.start()
    deadline = time.monotonic() + 2.0
    initial_expiry = None
    while time.monotonic() < deadline:
        current = get_job(db, queued.job_id)
        if current.state == "LEASED" and current.lease_expires_at:
            initial_expiry = current.lease_expires_at
            break
        time.sleep(0.01)
    else:
        pytest.fail("owner did not lease job")

    renewal_deadline = time.monotonic() + 1.0
    renewed = None
    while time.monotonic() < renewal_deadline:
        current = get_job(db, queued.job_id)
        if current.lease_expires_at and current.lease_expires_at != initial_expiry:
            renewed = current.lease_expires_at
            break
        time.sleep(0.02)
    assert renewed is not None, "heartbeat did not renew lease"

    original_expiry = datetime.fromisoformat(initial_expiry)
    renewed_expiry = datetime.fromisoformat(renewed)
    assert renewed_expiry > original_expiry
    contender_time = original_expiry + timedelta(milliseconds=10)
    assert contender_time < renewed_expiry
    contender = claim_next_job(db, "worker-contender", lease_seconds=1, now=contender_time)
    assert contender is None

    thread.join(timeout=3.0)
    assert not thread.is_alive()
    assert errors == []
    assert result_holder and result_holder[0] is not None
    assert result_holder[0].state == "COMPLETED"
    assert result_holder[0].attempts == 1


def test_worker_restart_reclaims_job_without_duplicate_domain_result(tmp_path):
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 17})
    t0 = datetime(2026, 9, 11, tzinfo=timezone.utc)
    first = claim_next_job(db, "worker-a", lease_seconds=5, now=t0)
    assert first
    save_checkpoint(db, job.job_id, "worker-a", first.lease_token, {"phase": "CLAIMED"})

    recovered = run_worker_once(db, "worker-b", lease_seconds=30, now=t0 + timedelta(seconds=6))
    assert recovered and recovered.state == "COMPLETED" and recovered.attempts == 2
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0] == 1
        checkpoint = connection.execute(
            "SELECT lease_token, checkpoint_json FROM job_checkpoints WHERE job_id=?", (job.job_id,)
        ).fetchone()
    assert checkpoint[0] == 2
    assert '"phase":"COMPUTED"' in checkpoint[1]


def test_cancel_never_publishes_partial_result(tmp_path):
    db = tmp_path / "sare.db"
    queued = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 1})
    cancelled = request_cancel(db, queued.job_id)
    assert cancelled.state == "CANCELLED" and cancelled.result is None

    leased = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 2})
    t0 = datetime(2026, 9, 11, tzinfo=timezone.utc)
    claimed = claim_next_job(db, "worker-a", lease_seconds=30, now=t0)
    assert claimed and claimed.job_id == leased.job_id
    requested = request_cancel(db, leased.job_id)
    assert requested.cancel_requested is True and requested.state == "LEASED"
    final = complete_job(db, leased.job_id, "worker-a", claimed.lease_token, {"must_not_publish": True})
    assert final.state == "CANCELLED" and final.result is None


def test_schema_upgrade_preserves_existing_records(tmp_path):
    db = tmp_path / "sare.db"
    initialize_database(db)
    with connect(db) as connection:
        connection.execute("INSERT INTO schema_meta(key, value) VALUES('fixture', 'preserve-me')")
        connection.execute("UPDATE schema_meta SET value='4' WHERE key='schema_version'")
    initialize_database(db)
    with connect(db) as connection:
        assert connection.execute("SELECT value FROM schema_meta WHERE key='fixture'").fetchone()[0] == "preserve-me"
        assert connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == "5"


def test_disk_full_like_failure_never_publishes_completion(monkeypatch, tmp_path):
    import sqlite3
    import sare_lotofacil.persistence.jobs as jobs_module

    db = tmp_path / "sare.db"
    queued = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 404})

    def raise_disk_full(*_args, **_kwargs):
        raise sqlite3.OperationalError("database or disk is full")

    monkeypatch.setattr(jobs_module, "_execute_payload", raise_disk_full)
    failed = run_worker_once(db, "worker-disk-full", lease_seconds=30)
    assert failed is not None and failed.job_id == queued.job_id
    assert failed.state == "FAILED"
    assert failed.result is None
    assert failed.error is not None
    assert failed.error["type"] == "OperationalError"
    assert "disk is full" in failed.error["message"]
