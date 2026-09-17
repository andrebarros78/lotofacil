from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from sare_lotofacil.ingestion.caixa import CaixaContest
from sare_lotofacil.ingestion.validation import validate_contest
from sare_lotofacil.persistence.db import connect
from sare_lotofacil.persistence.operations import persist_uniform_portfolio
from sare_lotofacil.persistence.post_contest import (
    audit_post_contest,
    list_frozen_cards_for_target,
    list_post_contest_episodes,
)
from sare_lotofacil.persistence.repository import persist_caixa_contest
from sare_lotofacil.rag.learning import build_learning_rag


RESULT_3781 = (3, 5, 6, 7, 8, 9, 11, 12, 13, 16, 19, 21, 22, 24, 25)


def _persist_result_3781(db) -> None:
    contest = CaixaContest(
        record=validate_contest(3781, date(2026, 9, 16), RESULT_3781),
        prize_tiers=(),
        source_url="fixture://caixa/lotofacil/3781",
        captured_at=datetime(2026, 9, 17, 8, 36, tzinfo=timezone.utc),
        raw_payload={"numero": 3781, "listaDezenas": list(RESULT_3781)},
    )
    persisted = persist_caixa_contest(db, contest, source_class="OFICIAL_DIRETA")
    assert persisted.revision == 1


def test_3781_two_frozen_cards_are_recovered_audited_and_never_rewritten(tmp_path) -> None:
    db = tmp_path / "sare.db"
    persist_uniform_portfolio(db, card_count=2, seed=3781, target_contest=3781)
    _persist_result_3781(db)

    before = list_frozen_cards_for_target(db, 3781)
    assert len(before) == 2
    assert len({item.freeze_sha256 for item in before}) == 2

    episode = audit_post_contest(db, 3781, 1, expected_card_count=2)
    after = list_frozen_cards_for_target(db, 3781)

    assert before == after
    assert episode.contest_id == 3781
    assert episode.revision == 1
    assert episode.result == RESULT_3781
    assert len(episode.cards) == 2
    assert episode.max_hits == max(item.hits for item in episode.cards)
    for frozen, audited in zip(before, episode.cards, strict=True):
        assert audited.freeze_sha256 == frozen.freeze_sha256
        assert audited.card == frozen.card
        assert audited.hits == len(set(frozen.card) & set(RESULT_3781))
        assert set(audited.matched_numbers) == set(frozen.card) & set(RESULT_3781)
        assert set(audited.selected_misses) == set(frozen.card) - set(RESULT_3781)
        assert set(audited.omitted_winners) == set(RESULT_3781) - set(frozen.card)

    repeated = audit_post_contest(db, 3781, 1, expected_card_count=2)
    assert repeated.episode_id == episode.episode_id
    assert list_frozen_cards_for_target(db, 3781) == before

    with connect(db) as connection:
        revision_evaluations = connection.execute(
            "SELECT COUNT(*) FROM revision_evaluations WHERE contest_id=3781 AND revision=1"
        ).fetchone()[0]
        episodes = connection.execute(
            "SELECT COUNT(*) FROM audit_events WHERE action='POST_CONTEST_EPISODE_RECORDED'"
        ).fetchone()[0]
    assert revision_evaluations == 1
    assert episodes == 1
    assert len(list_post_contest_episodes(db)) == 1


def test_post_contest_pipeline_refuses_missing_second_freeze(tmp_path) -> None:
    db = tmp_path / "sare.db"
    persist_uniform_portfolio(db, card_count=1, seed=3781, target_contest=3781)
    _persist_result_3781(db)

    with pytest.raises(RuntimeError, match="FROZEN_CARD_COUNT_MISMATCH expected=2 observed=1"):
        audit_post_contest(db, 3781, 1, expected_card_count=2)


def test_audited_episode_is_retrievable_by_learning_rag(tmp_path) -> None:
    db = tmp_path / "sare.db"
    persist_uniform_portfolio(db, card_count=2, seed=3781, target_contest=3781)
    _persist_result_3781(db)
    episode = audit_post_contest(db, 3781, 1, expected_card_count=2)

    repository_root = tmp_path / "repo"
    repository_root.mkdir()
    (repository_root / "README.md").write_text("SARE Lotofacil\n", encoding="utf-8")

    rag = build_learning_rag(repository_root, db)
    hits = rag.search("concurso 3781 cartoes congelados acertos", top_k=5)

    assert hits
    learning_hits = [hit for hit in hits if hit.path.startswith("learning/post_contest/3781/")]
    assert learning_hits
    assert episode.episode_id in learning_hits[0].content
    assert "challenger" in learning_hits[0].content
