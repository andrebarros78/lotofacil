from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.domain.masks import mask_to_numbers, numbers_to_mask, normalize_numbers
from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.repository import load_snapshot_draws
from sare_lotofacil.portfolios.authority import CardGenerationService, STATUS_FROZEN
from sare_lotofacil.portfolios.core import Portfolio, audit_portfolio


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _audit(connection, action: str, entity_type: str, entity_id: str, detail: dict[str, Any]) -> None:
    detail_json = canonical_json(detail)
    event_id = "audit-" + hashlib.sha256(
        f"{action}|{entity_type}|{entity_id}|{detail_json}".encode("utf-8")
    ).hexdigest()[:24]
    connection.execute(
        "INSERT OR IGNORE INTO audit_events(event_id, action, entity_type, entity_id, detail_json) VALUES (?, ?, ?, ?, ?)",
        (event_id, action, entity_type, entity_id, detail_json),
    )


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    execution_state: str
    snapshot_id: str
    predictive_evidence: str
    result: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PortfolioRecord:
    portfolio_id: str
    snapshot_id: str | None
    target_contest: int | None
    seed: int
    cards: tuple[tuple[int, ...], ...]
    cost_cents: int
    predictive_evidence: str
    evidence_label: str
    artifact_id: str
    artifact_sha256: str
    artifact_status: str
    artifact_schema_version: str
    policy_id: str
    data_snapshot_hash: str | None


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    portfolio_id: str
    result: tuple[int, ...]
    hits: tuple[int, ...]
    max_hits: int


@dataclass(frozen=True, slots=True)
class RevisionEvaluationRecord:
    evaluation_id: str
    portfolio_id: str
    contest_id: int
    revision: int
    result: tuple[int, ...]
    hits: tuple[int, ...]
    max_hits: int


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    state: str
    owner_token: str | None
    response_json: str | None
    status_code: int | None


def persist_analysis(
    path: str | Path,
    snapshot_id: str,
    *,
    min_train: int | None = None,
    delta_min: float = 0.0,
) -> RunRecord:
    initialize_database(path)
    draws = load_snapshot_draws(path, snapshot_id)
    report = analyze_core(draws, min_train=min_train, delta_min=delta_min)
    result = report.to_dict()
    config = {"snapshot_id": snapshot_id, "min_train": report.min_train, "delta_min": delta_min}
    config_hash = payload_hash(config)
    run_id = f"run-{config_hash[:24]}"
    result_json = canonical_json(result)
    with connect(path) as connection:
        existing = connection.execute(
            "SELECT r.execution_state, r.predictive_evidence, rr.result_json "
            "FROM runs r JOIN run_results rr ON rr.run_id=r.run_id WHERE r.run_id=?",
            (run_id,),
        ).fetchone()
        if existing:
            return RunRecord(run_id, existing[0], snapshot_id, existing[1], json.loads(existing[2]))
        connection.execute(
            "INSERT INTO runs(run_id, run_type, execution_state, snapshot_id, code_commit, config_hash, technical_status, predictive_evidence, finished_at) "
            "VALUES (?, 'ANALYSIS', 'COMPLETED', ?, ?, ?, 'VALID', ?, CURRENT_TIMESTAMP)",
            (run_id, snapshot_id, os.getenv("SARE_CODE_COMMIT"), config_hash, report.predictive_evidence),
        )
        connection.execute("INSERT INTO run_results(run_id, result_json) VALUES (?, ?)", (run_id, result_json))
        _audit(connection, "ANALYSIS_COMPLETED", "run", run_id, config)
    return RunRecord(run_id, "COMPLETED", snapshot_id, report.predictive_evidence, result)


def get_run(path: str | Path, run_id: str) -> RunRecord:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT r.execution_state, r.snapshot_id, r.predictive_evidence, rr.result_json "
            "FROM runs r JOIN run_results rr ON rr.run_id=r.run_id WHERE r.run_id=?",
            (run_id,),
        ).fetchone()
    if not row:
        raise KeyError(run_id)
    return RunRecord(run_id, row[0], row[1], row[2], json.loads(row[3]))


def persist_uniform_portfolio(
    path: str | Path,
    *,
    card_count: int,
    seed: int,
    snapshot_id: str | None = None,
    target_contest: int | None = None,
) -> PortfolioRecord:
    initialize_database(path)
    storage_snapshot_hash = None
    data_snapshot_hash = None
    with connect(path) as connection:
        if snapshot_id is not None:
            snapshot = connection.execute(
                "SELECT snapshot_hash, data_snapshot_hash FROM snapshots WHERE snapshot_id=?",
                (snapshot_id,),
            ).fetchone()
            if snapshot is None:
                raise KeyError(f"snapshot inexistente: {snapshot_id}")
            storage_snapshot_hash, data_snapshot_hash = snapshot

    artifact = CardGenerationService.freeze_uniform(
        card_count=card_count,
        seed=seed,
        target_contest=target_contest,
        data_snapshot_hash=data_snapshot_hash,
        storage_snapshot_id=snapshot_id,
        storage_snapshot_hash=storage_snapshot_hash,
    )
    if artifact.status != STATUS_FROZEN or not artifact.operational_use_allowed:
        raise RuntimeError("PERSISTED_PORTFOLIO_MUST_BE_FROZEN")
    portfolio_id = f"portfolio-{artifact.artifact_sha256[:24]}"
    with connect(path) as connection:
        existing = connection.execute("SELECT 1 FROM portfolios WHERE portfolio_id=?", (portfolio_id,)).fetchone()
        if not existing:
            connection.execute(
                "INSERT INTO portfolios("
                "portfolio_id, snapshot_id, target_contest, seed, card_count, cost_cents, "
                "predictive_evidence, evidence_label, artifact_id, artifact_sha256, artifact_status, "
                "artifact_schema_version, policy_id, data_snapshot_hash"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    portfolio_id,
                    snapshot_id,
                    target_contest,
                    seed,
                    artifact.card_count,
                    artifact.cost_cents,
                    artifact.predictive_evidence,
                    artifact.evidence_label,
                    artifact.artifact_id,
                    artifact.artifact_sha256,
                    artifact.status,
                    artifact.schema_version,
                    artifact.policy_id,
                    artifact.data_snapshot_hash,
                ),
            )
            connection.executemany(
                "INSERT INTO portfolio_cards(portfolio_id, position, result_mask) VALUES (?, ?, ?)",
                [(portfolio_id, index, numbers_to_mask(card)) for index, card in enumerate(artifact.cards, start=1)],
            )
            _audit(
                connection,
                "PORTFOLIO_FROZEN",
                "card_artifact",
                artifact.artifact_id,
                {
                    "portfolio_id": portfolio_id,
                    "card_count": artifact.card_count,
                    "seed": seed,
                    "target_contest": target_contest,
                    "artifact_sha256": artifact.artifact_sha256,
                    "policy_id": artifact.policy_id,
                },
            )
    return get_portfolio(path, portfolio_id)


def get_portfolio(path: str | Path, portfolio_id: str) -> PortfolioRecord:
    initialize_database(path)
    with connect(path) as connection:
        row = connection.execute(
            "SELECT snapshot_id, target_contest, seed, cost_cents, predictive_evidence, evidence_label, "
            "artifact_id, artifact_sha256, artifact_status, artifact_schema_version, policy_id, data_snapshot_hash "
            "FROM portfolios WHERE portfolio_id=?",
            (portfolio_id,),
        ).fetchone()
        if not row:
            raise KeyError(portfolio_id)
        cards = tuple(
            mask_to_numbers(mask)
            for (mask,) in connection.execute(
                "SELECT result_mask FROM portfolio_cards WHERE portfolio_id=? ORDER BY position",
                (portfolio_id,),
            ).fetchall()
        )
        storage_snapshot_hash = None
        if row[0] is not None:
            snapshot = connection.execute(
                "SELECT snapshot_hash FROM snapshots WHERE snapshot_id=?",
                (row[0],),
            ).fetchone()
            if snapshot is None:
                raise RuntimeError("PORTFOLIO_STORAGE_SNAPSHOT_MISSING")
            storage_snapshot_hash = snapshot[0]
    if not row[6] or not row[7]:
        raise RuntimeError("PORTFOLIO_CARD_ARTIFACT_MISSING")
    expected_artifact = CardGenerationService.freeze_uniform(
        card_count=len(cards),
        seed=int(row[2]),
        target_contest=(int(row[1]) if row[1] is not None else None),
        data_snapshot_hash=row[11],
        storage_snapshot_id=row[0],
        storage_snapshot_hash=storage_snapshot_hash,
    )
    if (
        expected_artifact.cards != cards
        or row[6] != expected_artifact.artifact_id
        or row[7] != expected_artifact.artifact_sha256
        or row[8] != expected_artifact.status
        or row[9] != expected_artifact.schema_version
        or row[10] != expected_artifact.policy_id
    ):
        raise RuntimeError("PORTFOLIO_CARD_ARTIFACT_MISMATCH")
    return PortfolioRecord(
        portfolio_id,
        row[0],
        row[1],
        row[2],
        cards,
        row[3],
        row[4],
        row[5],
        row[6],
        row[7],
        row[8],
        row[9],
        row[10],
        row[11],
    )


def evaluate_portfolio(path: str | Path, portfolio_id: str, draw: Iterable[int]) -> EvaluationRecord:
    record = get_portfolio(path, portfolio_id)
    result = normalize_numbers(draw)
    portfolio = Portfolio(
        seed=record.seed,
        cards=record.cards,
        cost_cents=record.cost_cents,
        evidence_label=record.evidence_label,
    )
    hits = audit_portfolio(portfolio, result)
    result_mask = numbers_to_mask(result)
    evaluation_id = f"evaluation-{payload_hash({'portfolio_id': portfolio_id, 'result_mask': result_mask})[:24]}"
    hits_json = canonical_json(hits)
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO evaluations(evaluation_id, portfolio_id, result_mask, hits_json, max_hits) VALUES (?, ?, ?, ?, ?)",
            (evaluation_id, portfolio_id, result_mask, hits_json, max(hits)),
        )
        _audit(
            connection,
            "PORTFOLIO_EVALUATED",
            "evaluation",
            evaluation_id,
            {"portfolio_id": portfolio_id, "max_hits": max(hits)},
        )
    return EvaluationRecord(evaluation_id, portfolio_id, result, hits, max(hits))


def evaluate_portfolio_revision(
    path: str | Path,
    portfolio_id: str,
    contest_id: int,
    revision: int,
) -> RevisionEvaluationRecord:
    initialize_database(path)
    record = get_portfolio(path, portfolio_id)
    with connect(path) as connection:
        row = connection.execute(
            "SELECT result_mask FROM contest_revisions WHERE contest_id=? AND revision=?",
            (contest_id, revision),
        ).fetchone()
    if not row:
        raise KeyError((contest_id, revision))

    result_mask = int(row[0])
    result = mask_to_numbers(result_mask)
    portfolio = Portfolio(
        seed=record.seed,
        cards=record.cards,
        cost_cents=record.cost_cents,
        evidence_label=record.evidence_label,
    )
    hits = audit_portfolio(portfolio, result)
    identity = {"portfolio_id": portfolio_id, "contest_id": contest_id, "revision": revision}
    evaluation_id = f"revision-evaluation-{payload_hash(identity)[:24]}"
    hits_json = canonical_json(hits)
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO revision_evaluations(evaluation_id, portfolio_id, contest_id, revision, result_mask, hits_json, max_hits) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (evaluation_id, portfolio_id, contest_id, revision, result_mask, hits_json, max(hits)),
        )
        _audit(
            connection,
            "PORTFOLIO_REVISION_EVALUATED",
            "revision_evaluation",
            evaluation_id,
            {**identity, "max_hits": max(hits)},
        )
    return RevisionEvaluationRecord(evaluation_id, portfolio_id, contest_id, revision, result, hits, max(hits))


def list_snapshots(path: str | Path) -> tuple[dict[str, Any], ...]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT s.snapshot_id, s.snapshot_hash, s.state, COUNT(sm.contest_id) "
            "FROM snapshots s LEFT JOIN snapshot_members sm ON sm.snapshot_id=s.snapshot_id "
            "GROUP BY s.snapshot_id ORDER BY s.created_at DESC, s.snapshot_id"
        ).fetchall()
    return tuple(
        {"snapshot_id": row[0], "snapshot_hash": row[1], "state": row[2], "contest_count": row[3]}
        for row in rows
    )


def get_idempotency(path: str | Path, operation: str, key: str) -> IdempotencyRecord | None:
    initialize_database(path)
    with connect(path) as connection:
        row = connection.execute(
            "SELECT request_hash, state, owner_token, response_json, status_code "
            "FROM idempotency_keys WHERE operation=? AND idempotency_key=?",
            (operation, key),
        ).fetchone()
    return IdempotencyRecord(*row) if row else None


def reserve_idempotency(
    path: str | Path,
    operation: str,
    key: str,
    request_digest: str,
    owner_token: str,
) -> IdempotencyRecord:
    if not owner_token:
        raise ValueError("owner_token obrigatório")
    initialize_database(path)
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT request_hash, state, owner_token, response_json, status_code "
            "FROM idempotency_keys WHERE operation=? AND idempotency_key=?",
            (operation, key),
        ).fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO idempotency_keys("
                "operation,idempotency_key,request_hash,state,owner_token,response_json,status_code"
                ") VALUES (?, ?, ?, 'RESERVED', ?, NULL, NULL)",
                (operation, key, request_digest, owner_token),
            )
            return IdempotencyRecord(request_digest, "RESERVED", owner_token, None, None)
        return IdempotencyRecord(*row)


def complete_idempotency(
    path: str | Path,
    operation: str,
    key: str,
    request_digest: str,
    owner_token: str,
    response_payload: dict[str, Any],
    status_code: int,
) -> None:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE idempotency_keys SET state='COMPLETED', owner_token=NULL, response_json=?, "
            "status_code=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE operation=? AND idempotency_key=? AND request_hash=? "
            "AND state='RESERVED' AND owner_token=?",
            (
                canonical_json(response_payload),
                status_code,
                operation,
                key,
                request_digest,
                owner_token,
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("IDEMPOTENCY_RESERVATION_LOST")


def release_idempotency(
    path: str | Path,
    operation: str,
    key: str,
    request_digest: str,
    owner_token: str,
) -> None:
    with connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "DELETE FROM idempotency_keys WHERE operation=? AND idempotency_key=? "
            "AND request_hash=? AND state='RESERVED' AND owner_token=?",
            (operation, key, request_digest, owner_token),
        )


def save_idempotency(
    path: str | Path,
    operation: str,
    key: str,
    request_digest: str,
    response_payload: dict[str, Any],
    status_code: int,
) -> None:
    owner_token = f"legacy-save-{payload_hash({'operation': operation, 'key': key, 'request_hash': request_digest})[:24]}"
    record = reserve_idempotency(path, operation, key, request_digest, owner_token)
    if record.request_hash != request_digest:
        raise sqlite3.IntegrityError("IDEMPOTENCY_KEY_CONFLICT")
    if record.state == "COMPLETED":
        raise sqlite3.IntegrityError("IDEMPOTENCY_KEY_EXISTS")
    if record.owner_token != owner_token:
        raise sqlite3.IntegrityError("IDEMPOTENCY_KEY_RESERVED")
    complete_idempotency(path, operation, key, request_digest, owner_token, response_payload, status_code)


def audit_event_count(path: str | Path) -> int:
    with connect(path) as connection:
        return int(connection.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0])


def list_audit_events(path: str | Path, *, limit: int = 100) -> tuple[dict[str, Any], ...]:
    if not 1 <= limit <= 500:
        raise ValueError("limit deve estar entre 1 e 500")
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT event_id, action, entity_type, entity_id, detail_json, created_at "
            "FROM audit_events ORDER BY created_at DESC, event_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return tuple(
        {
            "event_id": row[0],
            "action": row[1],
            "entity_type": row[2],
            "entity_id": row[3],
            "detail": json.loads(row[4]),
            "created_at": row[5],
        }
        for row in rows
    )
