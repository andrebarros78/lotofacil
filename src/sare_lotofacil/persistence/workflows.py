from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sare_lotofacil.domain.masks import mask_to_numbers
from sare_lotofacil.experiments.protocol import ExperimentProtocol
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.persistence.db import connect, initialize_database
from sare_lotofacil.persistence.operations import canonical_json, persist_analysis
from sare_lotofacil.persistence.repository import persist_caixa_contest


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
class HypothesisRecord:
    hypothesis_id: str
    protocol_hash: str
    status: str
    protocol: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    experiment_id: str
    hypothesis_id: str
    run_id: str
    protocol_hash: str
    conclusion: str
    predictive_evidence: str


@dataclass(frozen=True, slots=True)
class IngestionRecord:
    ingestion_id: str
    source_class: str
    source_url: str
    contest_id: int
    revision: int
    artifact_id: str
    execution_state: str


@dataclass(frozen=True, slots=True)
class PromotionRecord:
    promotion_id: str
    experiment_id: str
    model_name: str
    predictive_evidence: str


def register_hypothesis(path: str | Path, protocol: ExperimentProtocol) -> HypothesisRecord:
    initialize_database(path)
    protocol_json = protocol.canonical_json()
    protocol_hash = protocol.protocol_hash
    with connect(path) as connection:
        snapshot = connection.execute(
            "SELECT 1 FROM snapshots WHERE snapshot_id=? AND state='PUBLISHED'", (protocol.snapshot_id,)
        ).fetchone()
        if not snapshot:
            raise KeyError(f"snapshot inexistente: {protocol.snapshot_id}")
        existing = connection.execute(
            "SELECT protocol_hash, protocol_json, status FROM hypotheses WHERE hypothesis_id=?",
            (protocol.hypothesis_id,),
        ).fetchone()
        if existing:
            if existing[0] != protocol_hash or existing[1] != protocol_json:
                raise ValueError("HYPOTHESIS_IMMUTABLE_CONFLICT")
            return HypothesisRecord(protocol.hypothesis_id, existing[0], existing[2], json.loads(existing[1]))
        connection.execute(
            "INSERT INTO hypotheses(hypothesis_id, protocol_hash, protocol_json, status) VALUES (?, ?, ?, 'REGISTERED')",
            (protocol.hypothesis_id, protocol_hash, protocol_json),
        )
        _audit(
            connection,
            "HYPOTHESIS_REGISTERED",
            "hypothesis",
            protocol.hypothesis_id,
            {"protocol_hash": protocol_hash, "snapshot_id": protocol.snapshot_id},
        )
    return HypothesisRecord(protocol.hypothesis_id, protocol_hash, "REGISTERED", json.loads(protocol_json))


def get_hypothesis(path: str | Path, hypothesis_id: str) -> HypothesisRecord:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT protocol_hash, protocol_json, status FROM hypotheses WHERE hypothesis_id=?", (hypothesis_id,)
        ).fetchone()
    if not row:
        raise KeyError(hypothesis_id)
    return HypothesisRecord(hypothesis_id, row[0], row[2], json.loads(row[1]))


def list_hypotheses(path: str | Path) -> tuple[HypothesisRecord, ...]:
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT hypothesis_id, protocol_hash, protocol_json, status FROM hypotheses ORDER BY created_at, hypothesis_id"
        ).fetchall()
    return tuple(HypothesisRecord(row[0], row[1], row[3], json.loads(row[2])) for row in rows)


def execute_experiment(path: str | Path, hypothesis_id: str) -> ExperimentRecord:
    hypothesis = get_hypothesis(path, hypothesis_id)
    protocol_data = dict(hypothesis.protocol)
    if isinstance(protocol_data.get("comparators"), list):
        protocol_data["comparators"] = tuple(protocol_data["comparators"])
    protocol = ExperimentProtocol(**protocol_data)
    protocol.validate()

    with connect(path) as connection:
        connection.execute(
            "UPDATE hypotheses SET status='IN_PROOF', updated_at=CURRENT_TIMESTAMP WHERE hypothesis_id=?",
            (hypothesis_id,),
        )

    run = persist_analysis(
        path,
        protocol.snapshot_id,
        min_train=protocol.min_train,
        delta_min=protocol.delta_min,
    )
    conclusion = str(run.result.get("scientific_conclusion") or "INCONCLUSIVO")
    identity = {
        "hypothesis_id": hypothesis_id,
        "protocol_hash": hypothesis.protocol_hash,
        "run_id": run.run_id,
    }
    digest = hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()
    experiment_id = f"experiment-{digest[:24]}"
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO experiment_runs(experiment_id, hypothesis_id, run_id, protocol_hash, conclusion, predictive_evidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (experiment_id, hypothesis_id, run.run_id, hypothesis.protocol_hash, conclusion, run.predictive_evidence),
        )
        connection.execute(
            "UPDATE hypotheses SET status='CONCLUDED', updated_at=CURRENT_TIMESTAMP WHERE hypothesis_id=?",
            (hypothesis_id,),
        )
        _audit(
            connection,
            "EXPERIMENT_CONCLUDED",
            "experiment",
            experiment_id,
            {
                "hypothesis_id": hypothesis_id,
                "run_id": run.run_id,
                "protocol_hash": hypothesis.protocol_hash,
                "conclusion": conclusion,
                "predictive_evidence": run.predictive_evidence,
            },
        )
    return ExperimentRecord(
        experiment_id,
        hypothesis_id,
        run.run_id,
        hypothesis.protocol_hash,
        conclusion,
        run.predictive_evidence,
    )


def get_experiment(path: str | Path, experiment_id: str) -> ExperimentRecord:
    with connect(path) as connection:
        row = connection.execute(
            "SELECT hypothesis_id, run_id, protocol_hash, conclusion, predictive_evidence "
            "FROM experiment_runs WHERE experiment_id=?",
            (experiment_id,),
        ).fetchone()
    if not row:
        raise KeyError(experiment_id)
    return ExperimentRecord(experiment_id, row[0], row[1], row[2], row[3], row[4])


def promote_model(path: str | Path, experiment_id: str, model_name: str) -> PromotionRecord:
    if not model_name.strip():
        raise ValueError("model_name obrigatório")
    experiment = get_experiment(path, experiment_id)
    if experiment.predictive_evidence != "REPLICATED":
        raise PermissionError("PREDICTIVE_EVIDENCE_NOT_REPLICATED")
    identity = {"experiment_id": experiment_id, "model_name": model_name}
    promotion_id = "promotion-" + hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:24]
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO model_promotions(promotion_id, experiment_id, model_name, predictive_evidence) "
            "VALUES (?, ?, ?, 'REPLICATED')",
            (promotion_id, experiment_id, model_name),
        )
        _audit(connection, "MODEL_PROMOTED", "promotion", promotion_id, identity)
    return PromotionRecord(promotion_id, experiment_id, model_name, "REPLICATED")


def record_caixa_ingestion(path: str | Path, contest: CaixaContest) -> IngestionRecord:
    persisted = persist_caixa_contest(path, contest, source_class="OFICIAL_DIRETA")
    identity = {
        "source_url": contest.source_url,
        "contest_id": persisted.contest_id,
        "revision": persisted.revision,
        "artifact_id": persisted.artifact_id,
    }
    ingestion_id = "ingestion-" + hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest()[:24]
    with connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO ingestion_runs(ingestion_id, source_class, source_url, contest_id, revision, artifact_id, execution_state, finished_at) "
            "VALUES (?, 'OFICIAL_DIRETA', ?, ?, ?, ?, 'COMPLETED', CURRENT_TIMESTAMP)",
            (ingestion_id, contest.source_url, persisted.contest_id, persisted.revision, persisted.artifact_id),
        )
        _audit(
            connection,
            "CAIXA_CONTEST_INGESTED",
            "ingestion",
            ingestion_id,
            {**identity, "created_revision": persisted.created},
        )
    return IngestionRecord(
        ingestion_id,
        "OFICIAL_DIRETA",
        contest.source_url,
        persisted.contest_id,
        persisted.revision,
        persisted.artifact_id,
        "COMPLETED",
    )


def list_ingestions(path: str | Path, *, limit: int = 100) -> tuple[IngestionRecord, ...]:
    if not 1 <= limit <= 500:
        raise ValueError("limit deve estar entre 1 e 500")
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT ingestion_id, source_class, source_url, contest_id, revision, artifact_id, execution_state "
            "FROM ingestion_runs ORDER BY created_at DESC, ingestion_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return tuple(IngestionRecord(*row) for row in rows)


def get_latest_contest(path: str | Path, contest_id: int) -> dict[str, Any]:
    if contest_id <= 0:
        raise ValueError("contest_id deve ser positivo")
    with connect(path) as connection:
        row = connection.execute(
            "SELECT contest_id, revision, draw_date, result_mask, source_class, source_artifact_id, availability_at "
            "FROM contest_revisions WHERE contest_id=? ORDER BY revision DESC LIMIT 1",
            (contest_id,),
        ).fetchone()
        if not row:
            raise KeyError(contest_id)
        tiers = connection.execute(
            "SELECT hits, winners, prize_cents FROM prize_tiers WHERE contest_id=? AND revision=? ORDER BY hits DESC",
            (row[0], row[1]),
        ).fetchall()
    return {
        "contest_id": row[0],
        "revision": row[1],
        "draw_date": row[2],
        "numbers": list(mask_to_numbers(row[3])),
        "source_class": row[4],
        "source_artifact_id": row[5],
        "availability_at": row[6],
        "prize_tiers": [
            {"hits": tier[0], "winners": tier[1], "prize_cents": tier[2]} for tier in tiers
        ],
    }


def list_contests(path: str | Path, *, limit: int = 100, offset: int = 0) -> tuple[dict[str, Any], ...]:
    if not 1 <= limit <= 500:
        raise ValueError("limit deve estar entre 1 e 500")
    if offset < 0:
        raise ValueError("offset não pode ser negativo")
    with connect(path) as connection:
        rows = connection.execute(
            "SELECT c.contest_id, c.revision, c.draw_date, c.result_mask, c.source_class "
            "FROM contest_revisions c "
            "JOIN (SELECT contest_id, MAX(revision) revision FROM contest_revisions GROUP BY contest_id) x "
            "ON x.contest_id=c.contest_id AND x.revision=c.revision "
            "ORDER BY c.contest_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return tuple(
        {
            "contest_id": row[0],
            "revision": row[1],
            "draw_date": row[2],
            "numbers": list(mask_to_numbers(row[3])),
            "source_class": row[4],
        }
        for row in rows
    )
