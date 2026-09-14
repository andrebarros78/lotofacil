from __future__ import annotations

import sqlite3

from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect, initialize_database
from sare_lotofacil.persistence.operations import persist_uniform_portfolio


def test_schema_v6_migrates_portfolios_to_allow_single_card_without_data_loss(tmp_path) -> None:
    db = tmp_path / "legacy-v6.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT INTO schema_meta(key, value) VALUES('schema_version', '6');

            CREATE TABLE portfolios (
                portfolio_id TEXT PRIMARY KEY,
                snapshot_id TEXT,
                target_contest INTEGER,
                seed INTEGER NOT NULL,
                card_count INTEGER NOT NULL CHECK (card_count BETWEEN 3 AND 100),
                cost_cents INTEGER NOT NULL CHECK (cost_cents > 0),
                predictive_evidence TEXT NOT NULL DEFAULT 'NOT_ESTABLISHED',
                evidence_label TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO portfolios(
                portfolio_id, snapshot_id, target_contest, seed, card_count,
                cost_cents, predictive_evidence, evidence_label
            ) VALUES (
                'legacy-portfolio', NULL, 3780, 77, 3,
                1050, 'NOT_ESTABLISHED', 'legacy-label'
            );
            """
        )

    initialize_database(db)

    with connect(db) as connection:
        schema_version = int(
            connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
        )
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='portfolios'"
        ).fetchone()[0]
        legacy = connection.execute(
            "SELECT portfolio_id, card_count, cost_cents FROM portfolios WHERE portfolio_id='legacy-portfolio'"
        ).fetchone()
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()

    assert schema_version == SCHEMA_VERSION == 7
    assert "BETWEEN 1 AND 100" in " ".join(table_sql.upper().split())
    assert legacy == ("legacy-portfolio", 3, 1050)
    assert foreign_key_violations == []

    single = persist_uniform_portfolio(db, card_count=1, seed=3780, target_contest=3780)
    assert len(single.cards) == 1
    assert single.cost_cents == 350
