from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

import sare_lotofacil.api.app as app_module
from sare_lotofacil.api.app import create_app
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.repository import create_latest_snapshot, persist_caixa_contest
from sare_lotofacil.simulation.null import simulate_uniform_draws


def _database_with_snapshot(tmp_path):
    db = tmp_path / "sare.db"
    draws = simulate_uniform_draws(105, seed=20260911).draws
    start = date(2026, 1, 1)
    for index, numbers in enumerate(draws, start=1):
        record = validate_contest(index, start + timedelta(days=index - 1), numbers)
        contest = CaixaContest(
            record=record,
            prize_tiers=(),
            source_url=f"fixture://contest/{index}",
            captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            raw_payload={"tipoJogo": "LOTOFACIL", "numero": index, "listaDezenas": list(numbers)},
        )
        persist_caixa_contest(db, contest, source_class="SINTETICO")
    snapshot = create_latest_snapshot(db)
    return db, snapshot, draws


def _hypothesis(snapshot_id: str):
    return {
        "hypothesis_id": "H-API-001",
        "question": "M1 ou M2 melhora Brier contra M0?",
        "h0": "Delta Brier <= 0",
        "h1": "Delta Brier > 0",
        "snapshot_id": snapshot_id,
        "variables": "presenca marginal de cada dezena usando apenas passado",
        "model": "M1 frequencia regularizada e M2 media exponencial",
        "comparators": ["uniform_p_0_6", "frequency_regularized", "exponential"],
        "multiplicity_family": "familia primaria registrada com Holm",
        "sample_plan": "walk-forward no snapshot congelado",
        "stopping_rule": "snapshot fixo sem parada oportunista",
        "code_environment": "release commit + Python 3.12/3.13",
        "delta_min": 0.0001,
        "min_train": 100,
    }


def test_hypothesis_requires_scientific_fields_and_is_immutable(tmp_path):
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token="secret"))
    headers = {"X-SARE-Token": "secret", "Idempotency-Key": "h-1"}
    incomplete = _hypothesis(snapshot.snapshot_id)
    incomplete.pop("stopping_rule")
    assert client.post("/v1/hypotheses", json=incomplete, headers=headers).status_code == 422

    body = _hypothesis(snapshot.snapshot_id)
    created = client.post("/v1/hypotheses", json=body, headers=headers)
    assert created.status_code == 201
    payload = created.json()
    assert payload["status"] == "REGISTERED"
    assert len(payload["protocol_hash"]) == 64

    changed = dict(body)
    changed["h1"] = "Delta Brier >= 0.01"
    conflict = client.post(
        "/v1/hypotheses",
        json=changed,
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "h-2"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "HYPOTHESIS_IMMUTABLE_CONFLICT"


def test_experiment_conclusion_persists_and_promotion_is_blocked(tmp_path):
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token="secret"))
    created = client.post(
        "/v1/hypotheses",
        json=_hypothesis(snapshot.snapshot_id),
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "h-1"},
    ).json()

    experiment = client.post(
        "/v1/experiments",
        json={"hypothesis_id": created["hypothesis_id"]},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "e-1"},
    )
    assert experiment.status_code == 201
    payload = experiment.json()
    assert payload["conclusion"] == "EVIDENCIA_PREDITIVA_INSUFICIENTE"
    assert payload["predictive_evidence"] == "NOT_ESTABLISHED"

    run = client.get(f"/v1/runs/{payload['run_id']}").json()
    for model_key in ("m1_frequency", "m2_exponential"):
        assert run["result"][model_key]["uniform_brier"] == 0.24
        assert "delta_brier_ci_low" in run["result"][model_key]
        assert "delta_brier_ci_high" in run["result"][model_key]
        assert run["result"][model_key]["delta_min"] == 0.0001

    promotion = client.post(
        "/v1/promotions",
        json={"experiment_id": payload["experiment_id"], "model_name": "M1"},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "promo-1"},
    )
    assert promotion.status_code == 409
    assert promotion.json()["detail"] == "PREDICTIVE_EVIDENCE_NOT_REPLICATED"

    restarted = TestClient(create_app(db, write_token="secret"))
    assert restarted.get(f"/v1/experiments/{payload['experiment_id']}").json() == payload
    hypothesis = restarted.get(f"/v1/hypotheses/{created['hypothesis_id']}").json()
    assert hypothesis["status"] == "CONCLUDED"
    assert hypothesis["protocol_hash"] == created["protocol_hash"]


def test_portfolio_export_carries_mandatory_evidence_label(tmp_path):
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token="secret"))
    portfolio = client.post(
        "/v1/portfolios",
        json={"card_count": 3, "seed": 17, "snapshot_id": snapshot.snapshot_id, "target_contest": 106},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "p-1"},
    ).json()
    exported = client.get(f"/v1/portfolios/{portfolio['portfolio_id']}/export")
    assert exported.status_code == 200
    assert "CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA" in exported.text
    assert "position,numbers" in exported.text


def test_caixa_ingestion_is_audited_and_queryable(monkeypatch, tmp_path):
    db = tmp_path / "sare.db"
    numbers = tuple(range(1, 16))
    record = validate_contest(999, date(2026, 9, 11), numbers)
    fixture = CaixaContest(
        record=record,
        prize_tiers=(),
        source_url="https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/999",
        captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
        raw_payload={"tipoJogo": "LOTOFACIL", "numero": 999, "dataApuracao": "11/09/2026", "listaDezenas": [f"{n:02d}" for n in numbers]},
    )
    monkeypatch.setattr(app_module, "fetch_caixa_contest", lambda contest_id=None: fixture)
    client = TestClient(create_app(db, write_token="secret"))
    ingested = client.post(
        "/v1/ingestions/caixa",
        json={"contest_id": 999},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "i-1"},
    )
    assert ingested.status_code == 201
    assert ingested.json()["execution_state"] == "COMPLETED"
    contest = client.get("/v1/contests/999")
    assert contest.status_code == 200
    assert contest.json()["numbers"] == list(numbers)
    items = client.get("/v1/ingestions").json()["items"]
    assert items[0]["contest_id"] == 999
    snapshot = client.post(
        "/v1/snapshots",
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "s-1"},
    )
    assert snapshot.status_code == 201
    assert snapshot.json()["contest_count"] == 1
