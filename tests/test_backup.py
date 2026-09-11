import sqlite3

from sare_lotofacil.persistence.backup import backup_database, database_integrity, restore_database
from sare_lotofacil.persistence.db import initialize_database


def test_backup_and_restore_preserve_committed_data(tmp_path) -> None:
    source = tmp_path / "source.db"
    backup = tmp_path / "backup" / "sare.db"
    restored = tmp_path / "restored" / "sare.db"
    initialize_database(source)
    connection = sqlite3.connect(source)
    try:
        connection.execute(
            "INSERT INTO rulesets(ruleset_id, valid_from, universe_size, draw_size, simple_bet_cost_cents, source) VALUES (?, ?, ?, ?, ?, ?)",
            ("r1", "2026-01-01", 25, 15, 350, "test"),
        )
        connection.commit()
    finally:
        connection.close()

    backup_info = backup_database(source, backup)
    restore_info = restore_database(backup, restored)
    assert backup_info.integrity == restore_info.integrity == "ok"
    assert database_integrity(restored) == "ok"

    connection = sqlite3.connect(restored)
    try:
        assert connection.execute("SELECT ruleset_id FROM rulesets").fetchone() == ("r1",)
    finally:
        connection.close()
