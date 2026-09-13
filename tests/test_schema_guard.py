import sqlite3

import pytest

from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect, initialize_database


def test_additive_upgrade_restores_missing_current_tables_before_advancing_metadata(tmp_path):
    db = tmp_path / "sare.db"
    initialize_database(db)
    with connect(db) as connection:
        connection.execute("INSERT INTO schema_meta(key, value) VALUES('fixture', 'preserve-me')")
        connection.execute("DROP TABLE job_checkpoints")
        connection.execute("DROP TABLE jobs")
        connection.execute("UPDATE schema_meta SET value='4' WHERE key='schema_version'")
    initialize_database(db)
    with connect(db) as connection:
        assert connection.execute("SELECT value FROM schema_meta WHERE key='fixture'").fetchone()[0] == "preserve-me"
        assert connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == str(SCHEMA_VERSION)
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='jobs'").fetchone()
        assert connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='job_checkpoints'").fetchone()


def test_incompatible_existing_table_fails_closed_and_does_not_advance_version(tmp_path):
    db = tmp_path / "sare.db"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '1');
        CREATE TABLE snapshots(snapshot_id TEXT PRIMARY KEY);
        """
    )
    connection.commit()
    connection.close()

    with pytest.raises(RuntimeError, match="SCHEMA_INCOMPATIBLE"):
        initialize_database(db)

    connection = sqlite3.connect(db)
    assert connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == "1"
    connection.close()


def test_database_newer_than_code_is_rejected_without_downgrade(tmp_path):
    db = tmp_path / "sare.db"
    initialize_database(db)
    with connect(db) as connection:
        connection.execute("UPDATE schema_meta SET value=? WHERE key='schema_version'", (str(SCHEMA_VERSION + 1),))

    with pytest.raises(RuntimeError, match="SCHEMA_NEWER_THAN_CODE"):
        initialize_database(db)

    with connect(db) as connection:
        assert connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0] == str(SCHEMA_VERSION + 1)
