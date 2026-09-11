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
from sare_lotofacil.portfolios.core import Portfolio, audit_portfolio, generate_uniform_portfolio


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


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    evaluation_id: str
    portfolio_id: str
    result: tuple[int, ...]
    hits: tuple[int, ...]
    max_hits: int


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    request_hash: str
    response_json: str
    status_code: int


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
    portfolio = generate_uniform_portfolio(card_count, seed=seed)
    identity = {
        "snapshot_id": snapshot_id,
        "target_contest": target_contest,
        "seed": seed,
        "cards": portfolio.cards,
        "predictive_evidence": "NOT_ESTABLISHED",
    }
    portfolio_id = f"portfolio-{payload_hash(identity)[:24]}"
    with connect(path) as connection:
        if snapshot_id is not None:
            exists = connection.execute("SELECT 1 FROM snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            if not exists:
                raise KeyError(f"snapshot inexistente: {snapshot_id}")
        existing = connection.execute("SELECT 1 FROM portfolios WHERE portfolio_id=?", (portfolio_id,)).fetchone()
        if not existing:
            connection.execute(
                "INSERT INTO portfolios(portfolio_id, snapshot_id, target_contest, seed, card_count, cost_cents, predictive_evidence, evidence_label) "
                "VALUES (?, ?, ?, ?, ?, ?, 'NOT_ESTABLISHED', ?)",
                (portfolio_id, snapshot_id, target_contest, seed, len(portfolio.cards), portfolio.cost_cents, portfolio.evidence_label),
            )
            connection.executemany(
                "INSERT INTO portfolio_cards(portfolio_id, position, result_mask) VALUES (?, ?, ?)",
                [(portfolio_id, index, numbers_to_mask(card)) for index, card in enumerate(portfolio.cards, start=1)],
            )
            _audit(
                connection,
                "PORTFOLIO_FROZEN",
                "portfolio",
                portfolio_id,
                {"card_count": card_count, "seed": seed, "target_contest": target_contest},
            )
    return get_portfolio(path, portfolio_id)


def get_portfolio(path: str | Path, portfolio_id: str) -> PortfolioRecord:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT snapshot_id, target_contest, seed, cost_cents, predictive_evidence, evidence_label "
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
    return PortfolioRecord(portfolio_id, row[0], row[1], row[2], cards, row[3], row[4], row[5])


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
            "SELECT request_hash, response_json, status_code FROM idempotency_keys WHERE operation=? AND idempotency_key=?",
            (operation, key),
        ).fetchone()
    return IdempotencyRecord(*row) if row else None


def save_idempotency(
    path: str | Path,
    operation: str,
    key: str,
    request_digest: str,
    response_payload: dict[str, Any],
    status_code: int,
) -> None:
    with connect(path) as connection:
        connection.execute(
            "INSERT INTO idempotency_keys(operation, idempotency_key, request_hash, response_json, status_code) VALUES (?, ?, ?, ?, ?)",
            (operation, key, request_digest, canonical_json(response_payload), status_code),
        )


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
