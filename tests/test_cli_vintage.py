from datetime import date

from sare_lotofacil.cli import main
from sare_lotofacil.domain.masks import numbers_to_mask
from sare_lotofacil.persistence.db import connect, initialize_database


def test_snapshot_as_of_cli_publishes_historical_vintage(monkeypatch, tmp_path, capsys):
    db = tmp_path / "sare.db"
    initialize_database(db)
    with connect(db) as connection:
        connection.execute(
            "INSERT INTO contest_revisions(contest_id, revision, draw_date, result_mask, source_class, availability_at) "
            "VALUES (1, 1, ?, ?, 'SINTETICO', '2026-01-02T09:00:00+00:00')",
            (date(2026, 1, 1).isoformat(), numbers_to_mask(tuple(range(1, 16)))),
        )
        connection.execute(
            "INSERT INTO contest_revisions(contest_id, revision, draw_date, result_mask, source_class, availability_at) "
            "VALUES (1, 2, ?, ?, 'SINTETICO', '2026-02-02T09:00:00+00:00')",
            (date(2026, 1, 1).isoformat(), numbers_to_mask(tuple(range(2, 17)))),
        )

    monkeypatch.setattr(
        "sys.argv",
        [
            "sare-lotofacil",
            "snapshot-as-of",
            "--db",
            str(db),
            "--availability-cutoff",
            "2026-01-15T00:00:00+00:00",
        ],
    )
    assert main() == 0
    output = capsys.readouterr().out
    assert '"contest_count": 1' in output
    assert '"availability_cutoff": "2026-01-15T00:00:00+00:00"' in output
