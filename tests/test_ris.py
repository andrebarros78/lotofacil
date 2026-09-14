from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sare_lotofacil.analysis.ris import build_categorical_ris
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import initialize_database
from sare_lotofacil.persistence.repository import create_latest_snapshot, persist_caixa_contest
from sare_lotofacil.simulation.null import simulate_uniform_draws
from sare_lotofacil.statistics.inference import temporal_lag_permutation_tests


def _database_with_snapshot(tmp_path, contest_count: int = 105):
    db = tmp_path / "ris.db"
    draws = simulate_uniform_draws(contest_count, seed=20260911).draws
    start = date(2026, 1, 1)
    for index, numbers in enumerate(draws, start=1):
        record = validate_contest(index, start + timedelta(days=index - 1), numbers)
        persist_caixa_contest(
            db,
            CaixaContest(
                record=record,
                prize_tiers=(),
                source_url=f"fixture://ris/{index}",
                captured_at=datetime(2026, 9, 14, tzinfo=timezone.utc),
                raw_payload={"numero": index, "listaDezenas": list(numbers)},
            ),
            source_class="SINTETICO",
        )
    snapshot = create_latest_snapshot(db)
    return db, snapshot, draws


def test_ris_without_snapshot_is_limited_and_never_numeric(tmp_path) -> None:
    db = initialize_database(tmp_path / "empty.db")
    ris = build_categorical_ris(db, temporal_replications=49)

    assert ris["numeric_ris_enabled"] is False
    assert ris["score"] is None
    assert ris["snapshot_id"] is None
    assert ris["dimensions"]["data_integrity"]["state"] == "LIMITED"
    assert ris["dimensions"]["uniformity"]["state"] == "INCONCLUSIVE"
    assert ris["dimensions"]["cooccurrence"]["state"] == "INCONCLUSIVE"
    assert ris["dimensions"]["temporal"]["state"] == "INCONCLUSIVE"
    assert ris["dimensions"]["regime"]["state"] == "INCONCLUSIVE"
    assert ris["dimensions"]["predictive_evidence"]["state"] == "NOT_ESTABLISHED"


def test_ris_exposes_six_canonical_dimensions_with_evidence(tmp_path) -> None:
    db, snapshot, _ = _database_with_snapshot(tmp_path)
    ris = build_categorical_ris(db, temporal_replications=99, temporal_seed=77)

    assert ris["schema_version"] == "ris-categorical-v1"
    assert ris["numeric_ris_enabled"] is False
    assert ris["score"] is None
    assert ris["snapshot_id"] == snapshot.snapshot_id
    assert ris["contest_count"] == 105
    assert set(ris["dimensions"]) == {
        "data_integrity",
        "uniformity",
        "cooccurrence",
        "temporal",
        "regime",
        "predictive_evidence",
    }

    assert ris["dimensions"]["data_integrity"]["state"] == "VERIFIED"
    assert ris["dimensions"]["uniformity"]["state"] in {"COMPATIBLE", "ALERT"}
    assert ris["dimensions"]["uniformity"]["evidence"]["family_size"] == 25
    assert ris["dimensions"]["uniformity"]["evidence"]["correction"] == "holm"

    assert ris["dimensions"]["cooccurrence"]["state"] in {"COMPATIBLE", "ALERT"}
    assert ris["dimensions"]["cooccurrence"]["evidence"]["family_size"] == 300
    assert ris["dimensions"]["cooccurrence"]["evidence"]["expected_pair_probability"] == 0.35

    temporal = ris["dimensions"]["temporal"]
    assert temporal["state"] in {"COMPATIBLE", "ALERT"}
    assert temporal["evidence"]["method"] == "complete_draw_row_permutation"
    assert temporal["evidence"]["lags"] == [1, 2, 3, 5, 10]
    assert temporal["evidence"]["replications"] == 99
    assert len(temporal["evidence"]["statistics"]) == 5

    regime = ris["dimensions"]["regime"]
    assert regime["state"] == "INCONCLUSIVE"
    assert regime["evidence"]["false_alarm_calibration"] == "NOT_ESTABLISHED"

    predictive = ris["dimensions"]["predictive_evidence"]
    assert predictive["state"] == "NOT_ESTABLISHED"
    assert predictive["evidence"]["replicated_promotions"] == 0
    assert "RIS_NUMERIC_FORBIDDEN_IN_1_X" in ris["guardrails"]


def test_temporal_lag_permutation_is_deterministic() -> None:
    draws = simulate_uniform_draws(40, seed=19).draws
    first = temporal_lag_permutation_tests(draws, lags=(1, 2, 5), replications=49, seed=123)
    second = temporal_lag_permutation_tests(draws, lags=(1, 2, 5), replications=49, seed=123)

    assert first == second
    assert [item.lag for item in first] == [1, 2, 5]
    assert all(0.0 < item.p_value <= 1.0 for item in first)
    assert all(0.0 < item.p_holm <= 1.0 for item in first)
    assert all(item.replications == 49 and item.seed == 123 for item in first)
