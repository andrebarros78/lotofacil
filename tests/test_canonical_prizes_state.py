import json
from datetime import date, datetime, timezone

from sare_lotofacil.ingestion.caixa import CaixaContest, PrizeTier
from sare_lotofacil.ingestion.validation import validate_contest
from scripts import update_canonical_prizes as updater
from scripts.verify_canonical_prizes import verify


def _contest(prize_15: int = 1_000_000) -> CaixaContest:
    record = validate_contest(10, date(2026, 9, 14), range(1, 16))
    tiers = (
        PrizeTier(15, 1, prize_15),
        PrizeTier(14, 10, 100_000),
        PrizeTier(13, 100, 10_000),
        PrizeTier(12, 1000, 2_000),
        PrizeTier(11, 10000, 1_000),
    )
    return CaixaContest(
        record=record,
        prize_tiers=tiers,
        source_url="https://servicebus2.caixa.gov.br/portaldeloterias/api/lotofacil/10",
        captured_at=datetime(2026, 9, 14, 18, tzinfo=timezone.utc),
        raw_payload={"numero": 10, "prize_15": prize_15},
    )


def _state_dir(tmp_path):
    state = tmp_path / "operations"
    state.mkdir()
    records = [
        {"contest_id": index, "draw_date": "2026-09-14", "numbers": list(range(1, 16))}
        for index in range(1, 11)
    ]
    (state / "canonical_history.json").write_text(
        json.dumps({"schema_version": 1, "records": records}), encoding="utf-8"
    )
    (state / "latest.json").write_text(
        json.dumps({"official_latest_contest": 10}), encoding="utf-8"
    )
    return state


def test_canonical_prizes_initial_capture_is_idempotent_and_auditable(tmp_path):
    state = _state_dir(tmp_path)
    contest = _contest()

    first = updater.update_state(state, fetcher=lambda contest_id: contest)
    second = updater.update_state(state, fetcher=lambda contest_id: contest)

    payload = json.loads((state / "canonical_prizes.json").read_text(encoding="utf-8"))
    assert first["changed_contests"] == [10]
    assert second["changed_contests"] == []
    assert payload["contest_count"] == 1
    assert len(payload["contests"][0]["revisions"]) == 1
    assert verify(state)["status"] == "CANONICAL_PRIZE_AUDIT_PASS"


def test_canonical_prizes_preserves_official_revision(tmp_path):
    state = _state_dir(tmp_path)
    updater.update_state(state, fetcher=lambda contest_id: _contest(1_000_000))
    updater.update_state(state, fetcher=lambda contest_id: _contest(2_000_000))

    payload = json.loads((state / "canonical_prizes.json").read_text(encoding="utf-8"))
    revisions = payload["contests"][0]["revisions"]
    assert [item["revision"] for item in revisions] == [1, 2]
    assert revisions[0]["prize_tiers"][0]["prize_cents"] == 1_000_000
    assert revisions[1]["prize_tiers"][0]["prize_cents"] == 2_000_000
    assert verify(state)["prize_revisions"] == 2
