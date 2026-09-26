from __future__ import annotations

from sare_lotofacil.physical.gap_recovery import (
    apply_gap_decisions,
    decide_remaining_gap,
    remaining_gap_searches,
)
from sare_lotofacil.physical.video_index import VideoMetadata


def _record() -> dict[str, object]:
    return {
        "contest_id": 3615,
        "draw_date": "2026-02-18",
        "mapping_status": "MISSING",
        "confidence": "NONE",
        "candidate_video_ids": [],
        "candidate_video_urls": [],
        "evidence_basis": [],
        "video_id": None,
        "video_url": None,
    }


def _video(video_id: str, *, channel: str = "CAIXA", title: str = "Loterias CAIXA | 18/02/2026") -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        title=title,
        description="Lotofácil - concurso nº 3615;",
        webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        channel=channel,
        uploader=channel,
    )


def test_remaining_gap_searches_emit_four_queries_per_missing_record() -> None:
    searches = remaining_gap_searches((_record(),), results_per_query=5)
    assert len(searches) == 4
    assert all("3615" in query or "18/02/2026" in query for query in searches)


def test_official_exact_date_and_contest_is_recovered() -> None:
    decision = decide_remaining_gap(_record(), (_video("winner"),))
    assert decision.status == "RECOVERED_STRICT"
    assert decision.winner_video_id == "winner"

    index = {
        "schema_version": 4,
        "eligible_contests": 1,
        "mapped_contests": 0,
        "ambiguous_contests": 0,
        "missing_contests": 1,
        "accessible_contests": 0,
        "candidate_available_contests": 0,
        "records": [_record()],
        "predictive_evidence": "NOT_ESTABLISHED",
        "purchase_executed": False,
    }
    output = apply_gap_decisions(index, (decision,))
    assert output["mapped_contests"] == 1
    assert output["missing_contests"] == 0
    assert output["records"][0]["mapping_status"] == "MAPPED"


def test_unknown_channel_is_never_recovered_from_search_relevance() -> None:
    decision = decide_remaining_gap(_record(), (_video("copy", channel="Random Channel"),))
    assert decision.status == "STILL_MISSING"


def test_equal_strong_candidates_remain_ambiguous() -> None:
    decision = decide_remaining_gap(_record(), (_video("a"), _video("b")))
    assert decision.status == "GAP_AMBIGUOUS"
    assert decision.winner_video_id is None
    assert set(decision.candidate_video_ids) == {"a", "b"}
