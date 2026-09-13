from datetime import date, datetime, timezone

from sare_lotofacil.domain.masks import numbers_to_mask
from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.repository import load_snapshot_records
from sare_lotofacil.persistence.vintages import create_snapshot_as_of


def _insert_revision(db, contest_id, revision, numbers, availability_at):
    with connect(db) as connection:
        connection.execute(
            "INSERT INTO contest_revisions(contest_id, revision, draw_date, result_mask, source_class, availability_at) "
            "VALUES (?, ?, ?, ?, 'SINTETICO', ?)",
            (
                contest_id,
                revision,
                date(2026, 1, contest_id).isoformat(),
                numbers_to_mask(numbers),
                availability_at,
            ),
        )


def test_point_in_time_snapshot_excludes_future_revision(tmp_path):
    db = tmp_path / "sare.db"
    initialize_database(db)
    old = tuple(range(1, 16))
    revised = tuple(range(2, 17))
    _insert_revision(db, 1, 1, old, "2026-01-02T09:00:00+00:00")
    _insert_revision(db, 1, 2, revised, "2026-02-02T09:00:00+00:00")

    snapshot = create_snapshot_as_of(db, datetime(2026, 1, 15, tzinfo=timezone.utc))
    records = load_snapshot_records(db, snapshot.snapshot_id)
    assert records[0].numbers == old


def test_point_in_time_uses_availability_not_ingestion_revision_order(tmp_path):
    db = tmp_path / "sare.db"
    initialize_database(db)
    newer_information = tuple(range(1, 16))
    older_information_imported_later = tuple(range(2, 17))
    _insert_revision(db, 1, 1, newer_information, "2026-03-01T10:00:00+00:00")
    _insert_revision(db, 1, 2, older_information_imported_later, "2026-02-01T10:00:00-03:00")

    snapshot = create_snapshot_as_of(db, datetime(2026, 3, 2, tzinfo=timezone.utc))
    records = load_snapshot_records(db, snapshot.snapshot_id)
    assert records[0].numbers == newer_information


def test_point_in_time_excludes_unknown_availability_and_audits_cutoff(tmp_path):
    db = tmp_path / "sare.db"
    initialize_database(db)
    _insert_revision(db, 1, 1, tuple(range(1, 16)), "2026-01-02T09:00:00+00:00")
    _insert_revision(db, 2, 1, tuple(range(1, 16)), None)

    cutoff = datetime(2026, 1, 20, tzinfo=timezone.utc)
    snapshot = create_snapshot_as_of(db, cutoff)
    records = load_snapshot_records(db, snapshot.snapshot_id)
    assert [record.contest_id for record in records] == [1]
    with connect(db) as connection:
        detail = connection.execute(
            "SELECT detail_json FROM audit_events WHERE action='POINT_IN_TIME_SNAPSHOT' AND entity_id=?",
            (snapshot.snapshot_id,),
        ).fetchone()[0]
    assert cutoff.isoformat() in detail
    assert '"unknown_availability_policy":"EXCLUDE"' in detail
