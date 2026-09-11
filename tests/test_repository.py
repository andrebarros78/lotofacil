from copy import deepcopy
from datetime import datetime, timezone

from sare_lotofacil.ingestion.caixa import parse_caixa_payload
from sare_lotofacil.persistence.repository import create_latest_snapshot, load_snapshot_draws, persist_caixa_contest

BASE = {
    "tipoJogo": "LOTOFACIL",
    "numero": 100,
    "dataApuracao": "01/01/2026",
    "listaDezenas": [f"{n:02d}" for n in range(1, 16)],
    "listaRateioPremio": [{"descricaoFaixa": "15 acertos", "numeroDeGanhadores": 1, "valorPremio": 1000.0}],
}


def contest(payload):
    return parse_caixa_payload(payload, captured_at=datetime(2026, 1, 2, tzinfo=timezone.utc))


def test_persistence_is_idempotent_and_divergence_creates_revision(tmp_path) -> None:
    path = tmp_path / "sare.db"
    first = persist_caixa_contest(path, contest(BASE))
    again = persist_caixa_contest(path, contest(BASE))
    assert first.revision == again.revision == 1
    assert first.created is True
    assert again.created is False

    changed = deepcopy(BASE)
    changed["listaDezenas"] = [f"{n:02d}" for n in range(11, 26)]
    second = persist_caixa_contest(path, contest(changed))
    assert second.revision == 2
    assert second.created is True


def test_snapshot_is_deterministic_and_loadable(tmp_path) -> None:
    path = tmp_path / "sare.db"
    persist_caixa_contest(path, contest(BASE))
    first = create_latest_snapshot(path)
    second = create_latest_snapshot(path)
    assert first == second
    draws = load_snapshot_draws(path, first.snapshot_id)
    assert draws == (tuple(range(1, 16)),)


def test_prize_change_creates_new_revision_and_preserves_previous(tmp_path) -> None:
    path = tmp_path / "sare.db"
    first = persist_caixa_contest(path, contest(BASE))

    changed = deepcopy(BASE)
    changed["listaRateioPremio"][0]["valorPremio"] = 2000.0
    second = persist_caixa_contest(path, contest(changed))

    assert first.revision == 1
    assert second.revision == 2
    assert second.created is True

    import sqlite3

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT revision, prize_cents FROM prize_tiers WHERE contest_id=100 ORDER BY revision"
        ).fetchall()
        assert rows == [(1, 100000), (2, 200000)]
    finally:
        connection.close()
