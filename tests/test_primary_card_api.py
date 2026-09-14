from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from sare_lotofacil.api.app import create_app
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.repository import create_latest_snapshot, persist_caixa_contest


def test_api_accepts_single_optional_portfolio_card(tmp_path) -> None:
    db = tmp_path / "sare.db"
    contest = CaixaContest(
        record=validate_contest(1, date(2026, 9, 14), range(1, 16)),
        prize_tiers=(),
        source_url="fixture://contest/1",
        captured_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
        raw_payload={"numero": 1, "listaDezenas": list(range(1, 16))},
    )
    persist_caixa_contest(db, contest, source_class="SINTETICO")
    snapshot = create_latest_snapshot(db)
    client = TestClient(create_app(db, write_token="secret"))
    response = client.post(
        "/v1/portfolios",
        json={"card_count": 1, "seed": 3780, "snapshot_id": snapshot.snapshot_id, "target_contest": 2},
        headers={"Idempotency-Key": "single-card-1", "X-SARE-Token": "secret"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["card_count"] == 1
    assert len(payload["cards"]) == 1
    assert payload["cost_cents"] == 350
