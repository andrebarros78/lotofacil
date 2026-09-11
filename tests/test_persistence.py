import sqlite3

from sare_lotofacil.persistence.db import SCHEMA_VERSION, initialize_database


def test_database_initialization_is_idempotent(tmp_path) -> None:
    path = tmp_path / "sare.db"
    initialize_database(path)
    initialize_database(path)

    connection = sqlite3.connect(path)
    try:
        version = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        assert version == (str(SCHEMA_VERSION),)
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"rulesets", "contest_revisions", "snapshots", "snapshot_members", "runs"} <= tables
    finally:
        connection.close()
