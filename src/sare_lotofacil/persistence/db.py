from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_artifacts (
    artifact_id TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_class TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    raw_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rulesets (
    ruleset_id TEXT PRIMARY KEY,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    universe_size INTEGER NOT NULL CHECK (universe_size = 25),
    draw_size INTEGER NOT NULL CHECK (draw_size = 15),
    simple_bet_cost_cents INTEGER NOT NULL CHECK (simple_bet_cost_cents > 0),
    source TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS contest_revisions (
    contest_id INTEGER NOT NULL CHECK (contest_id > 0),
    revision INTEGER NOT NULL CHECK (revision > 0),
    draw_date TEXT NOT NULL,
    result_mask INTEGER NOT NULL CHECK (result_mask > 0),
    source_class TEXT NOT NULL,
    source_artifact_id TEXT,
    availability_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (contest_id, revision)
);

CREATE TABLE IF NOT EXISTS prize_tiers (
    contest_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    hits INTEGER NOT NULL CHECK (hits BETWEEN 11 AND 15),
    winners INTEGER NOT NULL CHECK (winners >= 0),
    prize_cents INTEGER NOT NULL CHECK (prize_cents >= 0),
    PRIMARY KEY (contest_id, revision, hits),
    FOREIGN KEY (contest_id, revision)
        REFERENCES contest_revisions(contest_id, revision) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    snapshot_hash TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL CHECK (state IN ('DRAFT', 'PUBLISHED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS snapshot_members (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(snapshot_id) ON DELETE CASCADE,
    contest_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    PRIMARY KEY (snapshot_id, contest_id),
    FOREIGN KEY (contest_id, revision)
        REFERENCES contest_revisions(contest_id, revision)
);

CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    run_type TEXT NOT NULL,
    execution_state TEXT NOT NULL,
    snapshot_id TEXT REFERENCES snapshots(snapshot_id),
    code_commit TEXT,
    config_hash TEXT,
    seed INTEGER,
    technical_status TEXT NOT NULL,
    predictive_evidence TEXT NOT NULL DEFAULT 'NOT_ESTABLISHED',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_contest_revisions_date
ON contest_revisions(draw_date);

CREATE INDEX IF NOT EXISTS idx_runs_state
ON runs(execution_state);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def initialize_database(path: str | Path) -> Path:
    db_path = Path(path)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
    return db_path
