from __future__ import annotations

import hmac
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from sare_lotofacil.api.legacy_app import create_app as _legacy_create_app
from sare_lotofacil.experiments.protocol import ExperimentProtocol
from sare_lotofacil.ingestion.caixa import fetch_caixa_contest
from sare_lotofacil.persistence.operations import (
    get_idempotency,
    get_portfolio,
    payload_hash,
    save_idempotency,
)
from sare_lotofacil.persistence.repository import create_latest_snapshot
from sare_lotofacil.persistence.workflows import (
    execute_experiment,
    get_experiment,
    get_hypothesis,
    get_latest_contest,
    list_contests,
    list_hypotheses,
    list_ingestions,
    promote_model,
    record_caixa_ingestion,
    register_hypothesis,
)


class CaixaIngestionRequest(BaseModel):
    contest_id: int | None = Field(default=None, ge=1)


class HypothesisRequest(BaseModel):
    hypothesis_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=3, max_length=2000)
    h0: str = Field(min_length=1, max_length=2000)
    h1: str = Field(min_length=1, max_length=2000)
    snapshot_id: str = Field(min_length=1, max_length=128)
    variables: str = Field(min_length=1, max_length=4000)
    model: str = Field(min_length=1, max_length=4000)
    comparators: list[str] = Field(min_length=1, max_length=20)
    multiplicity_family: str = Field(min_length=1, max_length=2000)
    sample_plan: str = Field(min_length=1, max_length=2000)
    stopping_rule: str = Field(min_length=1, max_length=2000)
    code_environment: str = Field(min_length=1, max_length=2000)
    metric_primary: str = "brier_score"
    baseline: str = "uniform_p_0_6"
    correction: str = "holm"
    evidence_mode: str = "RETROSPECTIVO_REVISADO"
    delta_min: float = Field(default=0.0, ge=0.0)
    min_train: int = Field(default=100, ge=1)

    def to_protocol(self) -> ExperimentProtocol:
        data = self.model_dump()
        data["comparators"] = tuple(data["comparators"])
        return ExperimentProtocol(**data)


class ExperimentRequest(BaseModel):
    hypothesis_id: str = Field(min_length=1, max_length=128)


class PromotionRequest(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=256)


def _hypothesis_payload(record) -> dict[str, Any]:
    return {
        "hypothesis_id": record.hypothesis_id,
        "protocol_hash": record.protocol_hash,
        "status": record.status,
        "protocol": record.protocol,
    }


def _experiment_payload(record) -> dict[str, Any]:
    return {
        "experiment_id": record.experiment_id,
        "hypothesis_id": record.hypothesis_id,
        "run_id": record.run_id,
        "protocol_hash": record.protocol_hash,
        "conclusion": record.conclusion,
        "predictive_evidence": record.predictive_evidence,
    }


def create_app(db_path: str | Path, *, write_token: str | None = None, max_body_bytes: int = 65_536):
    path = Path(db_path)
    app = _legacy_create_app(path, write_token=write_token, max_body_bytes=max_body_bytes)
    app.version = "0.3.0"

    def require_write_auth(token: str | None) -> None:
        if not write_token:
            raise HTTPException(status_code=503, detail="WRITE_DISABLED")
        if token is None:
            raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
        if not hmac.compare_digest(token, write_token):
            raise HTTPException(status_code=403, detail="AUTH_INVALID")

    def idempotent(
        operation: str,
        key: str | None,
        request_payload: dict[str, Any],
        callback: Callable[[], tuple[dict[str, Any], int]],
    ) -> JSONResponse:
        if key is None or not key.strip():
            raise HTTPException(status_code=400, detail="IDEMPOTENCY_KEY_REQUIRED")
        if len(key) > 128:
            raise HTTPException(status_code=400, detail="IDEMPOTENCY_KEY_TOO_LONG")
        digest = payload_hash(request_payload)
        existing = get_idempotency(path, operation, key)
        if existing:
            if existing.request_hash != digest:
                raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_CONFLICT")
            return JSONResponse(json.loads(existing.response_json), status_code=existing.status_code)
        payload, status = callback()
        try:
            save_idempotency(path, operation, key, digest, payload, status)
        except sqlite3.IntegrityError:
            existing = get_idempotency(path, operation, key)
            if not existing or existing.request_hash != digest:
                raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_CONFLICT")
            return JSONResponse(json.loads(existing.response_json), status_code=existing.status_code)
        return JSONResponse(payload, status_code=status)

    @app.get("/v1/contests")
    def contests(limit: int = 100, offset: int = 0):
        try:
            return {"items": list(list_contests(path, limit=limit, offset=offset))}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/v1/contests/{contest_id}")
    def contest_by_id(contest_id: int):
        try:
            return get_latest_contest(path, contest_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="CONTEST_NOT_FOUND")
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/v1/ingestions")
    def ingestions(limit: int = 100):
        try:
            records = list_ingestions(path, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        return {
            "items": [
                {
                    "ingestion_id": r.ingestion_id,
                    "source_class": r.source_class,
                    "source_url": r.source_url,
                    "contest_id": r.contest_id,
                    "revision": r.revision,
                    "artifact_id": r.artifact_id,
                    "execution_state": r.execution_state,
                }
                for r in records
            ]
        }

    @app.post("/v1/ingestions/caixa")
    def ingest_caixa(
        body: CaixaIngestionRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ):
        require_write_auth(x_sare_token)

        def execute():
            try:
                r = record_caixa_ingestion(path, fetch_caixa_contest(body.contest_id))
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                raise HTTPException(status_code=502, detail=f"CAIXA_INGESTION_FAILED: {exc}")
            return {
                "ingestion_id": r.ingestion_id,
                "source_class": r.source_class,
                "source_url": r.source_url,
                "contest_id": r.contest_id,
                "revision": r.revision,
                "artifact_id": r.artifact_id,
                "execution_state": r.execution_state,
            }, 201

        return idempotent("INGEST_CAIXA", idempotency_key, body.model_dump(), execute)

    @app.post("/v1/snapshots")
    def publish_snapshot(
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ):
        require_write_auth(x_sare_token)

        def execute():
            try:
                s = create_latest_snapshot(path)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            return {"snapshot_id": s.snapshot_id, "snapshot_hash": s.snapshot_hash, "contest_count": s.contest_count}, 201

        return idempotent("PUBLISH_SNAPSHOT", idempotency_key, {"mode": "LATEST_REVISIONS"}, execute)

    @app.get("/v1/hypotheses")
    def hypotheses():
        return {"items": [_hypothesis_payload(r) for r in list_hypotheses(path)]}

    @app.get("/v1/hypotheses/{hypothesis_id}")
    def hypothesis_by_id(hypothesis_id: str):
        try:
            return _hypothesis_payload(get_hypothesis(path, hypothesis_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="HYPOTHESIS_NOT_FOUND")

    @app.post("/v1/hypotheses")
    def create_hypothesis(
        body: HypothesisRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ):
        require_write_auth(x_sare_token)

        def execute():
            try:
                r = register_hypothesis(path, body.to_protocol())
            except KeyError:
                raise HTTPException(status_code=404, detail="SNAPSHOT_NOT_FOUND")
            except ValueError as exc:
                raise HTTPException(
                    status_code=409 if str(exc) == "HYPOTHESIS_IMMUTABLE_CONFLICT" else 422,
                    detail=str(exc),
                )
            return _hypothesis_payload(r), 201

        return idempotent("REGISTER_HYPOTHESIS", idempotency_key, body.model_dump(), execute)

    @app.post("/v1/experiments")
    def create_experiment(
        body: ExperimentRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ):
        require_write_auth(x_sare_token)

        def execute():
            try:
                r = execute_experiment(path, body.hypothesis_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="HYPOTHESIS_NOT_FOUND")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            return _experiment_payload(r), 201

        return idempotent("EXECUTE_EXPERIMENT", idempotency_key, body.model_dump(), execute)

    @app.get("/v1/experiments/{experiment_id}")
    def experiment_by_id(experiment_id: str):
        try:
            return _experiment_payload(get_experiment(path, experiment_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="EXPERIMENT_NOT_FOUND")

    @app.post("/v1/promotions")
    def create_promotion(
        body: PromotionRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ):
        require_write_auth(x_sare_token)

        def execute():
            try:
                r = promote_model(path, body.experiment_id, body.model_name)
            except KeyError:
                raise HTTPException(status_code=404, detail="EXPERIMENT_NOT_FOUND")
            except PermissionError as exc:
                raise HTTPException(status_code=409, detail=str(exc))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            return {
                "promotion_id": r.promotion_id,
                "experiment_id": r.experiment_id,
                "model_name": r.model_name,
                "predictive_evidence": r.predictive_evidence,
            }, 201

        return idempotent("PROMOTE_MODEL", idempotency_key, body.model_dump(), execute)

    @app.get("/v1/portfolios/{portfolio_id}/export", response_class=PlainTextResponse)
    def export_portfolio(portfolio_id: str):
        try:
            r = get_portfolio(path, portfolio_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="PORTFOLIO_NOT_FOUND")
        lines = [
            f"# {r.evidence_label}",
            f"# portfolio_id={r.portfolio_id}",
            f"# predictive_evidence={r.predictive_evidence}",
            "position,numbers",
        ]
        lines.extend(
            f'{index},"{" ".join(f"{number:02d}" for number in card)}"'
            for index, card in enumerate(r.cards, start=1)
        )
        return "\n".join(lines) + "\n"

    return app
