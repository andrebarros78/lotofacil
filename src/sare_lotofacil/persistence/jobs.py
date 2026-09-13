from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.operations import canonical_json, persist_analysis, persist_uniform_portfolio
from sare_lotofacil.persistence.workflows import execute_experiment


class StaleLeaseError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    job_type: str
    state: str
    payload: dict[str, Any]
    lease_owner: str | None
    lease_token: int
    lease_expires_at: str | None
    attempts: int
    cancel_requested: bool
    result: dict[str, Any] | None
    error: dict[str, Any] | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _identity(job_type: str, payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json({"job_type": job_type, "payload": payload}).encode("utf-8")).hexdigest()


def enqueue_job(path: str | Path, job_type: str, payload: dict[str, Any]) -> JobRecord:
    initialize_database(path)
    normalized_type = job_type.strip().upper()
    if normalized_type not in {"ANALYSIS", "PORTFOLIO", "EXPERIMENT"}:
        raise ValueError("job_type inválido")
    digest = _identity(normalized_type, payload)
    job_id = f"job-{digest[:24]}"
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO jobs(job_id, job_type, request_json, request_hash, state) VALUES (?, ?, ?, ?, 'QUEUED')",
            (job_id, normalized_type, canonical_json(payload), digest),
        )
    return get_job(path, job_id)


def get_job(path: str | Path, job_id: str) -> JobRecord:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT job_type, state, request_json, lease_owner, lease_token, lease_expires_at, attempts, cancel_requested, result_json, error_json "
            "FROM jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
    if not row:
        raise KeyError(job_id)
    return JobRecord(
        job_id=job_id,
        job_type=row[0],
        state=row[1],
        payload=json.loads(row[2]),
        lease_owner=row[3],
        lease_token=row[4],
        lease_expires_at=row[5],
        attempts=row[6],
        cancel_requested=bool(row[7]),
        result=json.loads(row[8]) if row[8] else None,
        error=json.loads(row[9]) if row[9] else None,
    )


def claim_next_job(
    path: str | Path,
    worker_id: str,
    *,
    lease_seconds: float = 30,
    now: datetime | None = None,
) -> JobRecord | None:
    if not worker_id.strip():
        raise ValueError("worker_id obrigatório")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds deve ser positivo")
    initialize_database(path)
    current = now or _utcnow()
    if current.tzinfo is None:
        raise ValueError("now deve possuir timezone")
    expires = current + timedelta(seconds=lease_seconds)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT job_id, lease_token FROM jobs "
            "WHERE cancel_requested=0 AND (state='QUEUED' OR (state='LEASED' AND lease_expires_at<=?)) "
            "ORDER BY created_at, job_id LIMIT 1",
            (current.isoformat(),),
        ).fetchone()
        if not row:
            return None
        job_id, old_token = row
        new_token = int(old_token) + 1
        connection.execute(
            "UPDATE jobs SET state='LEASED', lease_owner=?, lease_token=?, lease_expires_at=?, attempts=attempts+1, updated_at=CURRENT_TIMESTAMP "
            "WHERE job_id=?",
            (worker_id, new_token, expires.isoformat(), job_id),
        )
    return get_job(path, job_id)


def renew_lease(
    path: str | Path,
    job_id: str,
    worker_id: str,
    lease_token: int,
    *,
    lease_seconds: float = 30,
    now: datetime | None = None,
) -> str:
    """Extend a live lease only while the same fenced worker still owns it."""
    if lease_seconds <= 0:
        raise ValueError("lease_seconds deve ser positivo")
    current = now or _utcnow()
    if current.tzinfo is None:
        raise ValueError("now deve possuir timezone")
    expires = current + timedelta(seconds=lease_seconds)
    with connect(path) as connection:
        cursor = connection.execute(
            "UPDATE jobs SET lease_expires_at=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE job_id=? AND state='LEASED' AND lease_owner=? AND lease_token=? AND cancel_requested=0",
            (expires.isoformat(), job_id, worker_id, lease_token),
        )
        if cursor.rowcount != 1:
            raise StaleLeaseError("STALE_LEASE")
    return expires.isoformat()


def save_checkpoint(
    path: str | Path,
    job_id: str,
    worker_id: str,
    lease_token: int,
    checkpoint: dict[str, Any],
) -> None:
    with connect(path) as connection:
        valid = connection.execute(
            "SELECT 1 FROM jobs WHERE job_id=? AND state='LEASED' AND lease_owner=? AND lease_token=? AND cancel_requested=0",
            (job_id, worker_id, lease_token),
        ).fetchone()
        if not valid:
            raise StaleLeaseError("STALE_LEASE")
        connection.execute(
            "INSERT INTO job_checkpoints(job_id, lease_token, checkpoint_json) VALUES (?, ?, ?) "
            "ON CONFLICT(job_id) DO UPDATE SET lease_token=excluded.lease_token, checkpoint_json=excluded.checkpoint_json, updated_at=CURRENT_TIMESTAMP",
            (job_id, lease_token, canonical_json(checkpoint)),
        )


def complete_job(
    path: str | Path,
    job_id: str,
    worker_id: str,
    lease_token: int,
    result: dict[str, Any],
) -> JobRecord:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT cancel_requested FROM jobs WHERE job_id=? AND state='LEASED' AND lease_owner=? AND lease_token=?",
            (job_id, worker_id, lease_token),
        ).fetchone()
        if not row:
            raise StaleLeaseError("STALE_LEASE")
        if row[0]:
            connection.execute(
                "UPDATE jobs SET state='CANCELLED', lease_owner=NULL, lease_expires_at=NULL, result_json=NULL, updated_at=CURRENT_TIMESTAMP, finished_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (job_id,),
            )
        else:
            connection.execute(
                "UPDATE jobs SET state='COMPLETED', result_json=?, error_json=NULL, lease_owner=NULL, lease_expires_at=NULL, updated_at=CURRENT_TIMESTAMP, finished_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (canonical_json(result), job_id),
            )
    return get_job(path, job_id)


def fail_job(
    path: str | Path,
    job_id: str,
    worker_id: str,
    lease_token: int,
    error: dict[str, Any],
) -> JobRecord:
    with connect(path) as connection:
        cursor = connection.execute(
            "UPDATE jobs SET state='FAILED', error_json=?, lease_owner=NULL, lease_expires_at=NULL, updated_at=CURRENT_TIMESTAMP, finished_at=CURRENT_TIMESTAMP "
            "WHERE job_id=? AND state='LEASED' AND lease_owner=? AND lease_token=?",
            (canonical_json(error), job_id, worker_id, lease_token),
        )
        if cursor.rowcount != 1:
            raise StaleLeaseError("STALE_LEASE")
    return get_job(path, job_id)


def request_cancel(path: str | Path, job_id: str) -> JobRecord:
    with connect(path) as connection:
        row = connection.execute("SELECT state FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise KeyError(job_id)
        state = row[0]
        if state == "QUEUED":
            connection.execute(
                "UPDATE jobs SET state='CANCELLED', cancel_requested=1, updated_at=CURRENT_TIMESTAMP, finished_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (job_id,),
            )
        elif state == "LEASED":
            connection.execute(
                "UPDATE jobs SET cancel_requested=1, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (job_id,),
            )
    return get_job(path, job_id)


def _execute_payload(path: str | Path, job: JobRecord) -> dict[str, Any]:
    if job.job_type == "ANALYSIS":
        record = persist_analysis(
            path,
            str(job.payload["snapshot_id"]),
            min_train=job.payload.get("min_train"),
            delta_min=float(job.payload.get("delta_min", 0.0)),
        )
        return asdict(record)
    if job.job_type == "PORTFOLIO":
        record = persist_uniform_portfolio(
            path,
            card_count=int(job.payload["card_count"]),
            seed=int(job.payload["seed"]),
            snapshot_id=job.payload.get("snapshot_id"),
            target_contest=job.payload.get("target_contest"),
        )
        result = asdict(record)
        result["cards"] = [list(card) for card in record.cards]
        return result
    if job.job_type == "EXPERIMENT":
        return asdict(execute_experiment(path, str(job.payload["hypothesis_id"])))
    raise ValueError(f"job_type não suportado: {job.job_type}")


def run_worker_once(
    path: str | Path,
    worker_id: str,
    *,
    lease_seconds: float = 30,
    now: datetime | None = None,
) -> JobRecord | None:
    job = claim_next_job(path, worker_id, lease_seconds=lease_seconds, now=now)
    if job is None:
        return None

    stop_heartbeat = threading.Event()
    heartbeat_errors: list[BaseException] = []
    interval = max(0.05, lease_seconds / 3.0)

    def heartbeat() -> None:
        while not stop_heartbeat.wait(interval):
            try:
                renew_lease(
                    path,
                    job.job_id,
                    worker_id,
                    job.lease_token,
                    lease_seconds=lease_seconds,
                )
            except BaseException as exc:  # surfaced deterministically in the owner thread
                heartbeat_errors.append(exc)
                stop_heartbeat.set()
                return

    heartbeat_thread = threading.Thread(
        target=heartbeat,
        name=f"sare-lease-heartbeat-{job.job_id}",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        save_checkpoint(path, job.job_id, worker_id, job.lease_token, {"phase": "CLAIMED", "attempt": job.attempts})
        result = _execute_payload(path, job)
        if heartbeat_errors:
            raise StaleLeaseError("STALE_LEASE") from heartbeat_errors[0]
        renew_lease(path, job.job_id, worker_id, job.lease_token, lease_seconds=lease_seconds)
        save_checkpoint(path, job.job_id, worker_id, job.lease_token, {"phase": "COMPUTED", "attempt": job.attempts})
        return complete_job(path, job.job_id, worker_id, job.lease_token, result)
    except StaleLeaseError:
        raise
    except Exception as exc:
        return fail_job(
            path,
            job.job_id,
            worker_id,
            job.lease_token,
            {"type": type(exc).__name__, "message": str(exc)},
        )
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=max(1.0, interval * 2.0))
