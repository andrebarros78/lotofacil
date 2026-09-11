from __future__ import annotations

import hmac
import json
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Callable

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from sare_lotofacil.persistence.backup import database_integrity
from sare_lotofacil.persistence.db import SCHEMA_VERSION, connect, initialize_database
from sare_lotofacil.persistence.operations import (
    evaluate_portfolio,
    get_idempotency,
    get_portfolio,
    get_run,
    list_audit_events,
    list_snapshots,
    payload_hash,
    persist_analysis,
    persist_uniform_portfolio,
    save_idempotency,
)


class AnalysisRequest(BaseModel):
    snapshot_id: str = Field(min_length=1, max_length=128)
    min_train: int | None = Field(default=None, ge=1)
    delta_min: float = Field(default=0.0, ge=0.0)


class PortfolioRequest(BaseModel):
    card_count: int = Field(ge=3, le=100)
    seed: int
    snapshot_id: str | None = Field(default=None, max_length=128)
    target_contest: int | None = Field(default=None, ge=1)


class EvaluationRequest(BaseModel):
    portfolio_id: str = Field(min_length=1, max_length=128)
    result: list[int] = Field(min_length=15, max_length=15)


def _portfolio_payload(record) -> dict[str, Any]:
    return {
        "portfolio_id": record.portfolio_id,
        "snapshot_id": record.snapshot_id,
        "target_contest": record.target_contest,
        "seed": record.seed,
        "cards": [list(card) for card in record.cards],
        "card_count": len(record.cards),
        "cost_cents": record.cost_cents,
        "predictive_evidence": record.predictive_evidence,
        "evidence_label": record.evidence_label,
    }


def _run_payload(record) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "execution_state": record.execution_state,
        "snapshot_id": record.snapshot_id,
        "predictive_evidence": record.predictive_evidence,
        "result": record.result,
    }


def create_app(
    db_path: str | Path,
    *,
    write_token: str | None = None,
    max_body_bytes: int = 65_536,
) -> FastAPI:
    if max_body_bytes < 1024:
        raise ValueError("max_body_bytes deve ser >= 1024")
    path = Path(db_path)
    initialize_database(path)

    app = FastAPI(
        title="SARE Lotofácil",
        version="0.2.0",
        docs_url="/docs",
        redoc_url=None,
    )

    @app.middleware("http")
    async def body_limit(request: Request, call_next):
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                content_length = int(raw_length)
            except ValueError:
                return JSONResponse({"detail": "Content-Length inválido"}, status_code=400)
            if content_length > max_body_bytes:
                return JSONResponse({"detail": "request body excede o limite"}, status_code=413)
        return await call_next(request)

    def require_write_auth(x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None) -> None:
        if not write_token:
            raise HTTPException(status_code=503, detail="WRITE_DISABLED")
        if x_sare_token is None:
            raise HTTPException(status_code=401, detail="AUTH_REQUIRED")
        if not hmac.compare_digest(x_sare_token, write_token):
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
        response_payload, status_code = callback()
        try:
            save_idempotency(path, operation, key, digest, response_payload, status_code)
        except sqlite3.IntegrityError:
            existing = get_idempotency(path, operation, key)
            if not existing or existing.request_hash != digest:
                raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_CONFLICT")
            return JSONResponse(json.loads(existing.response_json), status_code=existing.status_code)
        return JSONResponse(response_payload, status_code=status_code)

    @app.get("/health/live")
    def health_live() -> dict[str, str]:
        return {"status": "live"}

    @app.get("/health/ready")
    def health_ready() -> dict[str, Any]:
        integrity = database_integrity(path)
        with connect(path) as connection:
            row = connection.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        schema_version = int(row[0]) if row else None
        ready = integrity == "ok" and schema_version == SCHEMA_VERSION
        return {
            "status": "ready" if ready else "degraded",
            "database_integrity": integrity,
            "schema_version": schema_version,
            "write_enabled": bool(write_token),
        }

    @app.get("/v1/snapshots")
    def snapshots() -> dict[str, Any]:
        return {"items": list(list_snapshots(path))}

    @app.get("/v1/runs/{run_id}")
    def run_by_id(run_id: str) -> dict[str, Any]:
        try:
            return _run_payload(get_run(path, run_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="RUN_NOT_FOUND")

    @app.post("/v1/analyses")
    def create_analysis(
        body: AnalysisRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ) -> JSONResponse:
        require_write_auth(x_sare_token)
        payload = body.model_dump()

        def execute() -> tuple[dict[str, Any], int]:
            try:
                run = persist_analysis(
                    path,
                    body.snapshot_id,
                    min_train=body.min_train,
                    delta_min=body.delta_min,
                )
            except KeyError:
                raise HTTPException(status_code=404, detail="SNAPSHOT_NOT_FOUND")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            return _run_payload(run), 201

        return idempotent("CREATE_ANALYSIS", idempotency_key, payload, execute)

    @app.post("/v1/portfolios")
    def create_portfolio(
        body: PortfolioRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ) -> JSONResponse:
        require_write_auth(x_sare_token)
        payload = body.model_dump()

        def execute() -> tuple[dict[str, Any], int]:
            try:
                record = persist_uniform_portfolio(
                    path,
                    card_count=body.card_count,
                    seed=body.seed,
                    snapshot_id=body.snapshot_id,
                    target_contest=body.target_contest,
                )
            except KeyError:
                raise HTTPException(status_code=404, detail="SNAPSHOT_NOT_FOUND")
            return _portfolio_payload(record), 201

        return idempotent("CREATE_PORTFOLIO", idempotency_key, payload, execute)

    @app.get("/v1/portfolios/{portfolio_id}")
    def portfolio_by_id(portfolio_id: str) -> dict[str, Any]:
        try:
            return _portfolio_payload(get_portfolio(path, portfolio_id))
        except KeyError:
            raise HTTPException(status_code=404, detail="PORTFOLIO_NOT_FOUND")

    @app.post("/v1/evaluations")
    def create_evaluation(
        body: EvaluationRequest,
        idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
        x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None,
    ) -> JSONResponse:
        require_write_auth(x_sare_token)
        payload = body.model_dump()

        def execute() -> tuple[dict[str, Any], int]:
            try:
                record = evaluate_portfolio(path, body.portfolio_id, body.result)
            except KeyError:
                raise HTTPException(status_code=404, detail="PORTFOLIO_NOT_FOUND")
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc))
            return {
                "evaluation_id": record.evaluation_id,
                "portfolio_id": record.portfolio_id,
                "result": list(record.result),
                "hits": list(record.hits),
                "max_hits": record.max_hits,
            }, 201

        return idempotent("CREATE_EVALUATION", idempotency_key, payload, execute)

    @app.get("/v1/audit")
    def audit_events(limit: int = 100) -> dict[str, Any]:
        try:
            return {"items": list(list_audit_events(path, limit=limit))}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.get("/v1/ris")
    def ris_panel() -> dict[str, Any]:
        snapshots_count = len(list_snapshots(path))
        return {
            "numeric_ris_enabled": False,
            "score": None,
            "dimensions": {
                "data": "AVAILABLE" if snapshots_count else "NO_SNAPSHOT",
                "mathematics": "REFERENCE_IMPLEMENTED",
                "predictive_evidence": "NOT_ESTABLISHED",
                "portfolio_policy": "COMBINATORIAL_ONLY_UNLESS_REPLICATED",
            },
        }

    return app
