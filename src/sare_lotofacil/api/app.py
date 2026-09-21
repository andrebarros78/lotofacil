from __future__ import annotations

import hmac
import json
from pathlib import Path
from typing import Annotated, Any, Callable, Literal

from fastapi import Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from sare_lotofacil import __version__
from sare_lotofacil.api.idempotency import execute_idempotent
from sare_lotofacil.api.legacy_app import create_app as _legacy_create_app
from sare_lotofacil.experiments.protocol import ExperimentProtocol
from sare_lotofacil.ingestion.caixa import fetch_caixa_contest
from sare_lotofacil.persistence.evidence import verify_source_artifacts
from sare_lotofacil.persistence.jobs import enqueue_job, get_job, request_cancel
from sare_lotofacil.persistence.operations import get_portfolio, get_run
from sare_lotofacil.persistence.repository import create_latest_snapshot
from sare_lotofacil.portfolios.authority import OPERATIONAL_STATUSES
from sare_lotofacil.resource_limits import MAX_REQUEST_BODY_BYTES, ResourceLimitError
from sare_lotofacil.persistence.workflows import (
    execute_experiment, get_experiment, get_hypothesis, get_ingestion, get_latest_contest,
    list_contests, list_hypotheses, list_ingestions, promote_model, record_caixa_ingestion,
    register_hypothesis,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaixaIngestionRequest(StrictModel):
    contest_id: int | None = Field(default=None, ge=1)


class IngestionRequest(StrictModel):
    source: Literal["CAIXA"] = "CAIXA"
    contest_id: int | None = Field(default=None, ge=1)


class HypothesisRequest(StrictModel):
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


class ExperimentRequest(StrictModel):
    hypothesis_id: str = Field(min_length=1, max_length=128)


class PromotionRequest(StrictModel):
    experiment_id: str = Field(min_length=1, max_length=128)
    model_name: str = Field(min_length=1, max_length=256)


class ModelPromotionRequest(StrictModel):
    experiment_id: str = Field(min_length=1, max_length=128)


class JobRequest(StrictModel):
    job_type: Literal["ANALYSIS", "PORTFOLIO", "EXPERIMENT"]
    payload: dict[str, Any]


def _hypothesis_payload(record) -> dict[str, Any]:
    return {"hypothesis_id": record.hypothesis_id, "protocol_hash": record.protocol_hash, "status": record.status, "protocol": record.protocol}


def _experiment_payload(record) -> dict[str, Any]:
    return {
        "experiment_id": record.experiment_id, "hypothesis_id": record.hypothesis_id,
        "run_id": record.run_id, "protocol_hash": record.protocol_hash,
        "conclusion": record.conclusion, "predictive_evidence": record.predictive_evidence,
    }


def _ingestion_payload(record) -> dict[str, Any]:
    return {
        "ingestion_id": record.ingestion_id, "source_class": record.source_class,
        "source_url": record.source_url, "contest_id": record.contest_id,
        "revision": record.revision, "artifact_id": record.artifact_id,
        "execution_state": record.execution_state,
    }


def create_app(
    db_path: str | Path,
    *,
    write_token: str | None = None,
    max_body_bytes: int = MAX_REQUEST_BODY_BYTES,
):
    path = Path(db_path)
    app = _legacy_create_app(path, write_token=write_token, max_body_bytes=max_body_bytes)
    app.version = __version__

    def auth(token: str | None) -> None:
        if not write_token:
            raise HTTPException(503, "WRITE_DISABLED")
        if token is None:
            raise HTTPException(401, "AUTH_REQUIRED")
        if not hmac.compare_digest(token, write_token):
            raise HTTPException(403, "AUTH_INVALID")

    def idem(
        operation: str,
        key: str | None,
        request_payload: dict[str, Any],
        callback: Callable[[], tuple[dict[str, Any], int]],
    ) -> JSONResponse:
        return execute_idempotent(path, operation, key, request_payload, callback)

    @app.get("/v1/contests")
    def contests(limit: int = 100, offset: int = 0):
        try:
            return {"items": list(list_contests(path, limit=limit, offset=offset))}
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/v1/contests/{contest_id}")
    def contest_by_id(contest_id: int):
        try:
            return get_latest_contest(path, contest_id)
        except KeyError:
            raise HTTPException(404, "CONTEST_NOT_FOUND")

    @app.get("/v1/ingestions")
    def ingestions(limit: int = 100):
        try:
            return {"items": [_ingestion_payload(r) for r in list_ingestions(path, limit=limit)]}
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    def _caixa(contest_id: int | None):
        try:
            return record_caixa_ingestion(path, fetch_caixa_contest(contest_id))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(502, f"CAIXA_INGESTION_FAILED: {exc}")

    @app.post("/v1/ingestions/caixa")
    def ingest_caixa(body: CaixaIngestionRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        return idem("INGEST_CAIXA", idempotency_key, body.model_dump(), lambda: (_ingestion_payload(_caixa(body.contest_id)), 201))

    @app.post("/v1/ingestions")
    def ingest_configured(body: IngestionRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        return idem("INGEST_CONFIGURED_SOURCE", idempotency_key, body.model_dump(), lambda: (_ingestion_payload(_caixa(body.contest_id)), 201))

    @app.get("/v1/ingestions/{ingestion_id}")
    def ingestion_by_id(ingestion_id: str):
        try:
            return _ingestion_payload(get_ingestion(path, ingestion_id))
        except KeyError:
            raise HTTPException(404, "INGESTION_NOT_FOUND")

    @app.post("/v1/snapshots")
    def publish_snapshot(idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        def execute():
            try:
                s = create_latest_snapshot(path)
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            return {"snapshot_id": s.snapshot_id, "snapshot_hash": s.snapshot_hash, "contest_count": s.contest_count}, 201
        return idem("PUBLISH_SNAPSHOT", idempotency_key, {"mode": "LATEST_REVISIONS"}, execute)

    @app.get("/v1/hypotheses")
    def hypotheses():
        return {"items": [_hypothesis_payload(r) for r in list_hypotheses(path)]}

    @app.get("/v1/hypotheses/{hypothesis_id}")
    def hypothesis_by_id(hypothesis_id: str):
        try:
            return _hypothesis_payload(get_hypothesis(path, hypothesis_id))
        except KeyError:
            raise HTTPException(404, "HYPOTHESIS_NOT_FOUND")

    @app.post("/v1/hypotheses")
    def create_hypothesis(body: HypothesisRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        def execute():
            try:
                return _hypothesis_payload(register_hypothesis(path, body.to_protocol())), 201
            except KeyError:
                raise HTTPException(404, "SNAPSHOT_NOT_FOUND")
            except ValueError as exc:
                raise HTTPException(409 if str(exc) == "HYPOTHESIS_IMMUTABLE_CONFLICT" else 422, str(exc))
        return idem("REGISTER_HYPOTHESIS", idempotency_key, body.model_dump(), execute)

    @app.post("/v1/experiments")
    def create_experiment(body: ExperimentRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        def execute():
            try:
                return _experiment_payload(execute_experiment(path, body.hypothesis_id)), 201
            except KeyError:
                raise HTTPException(404, "HYPOTHESIS_NOT_FOUND")
            except ValueError as exc:
                raise HTTPException(422, str(exc))
        return idem("EXECUTE_EXPERIMENT", idempotency_key, body.model_dump(), execute)

    @app.get("/v1/experiments/{experiment_id}")
    def experiment_by_id(experiment_id: str):
        try:
            return _experiment_payload(get_experiment(path, experiment_id))
        except KeyError:
            raise HTTPException(404, "EXPERIMENT_NOT_FOUND")

    def _promote(experiment_id: str, model_name: str):
        try:
            r = promote_model(path, experiment_id, model_name)
        except KeyError:
            raise HTTPException(404, "EXPERIMENT_NOT_FOUND")
        except PermissionError as exc:
            raise HTTPException(409, str(exc))
        return {"promotion_id": r.promotion_id, "experiment_id": r.experiment_id, "model_name": r.model_name, "predictive_evidence": r.predictive_evidence}

    @app.post("/v1/promotions")
    def create_promotion(body: PromotionRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        return idem("PROMOTE_MODEL", idempotency_key, body.model_dump(), lambda: (_promote(body.experiment_id, body.model_name), 201))

    @app.post("/v1/models/{model_name}/promotions")
    def canonical_promotion(model_name: str, body: ModelPromotionRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        payload = {"model_name": model_name, **body.model_dump()}
        return idem("PROMOTE_MODEL_CANONICAL", idempotency_key, payload, lambda: (_promote(body.experiment_id, model_name), 201))

    @app.post("/v1/jobs")
    def create_job(body: JobRequest, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        def execute():
            try:
                job = enqueue_job(path, body.job_type, body.payload)
            except ResourceLimitError as exc:
                raise HTTPException(429, str(exc))
            except ValueError as exc:
                raise HTTPException(422, str(exc))
            return {"job_id": job.job_id, "state": job.state, "location": f"/v1/jobs/{job.job_id}"}, 202
        return idem("CREATE_JOB", idempotency_key, body.model_dump(), execute)

    @app.get("/v1/jobs/{job_id}")
    def job_by_id(job_id: str):
        try:
            job = get_job(path, job_id)
        except KeyError:
            raise HTTPException(404, "JOB_NOT_FOUND")
        return {"job_id": job.job_id, "job_type": job.job_type, "state": job.state, "attempts": job.attempts, "cancel_requested": job.cancel_requested, "result": job.result, "error": job.error}

    @app.post("/v1/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None, x_sare_token: Annotated[str | None, Header(alias="X-SARE-Token")] = None):
        auth(x_sare_token)
        def execute():
            try:
                job = request_cancel(path, job_id)
            except KeyError:
                raise HTTPException(404, "JOB_NOT_FOUND")
            return {"job_id": job.job_id, "state": job.state, "cancel_requested": job.cancel_requested}, 200
        return idem("CANCEL_JOB", idempotency_key, {"job_id": job_id}, execute)

    @app.get("/v1/exports/{run_id}")
    def export_run(run_id: str):
        try:
            run = get_run(path, run_id)
        except KeyError:
            raise HTTPException(404, "RUN_NOT_FOUND")
        return {"run_id": run.run_id, "execution_state": run.execution_state, "snapshot_id": run.snapshot_id, "predictive_evidence": run.predictive_evidence, "result": run.result}

    @app.get("/v1/portfolios/{portfolio_id}/export", response_class=PlainTextResponse)
    def export_portfolio(portfolio_id: str):
        try:
            r = get_portfolio(path, portfolio_id)
        except KeyError:
            raise HTTPException(404, "PORTFOLIO_NOT_FOUND")
        if r.artifact_status not in OPERATIONAL_STATUSES:
            raise HTTPException(409, "PORTFOLIO_ARTIFACT_NOT_OPERATIONAL")
        lines = [
            f"# {r.evidence_label}",
            f"# portfolio_id={r.portfolio_id}",
            f"# card_artifact_id={r.artifact_id}",
            f"# artifact_status={r.artifact_status}",
            f"# policy_id={r.policy_id}",
            f"# predictive_evidence={r.predictive_evidence}",
            "position,numbers",
        ]
        lines.extend(f'{i},"{" ".join(f"{n:02d}" for n in card)}"' for i, card in enumerate(r.cards, 1))
        return "\n".join(lines) + "\n"

    @app.get("/v1/evidence/integrity")
    def evidence_integrity():
        checks = verify_source_artifacts(path)
        return {"valid": all(c.valid for c in checks), "artifacts": [{"artifact_id": c.artifact_id, "expected_sha256": c.expected_sha256, "actual_sha256": c.actual_sha256, "valid": c.valid, "error": c.error} for c in checks]}

    @app.get("/", response_class=HTMLResponse)
    def ui_overview():
        return HTMLResponse("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>SARE Lotofácil</title></head><body><main><h1>SARE Lotofácil — Operational 1.1</h1><p><strong>Evidência preditiva:</strong> NÃO ESTABELECIDA.</p><p><a href='/docs'>API</a></p></main></body></html>")

    @app.get("/ui/portfolios/{portfolio_id}", response_class=HTMLResponse)
    def ui_portfolio(portfolio_id: str):
        try:
            record = get_portfolio(path, portfolio_id)
        except KeyError:
            raise HTTPException(404, "PORTFOLIO_NOT_FOUND")
        cards = []
        for position, card in enumerate(record.cards, 1):
            first = " ".join(f"{n:02d}" for n in card[:8])
            second = " ".join(f"{n:02d}" for n in card[8:])
            cards.append(f"<section><h2>Cartão {position}</h2><code>{first}<br>{second}</code></section>")
        return HTMLResponse("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Carteira SARE</title></head><body>" + f"<h1>{record.evidence_label}</h1>" + "".join(cards) + "</body></html>")

    return app
