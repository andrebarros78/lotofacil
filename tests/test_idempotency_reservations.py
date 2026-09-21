from __future__ import annotations

from sare_lotofacil.persistence.operations import (
    complete_idempotency,
    get_idempotency,
    payload_hash,
    release_idempotency,
    reserve_idempotency,
)


def test_atomic_reservation_has_single_effect_owner(tmp_path):
    db = tmp_path / "sare.db"
    digest = payload_hash({"seed": 17})

    first = reserve_idempotency(db, "PORTFOLIO", "same-key", digest, "owner-a")
    second = reserve_idempotency(db, "PORTFOLIO", "same-key", digest, "owner-b")

    assert first.state == "RESERVED"
    assert first.owner_token == "owner-a"
    assert second.state == "RESERVED"
    assert second.owner_token == "owner-a"

    complete_idempotency(
        db,
        "PORTFOLIO",
        "same-key",
        digest,
        "owner-a",
        {"portfolio_id": "p-1"},
        201,
    )
    final = get_idempotency(db, "PORTFOLIO", "same-key")
    assert final is not None
    assert final.state == "COMPLETED"
    assert final.owner_token is None
    assert final.status_code == 201


def test_reservation_conflict_never_changes_request_hash(tmp_path):
    db = tmp_path / "sare.db"
    first_digest = payload_hash({"seed": 17})
    second_digest = payload_hash({"seed": 18})

    reserve_idempotency(db, "PORTFOLIO", "same-key", first_digest, "owner-a")
    observed = reserve_idempotency(db, "PORTFOLIO", "same-key", second_digest, "owner-b")

    assert observed.request_hash == first_digest
    assert observed.owner_token == "owner-a"


def test_failed_owner_can_release_reservation_for_retry(tmp_path):
    db = tmp_path / "sare.db"
    digest = payload_hash({"seed": 17})

    reserve_idempotency(db, "PORTFOLIO", "retry-key", digest, "owner-a")
    release_idempotency(db, "PORTFOLIO", "retry-key", digest, "owner-a")
    retried = reserve_idempotency(db, "PORTFOLIO", "retry-key", digest, "owner-b")

    assert retried.state == "RESERVED"
    assert retried.owner_token == "owner-b"
