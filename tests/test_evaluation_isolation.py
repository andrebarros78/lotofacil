from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from sare_lotofacil.evaluation import CANONICAL_EVALUATION, MANUAL_EVALUATION
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect, initialize_database
from sare_lotofacil.persistence.operations import (
    evaluate_portfolio,
    evaluate_portfolio_revision,
    persist_uniform_portfolio,
)
from sare_lotofacil.persistence.repository import persist_caixa_contest


def _persist_target(db, contest_id: int = 106):
    numbers = tuple(range(1, 16))
    record = validate_contest(contest_id, date(2026, 9, 21), numbers)
    contest = CaixaContest(
        record=record,
        prize_tiers=(),
        source_url=f"fixture://caixa/{contest_id}",
        captured_at=datetime(2026, 9, 21, tzinfo=timezone.utc),
        raw_payload={"numero": contest_id, "listaDezenas": list(numbers)},
    )
    persisted = persist_caixa_contest(db, contest, source_class="CAIXA")
    return persisted, numbers


def test_manual_and_canonical_evaluations_are_semantically_disjoint(tmp_path) -> None:
    db = tmp_path / "sare.db"
    persisted, numbers = _persist_target(db)
    portfolio = persist_uniform_portfolio(
        db,
        card_count=3,
        seed=77,
        target_contest=106,
    )

    manual = evaluate_portfolio(db, portfolio.portfolio_id, numbers)
    canonical = evaluate_portfolio_revision(
        db,
        portfolio.portfolio_id,
        106,
        persisted.revision,
    )

    assert manual.evaluation_class == MANUAL_EVALUATION
    assert manual.evidence_eligible is False
    assert manual.source_class == "USER_SUPPLIED"

    assert canonical.evaluation_class == CANONICAL_EVALUATION
    assert canonical.evidence_eligible is True
    assert canonical.source_class == "CAIXA"
    assert canonical.contest_id == 106
    assert canonical.revision == persisted.revision
    assert canonical.result == manual.result

    with connect(db) as connection:
        manual_row = connection.execute(
            "SELECT evaluation_class, evidence_eligible, source_class "
            "FROM evaluations WHERE evaluation_id=?",
            (manual.evaluation_id,),
        ).fetchone()
        canonical_row = connection.execute(
            "SELECT evaluation_class, evidence_eligible, source_class, contest_id, revision "
            "FROM revision_evaluations WHERE evaluation_id=?",
            (canonical.evaluation_id,),
        ).fetchone()

    assert manual_row == ("MANUAL_EVALUATION", 0, "USER_SUPPLIED")
    assert canonical_row == (
        "CANONICAL_EVALUATION",
        1,
        "CAIXA",
        106,
        persisted.revision,
    )


def test_canonical_evaluation_requires_frozen_target_identity(tmp_path) -> None:
    db = tmp_path / "sare.db"
    persisted, _ = _persist_target(db)

    wrong_target = persist_uniform_portfolio(
        db,
        card_count=1,
        seed=1,
        target_contest=107,
    )
    with pytest.raises(ValueError, match="CANONICAL_EVALUATION_TARGET_MISMATCH"):
        evaluate_portfolio_revision(
            db,
            wrong_target.portfolio_id,
            106,
            persisted.revision,
        )

    unbound = persist_uniform_portfolio(
        db,
        card_count=1,
        seed=2,
        target_contest=None,
    )
    with pytest.raises(ValueError, match="CANONICAL_EVALUATION_REQUIRES_TARGET"):
        evaluate_portfolio_revision(
            db,
            unbound.portfolio_id,
            106,
            persisted.revision,
        )


def test_database_triggers_block_cross_channel_spoofing(tmp_path) -> None:
    db = tmp_path / "sare.db"
    persisted, numbers = _persist_target(db)
    portfolio = persist_uniform_portfolio(
        db,
        card_count=1,
        seed=3,
        target_contest=106,
    )
    mask = sum(1 << (number - 1) for number in numbers)

    with connect(db) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="MANUAL_EVALUATION_ISOLATION_VIOLATION"):
            connection.execute(
                "INSERT INTO evaluations("
                "evaluation_id, portfolio_id, evaluation_class, evidence_eligible, "
                "source_class, result_mask, hits_json, max_hits"
                ") VALUES ('spoof-manual', ?, 'CANONICAL_EVALUATION', 1, "
                "'CAIXA', ?, '[15]', 15)",
                (portfolio.portfolio_id, mask),
            )

        with pytest.raises(sqlite3.IntegrityError, match="CANONICAL_EVALUATION_CLASS_VIOLATION"):
            connection.execute(
                "INSERT INTO revision_evaluations("
                "evaluation_id, portfolio_id, evaluation_class, evidence_eligible, "
                "source_class, contest_id, revision, result_mask, hits_json, max_hits"
                ") VALUES ('spoof-canonical', ?, 'MANUAL_EVALUATION', 0, "
                "'CAIXA', 106, ?, ?, '[15]', 15)",
                (portfolio.portfolio_id, persisted.revision, mask),
            )


def test_v10_rows_migrate_with_conservative_evaluation_labels(tmp_path) -> None:
    db = tmp_path / "legacy-v10.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO schema_meta VALUES('schema_version','10');

            CREATE TABLE snapshots(
                snapshot_id TEXT PRIMARY KEY,
                snapshot_hash TEXT NOT NULL UNIQUE,
                data_snapshot_hash TEXT,
                state TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE portfolios(
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

            CREATE TABLE contest_revisions(
                contest_id INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                draw_date TEXT NOT NULL,
                result_mask INTEGER NOT NULL,
                source_class TEXT NOT NULL,
                source_artifact_id TEXT,
                availability_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(contest_id, revision)
            );

            CREATE TABLE evaluations(
                evaluation_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
                result_mask INTEGER NOT NULL,
                hits_json TEXT NOT NULL,
                max_hits INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE revision_evaluations(
                evaluation_id TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id),
                contest_id INTEGER NOT NULL,
                revision INTEGER NOT NULL,
                result_mask INTEGER NOT NULL,
                hits_json TEXT NOT NULL,
                max_hits INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(portfolio_id, contest_id, revision)
            );
            """
        )
        connection.execute(
            "INSERT INTO portfolios("
            "portfolio_id,target_contest,seed,card_count,cost_cents,evidence_label,"
            "artifact_id,artifact_sha256"
            ") VALUES ('p1',106,1,1,350,'legacy','card-x','hash-x')"
        )
        mask = sum(1 << (number - 1) for number in range(1, 16))
        connection.execute(
            "INSERT INTO contest_revisions("
            "contest_id,revision,draw_date,result_mask,source_class,source_artifact_id"
            ") VALUES (106,1,'2026-09-21',?,'CAIXA','source-1')",
            (mask,),
        )
        connection.execute(
            "INSERT INTO evaluations VALUES("
            "'manual-old','p1',?,'[15]',15,CURRENT_TIMESTAMP)",
            (mask,),
        )
        connection.execute(
            "INSERT INTO revision_evaluations VALUES("
            "'canonical-old','p1',106,1,?,'[15]',15,CURRENT_TIMESTAMP)",
            (mask,),
        )

    initialize_database(db)

    with connect(db) as connection:
        version = int(
            connection.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0]
        )
        manual = connection.execute(
            "SELECT evaluation_class,evidence_eligible,source_class "
            "FROM evaluations WHERE evaluation_id='manual-old'"
        ).fetchone()
        canonical = connection.execute(
            "SELECT evaluation_class,evidence_eligible,source_class,source_artifact_id "
            "FROM revision_evaluations WHERE evaluation_id='canonical-old'"
        ).fetchone()

    assert version == SCHEMA_VERSION == 11
    assert manual == ("MANUAL_EVALUATION", 0, "USER_SUPPLIED")
    assert canonical == ("CANONICAL_EVALUATION", 1, "CAIXA", "source-1")
