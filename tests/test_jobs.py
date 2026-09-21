from datetime import datetime, timedelta, timezone

import pytest

from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect, initialize_database
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
        complete_job(
            db,
            job.job_id,
            "worker-a",
            first.lease_token,
            {"invalid": True},
            now=t0 + timedelta(seconds=31),
        )
    completed = complete_job(
        db,
        job.job_id,
        "worker-b",
        second.lease_token,
        {"ok": True},
        now=t0 + timedelta(seconds=31),
    )
    assert completed.state == "COMPLETED"
    assert completed.result == {"ok": True}


def test_worker_restart_reclaims_job_without_duplicate_domain_result(tmp_path):
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 3, "seed": 17})
    t0 = datetime(2026, 9, 11, tzinfo=timezone.utc)
    first = claim_next_job(db, "worker-a", lease_seconds=5, now=t0)
    assert first
    save_checkpoint(
        db,
        job.job_id,
        "worker-a",
        first.lease_token,
        {"phase": "CLAIMED"},
        now=t0,
    )

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
    final = complete_job(
        db,
        leased.job_id,
        "worker-a",
        claimed.lease_token,
        {"must_not_publish": True},
        now=t0,
    )
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
        assert connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == str(SCHEMA_VERSION)


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

def test_expired_lease_cannot_checkpoint_complete_fail_or_renew(tmp_path):
    from sare_lotofacil.persistence.jobs import fail_job

    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 21})
    t0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    claimed = claim_next_job(db, "worker-a", lease_seconds=5, now=t0)
    assert claimed is not None
    expired = t0 + timedelta(seconds=6)

    with pytest.raises(StaleLeaseError, match="EXPIRED|STALE"):
        save_checkpoint(
            db,
            job.job_id,
            "worker-a",
            claimed.lease_token,
            {"phase": "LATE"},
            now=expired,
        )
    with pytest.raises(StaleLeaseError, match="EXPIRED|STALE"):
        renew_lease(
            db,
            job.job_id,
            "worker-a",
            claimed.lease_token,
            lease_seconds=5,
            now=expired,
        )
    with pytest.raises(StaleLeaseError, match="STALE"):
        complete_job(
            db,
            job.job_id,
            "worker-a",
            claimed.lease_token,
            {"late": True},
            now=expired,
        )
    with pytest.raises(StaleLeaseError, match="STALE"):
        fail_job(
            db,
            job.job_id,
            "worker-a",
            claimed.lease_token,
            {"late": True},
            now=expired,
        )


def test_lease_renewal_extends_ownership_without_changing_fencing_token(tmp_path):
    db = tmp_path / "sare.db"
    job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 22})
    t0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    claimed = claim_next_job(db, "worker-a", lease_seconds=30, now=t0)
    assert claimed is not None and claimed.lease_token == 1

    renewed = renew_lease(
        db,
        job.job_id,
        "worker-a",
        claimed.lease_token,
        lease_seconds=30,
        now=t0 + timedelta(seconds=20),
    )
    assert renewed.lease_token == 1
    assert renewed.lease_expires_at == (t0 + timedelta(seconds=50)).isoformat()

    assert claim_next_job(
        db,
        "worker-b",
        lease_seconds=30,
        now=t0 + timedelta(seconds=31),
    ) is None
    completed = complete_job(
        db,
        job.job_id,
        "worker-a",
        claimed.lease_token,
        {"ok": True},
        now=t0 + timedelta(seconds=40),
    )
    assert completed.state == "COMPLETED"
