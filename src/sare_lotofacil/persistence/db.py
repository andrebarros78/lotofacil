from __future__ import annotations

import sqlite3
import time
from datetime import date
from pathlib import Path

from sare_lotofacil.domain.masks import mask_to_numbers
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.snapshot_identity import semantic_data_snapshot_hash
from sare_lotofacil.portfolios.authority import CardGenerationService

SCHEMA_VERSION = 10

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
    data_snapshot_hash TEXT,
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
    card_count INTEGER NOT NULL CHECK (card_count BETWEEN 1 AND 100),
    cost_cents INTEGER NOT NULL CHECK (cost_cents > 0),
    predictive_evidence TEXT NOT NULL DEFAULT 'NOT_ESTABLISHED',
    evidence_label TEXT NOT NULL,
    artifact_id TEXT,
    artifact_sha256 TEXT,
    artifact_status TEXT NOT NULL DEFAULT 'FROZEN',
    artifact_schema_version TEXT NOT NULL DEFAULT 'card-artifact-v1',
    policy_id TEXT NOT NULL DEFAULT 'UNIFORM_RANDOM_PORTFOLIO_V1',
    data_snapshot_hash TEXT,
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

CREATE TABLE IF NOT EXISTS revision_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
    contest_id INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    result_mask INTEGER NOT NULL CHECK (result_mask > 0),
    hits_json TEXT NOT NULL,
    max_hits INTEGER NOT NULL CHECK (max_hits BETWEEN 5 AND 15),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (portfolio_id, contest_id, revision),
    FOREIGN KEY (contest_id, revision)
        REFERENCES contest_revisions(contest_id, revision)
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    operation TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (state IN ('RESERVED', 'COMPLETED')),
    owner_token TEXT,
    response_json TEXT,
    status_code INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (operation, idempotency_key),
    CHECK (
        (state='RESERVED' AND owner_token IS NOT NULL AND response_json IS NULL AND status_code IS NULL)
        OR
        (state='COMPLETED' AND owner_token IS NULL AND response_json IS NOT NULL AND status_code IS NOT NULL)
    )
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

CREATE INDEX IF NOT EXISTS idx_revision_evaluations_portfolio
ON revision_evaluations(portfolio_id, contest_id, revision);

CREATE INDEX IF NOT EXISTS idx_contest_revisions_date
ON contest_revisions(draw_date);

CREATE INDEX IF NOT EXISTS idx_runs_state
ON runs(execution_state);
"""

_PORTFOLIOS_V7_SQL = """
CREATE TABLE portfolios_v7 (
    portfolio_id TEXT PRIMARY KEY,
    snapshot_id TEXT REFERENCES snapshots(snapshot_id),
    target_contest INTEGER,
    seed INTEGER NOT NULL,
    card_count INTEGER NOT NULL CHECK (card_count BETWEEN 1 AND 100),
    cost_cents INTEGER NOT NULL CHECK (cost_cents > 0),
    predictive_evidence TEXT NOT NULL DEFAULT 'NOT_ESTABLISHED',
    evidence_label TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


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


def _migrate_portfolios_to_v7(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='portfolios'"
    ).fetchone()
    if not row or not row[0]:
        return
    normalized = " ".join(str(row[0]).upper().split())
    if "CARD_COUNT BETWEEN 1 AND 100" in normalized:
        return
    if "CARD_COUNT BETWEEN 3 AND 100" not in normalized:
        raise RuntimeError("unsupported portfolios schema while migrating to v7")

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            "BEGIN;\n"
            + _PORTFOLIOS_V7_SQL
            + "\nINSERT INTO portfolios_v7("
            "portfolio_id, snapshot_id, target_contest, seed, card_count, cost_cents, predictive_evidence, evidence_label, created_at"
            ") SELECT portfolio_id, snapshot_id, target_contest, seed, card_count, cost_cents, predictive_evidence, evidence_label, created_at FROM portfolios;\n"
            "DROP TABLE portfolios;\n"
            "ALTER TABLE portfolios_v7 RENAME TO portfolios;\n"
            "CREATE INDEX IF NOT EXISTS idx_portfolios_snapshot ON portfolios(snapshot_id);\n"
            "COMMIT;"
        )
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"foreign key violations after v7 migration: {violations[:5]}")


def _migrate_snapshots_to_v8(connection: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(snapshots)").fetchall()
    }
    if "data_snapshot_hash" not in columns:
        connection.execute("ALTER TABLE snapshots ADD COLUMN data_snapshot_hash TEXT")

    snapshot_ids = [
        row[0]
        for row in connection.execute(
            "SELECT snapshot_id FROM snapshots WHERE data_snapshot_hash IS NULL"
        ).fetchall()
    ]
    for snapshot_id in snapshot_ids:
        rows = connection.execute(
            "SELECT c.contest_id, c.draw_date, c.result_mask "
            "FROM snapshot_members sm "
            "JOIN contest_revisions c "
            "ON c.contest_id=sm.contest_id AND c.revision=sm.revision "
            "WHERE sm.snapshot_id=? ORDER BY c.contest_id",
            (snapshot_id,),
        ).fetchall()
        if not rows:
            continue
        records = tuple(
            validate_contest(contest_id, date.fromisoformat(draw_date), mask_to_numbers(result_mask))
            for contest_id, draw_date, result_mask in rows
        )
        connection.execute(
            "UPDATE snapshots SET data_snapshot_hash=? WHERE snapshot_id=?",
            (semantic_data_snapshot_hash(records), snapshot_id),
        )

    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_snapshots_data_hash ON snapshots(data_snapshot_hash)"
    )


def _migrate_portfolios_to_v9(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(portfolios)").fetchall()}
    additions = (
        ("artifact_id", "TEXT"),
        ("artifact_sha256", "TEXT"),
        ("artifact_status", "TEXT NOT NULL DEFAULT 'FROZEN'"),
        ("artifact_schema_version", "TEXT NOT NULL DEFAULT 'card-artifact-v1'"),
        ("policy_id", "TEXT NOT NULL DEFAULT 'UNIFORM_RANDOM_PORTFOLIO_V1'"),
        ("data_snapshot_hash", "TEXT"),
    )
    for name, ddl in additions:
        if name not in columns:
            connection.execute(f"ALTER TABLE portfolios ADD COLUMN {name} {ddl}")

    rows = connection.execute(
        "SELECT portfolio_id, snapshot_id, target_contest, seed, card_count "
        "FROM portfolios WHERE artifact_id IS NULL OR artifact_sha256 IS NULL"
    ).fetchall()
    for portfolio_id, snapshot_id, target_contest, seed, card_count in rows:
        cards = tuple(
            mask_to_numbers(mask)
            for (mask,) in connection.execute(
                "SELECT result_mask FROM portfolio_cards WHERE portfolio_id=? ORDER BY position",
                (portfolio_id,),
            ).fetchall()
        )
        if len(cards) != int(card_count):
            connection.execute(
                "UPDATE portfolios SET artifact_status='INVALIDATED', "
                "artifact_schema_version='card-artifact-v1', policy_id='LEGACY_UNVERIFIED_PORTFOLIO' "
                "WHERE portfolio_id=?",
                (portfolio_id,),
            )
            continue

        storage_snapshot_hash = None
        data_snapshot_hash = None
        if snapshot_id is not None:
            snapshot = connection.execute(
                "SELECT snapshot_hash, data_snapshot_hash FROM snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            if snapshot is None:
                raise RuntimeError(f"portfolio snapshot missing while migrating v9: {portfolio_id}")
            storage_snapshot_hash, data_snapshot_hash = snapshot

        artifact = CardGenerationService.freeze_uniform(
            card_count=int(card_count),
            seed=int(seed),
            target_contest=(int(target_contest) if target_contest is not None else None),
            data_snapshot_hash=data_snapshot_hash,
            storage_snapshot_id=snapshot_id,
            storage_snapshot_hash=storage_snapshot_hash,
        )
        if artifact.cards != cards:
            raise RuntimeError(f"portfolio generator drift while migrating v9: {portfolio_id}")
        connection.execute(
            "UPDATE portfolios SET artifact_id=?, artifact_sha256=?, artifact_status=?, "
            "artifact_schema_version=?, policy_id=?, data_snapshot_hash=? WHERE portfolio_id=?",
            (
                artifact.artifact_id,
                artifact.artifact_sha256,
                artifact.status,
                artifact.schema_version,
                artifact.policy_id,
                artifact.data_snapshot_hash,
                portfolio_id,
            ),
        )

    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_portfolios_artifact_id "
        "ON portfolios(artifact_id) WHERE artifact_id IS NOT NULL"
    )


def _migrate_idempotency_to_v10(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='idempotency_keys'"
    ).fetchone()
    if not row or not row[0]:
        return
    columns = {item[1] for item in connection.execute("PRAGMA table_info(idempotency_keys)").fetchall()}
    if {"state", "owner_token", "updated_at"}.issubset(columns):
        return

    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            "BEGIN;\n"
            "ALTER TABLE idempotency_keys RENAME TO idempotency_keys_v9;\n"
            "CREATE TABLE idempotency_keys ("
            "operation TEXT NOT NULL, idempotency_key TEXT NOT NULL, request_hash TEXT NOT NULL, "
            "state TEXT NOT NULL DEFAULT 'COMPLETED' CHECK (state IN ('RESERVED','COMPLETED')), "
            "owner_token TEXT, response_json TEXT, status_code INTEGER, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "PRIMARY KEY (operation,idempotency_key), "
            "CHECK ((state='RESERVED' AND owner_token IS NOT NULL AND response_json IS NULL AND status_code IS NULL) "
            "OR (state='COMPLETED' AND owner_token IS NULL AND response_json IS NOT NULL AND status_code IS NOT NULL))"
            ");\n"
            "INSERT INTO idempotency_keys(operation,idempotency_key,request_hash,state,owner_token,response_json,status_code,created_at,updated_at) "
            "SELECT operation,idempotency_key,request_hash,'COMPLETED',NULL,response_json,status_code,created_at,created_at "
            "FROM idempotency_keys_v9;\n"
            "DROP TABLE idempotency_keys_v9;\n"
            "COMMIT;"
        )
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def initialize_database(path: str | Path) -> Path:
    db_path = Path(path)
    with connect(db_path) as connection:
        connection.executescript(SCHEMA_SQL)
        _migrate_portfolios_to_v7(connection)
        _migrate_snapshots_to_v8(connection)
        _migrate_portfolios_to_v9(connection)
        _migrate_idempotency_to_v10(connection)
        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
    return db_path
