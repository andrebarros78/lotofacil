from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA_VERSION = 5

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

CREATE TABLE IF NOT EXISTS run_results (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    portfolio_id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(snapshot_id),
    target_contest INTEGER,
    seed INTEGER NOT NULL,
    card_count INTEGER NOT NULL CHECK (card_count BETWEEN 3 AND 100),
    cost_cents INTEGER NOT NULL CHECK (cost_cents > 0),
    predictive_evidence TEXT NOT NULL DEFAULT 'NOT_ESTABLISHED',
    evidence_label TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_cards (
    portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    position INTEGER NOT NULL CHECK (position > 0),
    result_mask INTEGER NOT NULL CHECK (result_mask > 0),
    PRIMARY KEY (portfolio_id, position),
    UNIQUE (portfolio_id, result_mask)
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    result_mask INTEGER NOT NULL CHECK (result_mask > 0),
    hits_json TEXT NOT NULL,
    max_hits INTEGER NOT NULL CHECK (max_hits BETWEEN 5 AND 15),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_json TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (operation, idempotency_key)
);

CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    ingestion_id TEXT PRIMARY KEY,
    source_class TEXT NOT NULL,
    source_url TEXT NOT NULL,
    contest_id INTEGER,
    revision INTEGER,
    artifact_id TEXT,
    execution_state TEXT NOT NULL CHECK (execution_state IN ('COMPLETED', 'FAILED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    protocol_hash TEXT NOT NULL UNIQUE,
    protocol_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('REGISTERED', 'IN_PROOF', 'CONCLUDED', 'INVALIDATED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_runs (
    experiment_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    protocol_hash TEXT NOT NULL,
    conclusion TEXT NOT NULL,
    predictive_evidence TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (hypothesis_id, run_id)
);

CREATE TABLE IF NOT EXISTS model_promotions (
    promotion_id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiment_runs(experiment_id),
    model_name TEXT NOT NULL,
    predictive_evidence TEXT NOT NULL CHECK (predictive_evidence = 'REPLICATED'),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (experiment_id, model_name)
);

CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    request_json TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('QUEUED', 'LEASED', 'COMPLETED', 'FAILED', 'CANCELLED')),
    lease_owner TEXT,
    lease_token INTEGER NOT NULL DEFAULT 0,
    lease_expires_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    result_json TEXT,
    error_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS job_checkpoints (
    job_id TEXT PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
    lease_token INTEGER NOT NULL,
    checkpoint_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_jobs_claim
ON jobs(state, lease_expires_at, created_at);

CREATE INDEX IF NOT EXISTS idx_hypotheses_status
ON hypotheses(status);

CREATE INDEX IF NOT EXISTS idx_experiment_runs_hypothesis
ON experiment_runs(hypothesis_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_contest
ON ingestion_runs(contest_id);

CREATE INDEX IF NOT EXISTS idx_portfolios_snapshot
ON portfolios(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_evaluations_portfolio
ON evaluations(portfolio_id);

CREATE INDEX IF NOT EXISTS idx_contest_revisions_date
ON contest_revisions(draw_date);

CREATE INDEX IF NOT EXISTS idx_runs_state
ON runs(execution_state);
"""

_REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    "schema_meta": frozenset({"key", "value"}),
    "source_artifacts": frozenset({"artifact_id", "source_url", "source_class", "captured_at", "sha256", "raw_json"}),
    "rulesets": frozenset({"ruleset_id", "valid_from", "universe_size", "draw_size", "simple_bet_cost_cents", "source"}),
    "contest_revisions": frozenset({"contest_id", "revision", "draw_date", "result_mask", "source_class", "availability_at"}),
    "prize_tiers": frozenset({"contest_id", "revision", "hits", "winners", "prize_cents"}),
    "snapshots": frozenset({"snapshot_id", "snapshot_hash", "state"}),
    "snapshot_members": frozenset({"snapshot_id", "contest_id", "revision"}),
    "runs": frozenset({"run_id", "run_type", "execution_state", "snapshot_id", "technical_status", "predictive_evidence"}),
    "run_results": frozenset({"run_id", "result_json"}),
    "portfolios": frozenset({"portfolio_id", "seed", "card_count", "cost_cents", "predictive_evidence", "evidence_label"}),
    "portfolio_cards": frozenset({"portfolio_id", "position", "result_mask"}),
    "evaluations": frozenset({"evaluation_id", "portfolio_id", "result_mask", "hits_json", "max_hits"}),
    "idempotency_keys": frozenset({"operation", "idempotency_key", "request_hash", "response_json", "status_code"}),
    "audit_events": frozenset({"event_id", "action", "entity_type", "entity_id", "detail_json"}),
    "ingestion_runs": frozenset({"ingestion_id", "source_class", "source_url", "execution_state"}),
    "hypotheses": frozenset({"hypothesis_id", "protocol_hash", "protocol_json", "status"}),
    "experiment_runs": frozenset({"experiment_id", "hypothesis_id", "run_id", "protocol_hash", "conclusion", "predictive_evidence"}),
    "model_promotions": frozenset({"promotion_id", "experiment_id", "model_name", "predictive_evidence"}),
    "jobs": frozenset({"job_id", "job_type", "request_json", "request_hash", "state", "lease_owner", "lease_token", "lease_expires_at", "attempts", "cancel_requested"}),
    "job_checkpoints": frozenset({"job_id", "lease_token", "checkpoint_json"}),
}


def connect(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30.0)
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.execute("PRAGMA foreign_keys = ON")
    for attempt in range(8):
        try:
            current_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            if str(current_mode).lower() != "wal":
                connection.execute("PRAGMA journal_mode = WAL")
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 7:
                connection.close()
                raise
            time.sleep(0.025 * (attempt + 1))
    return connection


def _existing_schema_version(connection: sqlite3.Connection) -> int | None:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
    ).fetchone()
    if not table:
        return None
    row = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
    if row is None:
        return None
    try:
        return int(row[0])
    except (TypeError, ValueError) as exc:
        raise RuntimeError("SCHEMA_VERSION_INVALID") from exc


def _verify_schema_shape(connection: sqlite3.Connection) -> None:
    for table, required in _REQUIRED_COLUMNS.items():
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if not exists:
            raise RuntimeError(f"SCHEMA_INCOMPATIBLE: missing table {table}")
        present = {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()}
        missing = sorted(required - present)
        if missing:
            raise RuntimeError(f"SCHEMA_INCOMPATIBLE: {table} missing columns {','.join(missing)}")


def initialize_database(path: str | Path) -> Path:
    """Initialize or additively migrate a known SARE schema, failing closed on drift.

    Historical SARE schema versions 1-5 are additive for the tables represented by
    ``SCHEMA_SQL``. ``CREATE TABLE IF NOT EXISTS`` supplies missing additive tables;
    shape verification prevents the previous false-success mode where metadata was
    advanced even though an incompatible pre-existing table remained unchanged.
    """
    db_path = Path(path)
    with connect(db_path) as connection:
        current_version = _existing_schema_version(connection)
        if current_version is not None and current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"SCHEMA_NEWER_THAN_CODE: database={current_version} code={SCHEMA_VERSION}"
            )
        connection.executescript(SCHEMA_SQL)
        _verify_schema_shape(connection)
        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
    return db_path
