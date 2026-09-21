from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import initialize_database
from sare_lotofacil.persistence.repository import (
    create_latest_snapshot,
    load_snapshot_records,
    persist_history_records,
)
from sare_lotofacil.persistence.snapshot_identity import (
    SEMANTIC_SNAPSHOT_SCHEMA,
    semantic_data_snapshot_hash,
    semantic_snapshot_payload,
)


def _records():
    return (
        validate_contest(1, date(2026, 1, 1), range(1, 16)),
        validate_contest(2, date(2026, 1, 2), range(2, 17)),
    )


def _persist(path, records, marker: bytes) -> None:
    persist_history_records(
        path,
        records,
        source_url=f"memory://{marker.decode('ascii')}",
        raw_bytes=marker,
        captured_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        source_class="TEST",
        media_type="application/octet-stream",
    )


def test_semantic_hash_is_order_independent_and_versioned() -> None:
    records = _records()
    forward = semantic_data_snapshot_hash(records)
    reverse = semantic_data_snapshot_hash(reversed(records))

    assert forward == reverse
    payload = semantic_snapshot_payload(records)
    assert payload["schema"] == SEMANTIC_SNAPSHOT_SCHEMA
    assert payload["contest_count"] == 2
    assert [item["contest_id"] for item in payload["contests"]] == [1, 2]


def test_same_data_with_different_revision_graph_has_same_data_hash(tmp_path) -> None:
    canonical = _records()
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"

    _persist(db_a, canonical, b"canonical-a")

    altered_first = validate_contest(1, date(2026, 1, 1), range(11, 26))
    _persist(db_b, (altered_first,), b"temporary-divergence")
    _persist(db_b, canonical, b"canonical-b")

    snapshot_a = create_latest_snapshot(db_a)
    snapshot_b = create_latest_snapshot(db_b)

    assert snapshot_a.snapshot_hash != snapshot_b.snapshot_hash
    assert snapshot_a.storage_snapshot_hash == snapshot_a.snapshot_hash
    assert snapshot_b.storage_snapshot_hash == snapshot_b.snapshot_hash
    assert snapshot_a.storage_snapshot_id == snapshot_a.snapshot_id
    assert snapshot_b.storage_snapshot_id == snapshot_b.snapshot_id
    assert snapshot_a.data_snapshot_hash == snapshot_b.data_snapshot_hash
    assert snapshot_a.data_snapshot_hash == semantic_data_snapshot_hash(canonical)
    assert load_snapshot_records(db_a, snapshot_a.snapshot_id) == canonical
    assert load_snapshot_records(db_b, snapshot_b.snapshot_id) == canonical


def test_semantic_hash_changes_when_date_or_numbers_change() -> None:
    original = _records()
    date_changed = (
        validate_contest(1, date(2026, 1, 3), range(1, 16)),
        original[1],
    )
    numbers_changed = (
        validate_contest(1, date(2026, 1, 1), range(11, 26)),
        original[1],
    )

    assert semantic_data_snapshot_hash(original) != semantic_data_snapshot_hash(date_changed)
    assert semantic_data_snapshot_hash(original) != semantic_data_snapshot_hash(numbers_changed)


def test_schema_v8_backfills_semantic_hash_for_existing_snapshot(tmp_path) -> None:
    path = tmp_path / "sare.db"
    records = _records()
    _persist(path, records, b"canonical")
    snapshot = create_latest_snapshot(path)

    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE snapshots SET data_snapshot_hash=NULL WHERE snapshot_id=?",
            (snapshot.snapshot_id,),
        )
        connection.commit()

    initialize_database(path)

    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT data_snapshot_hash FROM snapshots WHERE snapshot_id=?",
            (snapshot.snapshot_id,),
        ).fetchone()

    assert row == (semantic_data_snapshot_hash(records),)
