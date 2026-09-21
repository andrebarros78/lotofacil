from fastapi.testclient import TestClient

from sare_lotofacil.api.app import create_app


def test_generic_ingestion_rejects_arbitrary_url_field(tmp_path):
    client = TestClient(create_app(tmp_path / "sare.db", write_token="secret"))
    response = client.post(
        "/v1/ingestions",
        json={"source": "CAIXA", "contest_id": 1, "url": "http://127.0.0.1:1/internal"},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "ssrf-1"},
    )
    assert response.status_code == 422


def test_persistent_job_api_accepts_202_and_cancel_is_final(tmp_path):
    client = TestClient(create_app(tmp_path / "sare.db", write_token="secret"))
    created = client.post(
        "/v1/jobs",
        json={"job_type": "PORTFOLIO", "payload": {"card_count": 3, "seed": 77}},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "job-1"},
    )
    assert created.status_code == 202
    job_id = created.json()["job_id"]
    assert created.json()["location"] == f"/v1/jobs/{job_id}"
    cancelled = client.post(
        f"/v1/jobs/{job_id}/cancel",
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "cancel-1"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "CANCELLED"
    loaded = client.get(f"/v1/jobs/{job_id}").json()
    assert loaded["state"] == "CANCELLED"
    assert loaded["result"] is None


def test_portfolio_html_uses_two_digit_8_plus_7_layout(tmp_path):
    client = TestClient(create_app(tmp_path / "sare.db", write_token="secret"))
    portfolio = client.post(
        "/v1/portfolios",
        json={"card_count": 3, "seed": 21},
        headers={"X-SARE-Token": "secret", "Idempotency-Key": "portfolio-ui"},
    )
    assert portfolio.status_code == 201
    payload = portfolio.json()
    html = client.get(f"/ui/portfolios/{payload['portfolio_id']}")
    assert html.status_code == 200
    assert "CARTEIRA COMBINATÓRIA — SEM VANTAGEM PREDITIVA COMPROVADA" in html.text
    card = payload["cards"][0]
    first = " ".join(f"{number:02d}" for number in card[:8])
    second = " ".join(f"{number:02d}" for number in card[8:])
    assert f"{first}<br>{second}" in html.text


def test_concurrent_same_idempotency_key_creates_one_logical_job(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    db = tmp_path / "sare.db"
    headers = {"X-SARE-Token": "secret", "Idempotency-Key": "same-logical-job"}
    body = {"job_type": "PORTFOLIO", "payload": {"card_count": 3, "seed": 88}}

    def submit():
        client = TestClient(create_app(db, write_token="secret"))
        response = client.post("/v1/jobs", json=body, headers=headers)
        return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(executor.map(lambda _: submit(), range(2)))

    statuses = {first[0], second[0]}
    assert statuses <= {202, 409}
    assert 202 in statuses
    accepted = first if first[0] == 202 else second
    blocked = second if first[0] == 202 else first
    if blocked[0] == 409:
        assert blocked[1]["detail"] == "IDEMPOTENCY_REQUEST_IN_PROGRESS"
    else:
        assert blocked[1]["job_id"] == accepted[1]["job_id"]

    replay = TestClient(create_app(db, write_token="secret")).post(
        "/v1/jobs", json=body, headers=headers
    )
    assert replay.status_code == 202
    assert replay.json()["job_id"] == accepted[1]["job_id"]

    from sare_lotofacil.persistence.db import connect
    with connect(db) as connection:
        jobs = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        idempotency = connection.execute(
            "SELECT COUNT(*) FROM idempotency_keys WHERE operation='CREATE_JOB' AND idempotency_key='same-logical-job'"
        ).fetchone()[0]
    assert jobs == 1
    assert idempotency == 1
