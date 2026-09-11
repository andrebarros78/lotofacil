from datetime import date, datetime, timedelta, timezone

from sare_lotofacil.analysis.core_report import analyze_core
from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.backup import backup_database, restore_database
from sare_lotofacil.persistence.repository import create_latest_snapshot, load_snapshot_draws, persist_caixa_contest
from sare_lotofacil.simulation.null import simulate_uniform_draws


def test_core_end_to_end_persists_analyzes_and_recovers(tmp_path) -> None:
    db = tmp_path / "sare.db"
    draws = simulate_uniform_draws(120, seed=20260911).draws
    start = date(2026, 1, 1)

    for index, numbers in enumerate(draws, start=1):
        draw_date = start + timedelta(days=index - 1)
        record = validate_contest(index, draw_date, numbers)
        contest = CaixaContest(
            record=record,
            prize_tiers=(),
            source_url=f"fixture://contest/{index}",
            captured_at=datetime(2026, 9, 11, tzinfo=timezone.utc),
            raw_payload={
                "tipoJogo": "LOTOFACIL",
                "numero": index,
                "dataApuracao": draw_date.strftime("%d/%m/%Y"),
                "listaDezenas": [f"{number:02d}" for number in numbers],
                "listaRateioPremio": [],
            },
        )
        persisted = persist_caixa_contest(db, contest, source_class="SINTETICO")
        assert persisted.created is True
        assert persisted.revision == 1

    snapshot = create_latest_snapshot(db)
    loaded = load_snapshot_draws(db, snapshot.snapshot_id)
    assert loaded == draws

    report = analyze_core(loaded, min_train=100)
    assert report.contest_count == 120
    assert report.m1_frequency.predictions == 20
    assert report.m2_exponential.predictions == 20
    assert report.predictive_evidence == "NOT_ESTABLISHED"

    backup = tmp_path / "backups" / "sare.db"
    restored = tmp_path / "restored" / "sare.db"
    backup_info = backup_database(db, backup)
    restore_info = restore_database(backup, restored)
    assert backup_info.integrity == restore_info.integrity == "ok"
    assert load_snapshot_draws(restored, snapshot.snapshot_id) == draws
