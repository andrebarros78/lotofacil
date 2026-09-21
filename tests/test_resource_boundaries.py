from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import sare_lotofacil.portfolios.core as core_module
from sare_lotofacil.api.app import create_app
from sare_lotofacil.persistence.db import connect
from sare_lotofacil.persistence.jobs import claim_next_job, enqueue_job, get_job
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


def test_uniform_generation_preserves_reproducibility_with_hard_bounds() -> None:
    first = generate_uniform_portfolio(MAX_CARDS_PER_REQUEST, seed=20260921)
    second = generate_uniform_portfolio(MAX_CARDS_PER_REQUEST, seed=20260921)
    assert first == second
    assert len(first.cards) == MAX_CARDS_PER_REQUEST
    assert len(set(first.cards)) == MAX_CARDS_PER_REQUEST

    with pytest.raises(ValueError, match="card_count"):
        generate_uniform_portfolio(MAX_CARDS_PER_REQUEST + 1, seed=1)


def test_uniform_generation_attempt_limit_is_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        core_module.random.Random,
        "sample",
        lambda self, population, k: list(range(1, 16)),
    )
    with pytest.raises(ResourceLimitError, match="GENERATION_ATTEMPTS_LIMIT_EXCEEDED"):
        generate_uniform_portfolio(2, seed=77)


def test_uniform_generation_runtime_limit_is_fail_closed(monkeypatch) -> None:
    ticks = iter((100.0, 100.0 + MAX_RUNTIME_SECONDS + 0.001))
    monkeypatch.setattr(core_module.time, "monotonic", lambda: next(ticks))
    with pytest.raises(ResourceLimitError, match="RUNTIME_LIMIT_EXCEEDED"):
        generate_uniform_portfolio(1, seed=77)


def test_card_artifact_size_limit_blocks_oversized_metadata() -> None:
    oversized = "x" * (MAX_ARTIFACT_BYTES + 1)
    with pytest.raises(ResourceLimitError, match="ARTIFACT_BYTES_LIMIT_EXCEEDED"):
        build_card_artifact(
            status="PREVIEW",
            policy_id="TEST",
            policy_version="1",
            cards=(range(1, 16),),
            metadata={"oversized": oversized},
        )


def test_operator_freeze_card_limit_and_attempt_limit_leave_ledger_unchanged() -> None:
    ledger = empty_operator_card_ledger()
    with pytest.raises(ValueError, match="requested_card_count"):
        freeze_operator_cards(
            ledger,
            target_contest=3785,
            requested_card_count=MAX_OPERATOR_CARDS_PER_REQUEST + 1,
            state_snapshot_hash="storage",
            created_at_utc="2026-09-21T17:00:00+00:00",
            idempotency_key="too-many",
            source_commit="commit",
            workflow_run_id="run",
        )
    assert ledger["requests"] == []

    reserved = [
        card_for_generation_index(3785, index)
        for index in range(MAX_GENERATION_ATTEMPTS)
    ]
    with pytest.raises(
        ResourceLimitError,
        match="OPERATOR_CARD_GENERATION_ATTEMPTS_LIMIT_EXCEEDED",
    ):
        freeze_operator_cards(
            ledger,
            target_contest=3785,
            requested_card_count=1,
            state_snapshot_hash="storage",
            created_at_utc="2026-09-21T17:00:00+00:00",
            idempotency_key="bounded-scan",
            source_commit="commit",
            workflow_run_id="run",
            reserved_cards=reserved,
        )
    assert ledger["requests"] == []
    assert ledger["summary"] == {"by_target": {}}


def test_job_queue_limit_is_transactional_and_duplicate_is_still_idempotent(tmp_path) -> None:
    db = tmp_path / "sare.db"
    first = None
    for seed in range(MAX_PENDING_JOBS):
        record = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": seed})
        first = first or record

    with connect(db) as connection:
        pending = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','LEASED')"
        ).fetchone()[0]
    assert pending == MAX_PENDING_JOBS

    assert first is not None
    duplicate = enqueue_job(db, "PORTFOLIO", first.payload)
    assert duplicate.job_id == first.job_id

    with pytest.raises(ResourceLimitError, match="PENDING_JOB_LIMIT_EXCEEDED"):
        enqueue_job(
            db,
            "PORTFOLIO",
            {"card_count": 1, "seed": MAX_PENDING_JOBS + 1},
        )

    with connect(db) as connection:
        pending_after = connection.execute(
            "SELECT COUNT(*) FROM jobs WHERE state IN ('QUEUED','LEASED')"
        ).fetchone()[0]
    assert pending_after == MAX_PENDING_JOBS


def test_job_payload_size_and_attempt_limits_fail_closed(tmp_path) -> None:
    db = tmp_path / "sare.db"
    with pytest.raises(ResourceLimitError, match="JOB_PAYLOAD_BYTES_LIMIT_EXCEEDED"):
        enqueue_job(
            db,
            "PORTFOLIO",
            {"card_count": 1, "seed": 1, "padding": "x" * (MAX_JOB_PAYLOAD_BYTES + 1)},
        )

    job = enqueue_job(db, "PORTFOLIO", {"card_count": 1, "seed": 991})
    t0 = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    with connect(db) as connection:
        connection.execute(
            "UPDATE jobs SET state='LEASED', lease_owner='old', attempts=?, "
            "lease_expires_at=? WHERE job_id=?",
            (MAX_JOB_ATTEMPTS, (t0 - timedelta(seconds=1)).isoformat(), job.job_id),
        )

    assert claim_next_job(db, "worker-new", lease_seconds=30, now=t0) is None
    failed = get_job(db, job.job_id)
    assert failed.state == "FAILED"
    assert failed.error is not None
    assert failed.error["message"] == "JOB_ATTEMPT_LIMIT_EXCEEDED"


def test_http_body_limit_uses_actual_bytes_not_only_declared_content_length(tmp_path) -> None:
    client = TestClient(
        create_app(
            tmp_path / "sare.db",
            write_token="secret",
            max_body_bytes=1024,
        )
    )
    body = b"x" * 2048
    response = client.post(
        "/v1/jobs",
        content=body,
        headers={
            "content-type": "application/json",
            "content-length": "1",
            "X-SARE-Token": "secret",
            "Idempotency-Key": "oversized-body",
        },
    )
    assert response.status_code == 413

    with pytest.raises(ValueError, match="max_body_bytes"):
        create_app(
            tmp_path / "too-large.db",
            write_token="secret",
            max_body_bytes=MAX_REQUEST_BODY_BYTES + 1,
        )
