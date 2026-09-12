from datetime import date, datetime, timezone

import pytest

from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import connect
from sare_lotofacil.persistence.evidence import verify_source_artifacts
from sare_lotofacil.persistence.repository import create_latest_snapshot, persist_history_records


def test_evidence_hash_detects_tampering(tmp_path):
    db = tmp_path / "sare.db"
    record = validate_contest(1, date(2026, 1, 1), range(1, 16))
    persisted = persist_history_records(
        db,
        [record],
        source_url="fixture://history",
        raw_bytes=b"canonical-evidence",
        captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        source_class="TEST",
    )
    checks = verify_source_artifacts(db)
    assert len(checks) == 1 and checks[0].valid is True
    with connect(db) as connection:
        connection.execute(
            "UPDATE source_artifacts SET raw_json=raw_json || 'tampered' WHERE artifact_id=?",
            (persisted.artifact_id,),
        )
    tampered = verify_source_artifacts(db)
    assert tampered[0].valid is False
    assert tampered[0].actual_sha256 != tampered[0].expected_sha256


def test_failed_ingestion_does_not_change_published_snapshot(tmp_path):
    db = tmp_path / "sare.db"
    record = validate_contest(1, date(2026, 1, 1), range(1, 16))
    persist_history_records(
        db,
        [record],
        source_url="fixture://ok",
        raw_bytes=b"ok",
        captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        source_class="TEST",
    )
    before = create_latest_snapshot(db)
    with pytest.raises(ValueError):
        persist_history_records(
            db,
            [record, record],
            source_url="fixture://invalid",
            raw_bytes=b"invalid",
            captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            source_class="TEST",
        )
    after = create_latest_snapshot(db)
    assert after.snapshot_id == before.snapshot_id
    assert after.snapshot_hash == before.snapshot_hash
