from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient

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
        draw_date = start + timedelta(days=index - 1)
        record = validate_contest(index, draw_date, numbers)
        contest = CaixaContest(
            record=record,
            prize_tiers=(),
            source_url=f"fixture://contest/{index}",
            captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            raw_payload={"numero": index, "listaDezenas": list(numbers)},
        )
        persist_caixa_contest(db, contest, source_class="SINTETICO")
    snapshot = create_latest_snapshot(db)
    return db, snapshot, draws


def test_api_health_and_write_authentication(tmp_path) -> None:
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token="secret"))
    assert client.get("/health/live").json() == {"status": "live"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["write_enabled"] is True

    body = {"card_count": 3, "seed": 7, "snapshot_id": snapshot.snapshot_id, "target_contest": 106}
    assert client.post("/v1/portfolios", json=body, headers={"Idempotency-Key": "p1"}).status_code == 401
    assert client.post(
        "/v1/portfolios",
        json=body,
        headers={"Idempotency-Key": "p1", "X-SARE-Token": "wrong"},
    ).status_code == 403


def test_api_idempotency_conflict_and_restart_persistence(tmp_path) -> None:
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    headers = {"Idempotency-Key": "portfolio-001", "X-SARE-Token": "secret"}
    body = {"card_count": 3, "seed": 17, "snapshot_id": snapshot.snapshot_id, "target_contest": 106}
    client = TestClient(create_app(db, write_token="secret"))

    first = client.post("/v1/portfolios", json=body, headers=headers)
    second = client.post("/v1/portfolios", json=body, headers=headers)
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    portfolio_id = first.json()["portfolio_id"]
    assert "SEM VANTAGEM PREDITIVA COMPROVADA" in first.json()["evidence_label"]
    assert first.json()["artifact_status"] == "FROZEN"
    assert first.json()["operational_use_allowed"] is True
    assert first.json()["artifact_id"].startswith("card-")
    assert first.json()["policy_id"] == "UNIFORM_RANDOM_PORTFOLIO_V1"

    conflict = client.post(
        "/v1/portfolios",
        json={**body, "seed": 18},
        headers=headers,
    )
    assert conflict.status_code == 409

    restarted = TestClient(create_app(db, write_token="secret"))
    loaded = restarted.get(f"/v1/portfolios/{portfolio_id}")
    assert loaded.status_code == 200
    assert loaded.json() == first.json()

    exported = restarted.get(f"/v1/portfolios/{portfolio_id}/export")
    assert exported.status_code == 200
    assert "# artifact_status=FROZEN" in exported.text
    assert f"# card_artifact_id={first.json()['artifact_id']}" in exported.text


def test_api_in_progress_idempotency_reservation_blocks_duplicate_effect(tmp_path) -> None:
    from sare_lotofacil.persistence.operations import payload_hash, reserve_idempotency

    db, snapshot, _ = _database_with_snapshot(tmp_path)
    body = {"card_count": 3, "seed": 71, "snapshot_id": snapshot.snapshot_id, "target_contest": 106}
    reserve_idempotency(
        db,
        "CREATE_PORTFOLIO",
        "concurrent-001",
        payload_hash(body),
        "simulated-first-request",
    )

    client = TestClient(create_app(db, write_token="secret"))
    response = client.post(
        "/v1/portfolios",
        json=body,
        headers={"Idempotency-Key": "concurrent-001", "X-SARE-Token": "secret"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "IDEMPOTENCY_REQUEST_IN_PROGRESS"


def test_api_analysis_exposes_baseline_delta_interval_and_inconclusive_status(tmp_path) -> None:
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token="secret"))
    response = client.post(
        "/v1/analyses",
        json={"snapshot_id": snapshot.snapshot_id, "min_train": 100, "delta_min": 0.0001},
        headers={"Idempotency-Key": "analysis-001", "X-SARE-Token": "secret"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["predictive_evidence"] == "NOT_ESTABLISHED"
    assert payload["result"]["scientific_conclusion"] == "EVIDENCIA_PREDITIVA_INSUFICIENTE"
    for model_key in ("m1_frequency", "m2_exponential"):
        model = payload["result"][model_key]
        assert model["uniform_brier"] == 0.24
        assert model["predictions"] == 5
        assert "delta_brier" in model
        assert "delta_brier_ci_low" in model
        assert "delta_brier_ci_high" in model
        assert model["delta_min"] == 0.0001

    run_id = payload["run_id"]
    assert client.get(f"/v1/runs/{run_id}").json() == payload


def test_api_evaluation_and_ris_are_categorical(tmp_path) -> None:
    db, snapshot, draws = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token="secret"))
    portfolio = client.post(
        "/v1/portfolios",
        json={"card_count": 4, "seed": 9, "snapshot_id": snapshot.snapshot_id, "target_contest": 106},
        headers={"Idempotency-Key": "p-eval", "X-SARE-Token": "secret"},
    ).json()
    evaluation = client.post(
        "/v1/evaluations",
        json={"portfolio_id": portfolio["portfolio_id"], "result": list(draws[-1])},
        headers={"Idempotency-Key": "e-001", "X-SARE-Token": "secret"},
    )
    assert evaluation.status_code == 201
    assert len(evaluation.json()["hits"]) == 4
    assert 5 <= evaluation.json()["max_hits"] <= 15

    audit = client.get("/v1/audit").json()["items"]
    assert any(item["action"] == "PORTFOLIO_EVALUATED" for item in audit)

    ris = client.get("/v1/ris").json()
    assert ris["schema_version"] == "ris-categorical-v1"
    assert ris["numeric_ris_enabled"] is False
    assert ris["score"] is None
    assert set(ris["dimensions"]) == {
        "data_integrity",
        "uniformity",
        "cooccurrence",
        "temporal",
        "regime",
        "predictive_evidence",
    }
    assert ris["dimensions"]["predictive_evidence"]["state"] == "NOT_ESTABLISHED"
    assert ris["dimensions"]["regime"]["state"] == "INCONCLUSIVE"
    assert "RIS_NUMERIC_FORBIDDEN_IN_1_X" in ris["guardrails"]


def test_api_body_limit_and_read_only_mode(tmp_path) -> None:
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    client = TestClient(create_app(db, write_token=None, max_body_bytes=1024))
    response = client.post(
        "/v1/portfolios",
        json={"card_count": 3, "seed": 1, "snapshot_id": snapshot.snapshot_id},
        headers={"Idempotency-Key": "x", "X-SARE-Token": "anything"},
    )
    assert response.status_code == 503

    oversized = "x" * 2000
    response = client.post(
        "/v1/portfolios",
        content=oversized,
        headers={"content-type": "application/json", "content-length": str(len(oversized))},
    )
    assert response.status_code == 413
