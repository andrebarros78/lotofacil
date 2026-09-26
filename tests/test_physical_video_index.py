from __future__ import annotations

import datetime as dt

from sare_lotofacil.physical.video_index import (
    CanonicalContest,
    VideoMetadata,
    build_video_index,
    parse_lotofacil_contest_ids,
    parse_title_date,
)


def _contest(contest_id: int, date_text: str) -> CanonicalContest:
    return CanonicalContest(
        contest_id=contest_id,
        draw_date=dt.date.fromisoformat(date_text),
        numbers=tuple(range(1, 16)),
    )


def _video(
    video_id: str,
    title: str,
    description: str = "",
    *,
    channel: str = "CAIXA",
) -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        title=title,
        description=description,
        webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        channel=channel,
        channel_id="channel-test",
        uploader=channel,
        duration=3600.0,
    )


def test_parse_official_title_date() -> None:
    assert parse_title_date("Loterias CAIXA | 26/06/2026") == dt.date(2026, 6, 26)
    assert parse_title_date("sem data") is None


def test_parse_lotofacil_contest_ids_accepts_real_description_shape() -> None:
    text = "Transmissão dos Sorteios Loterias CAIXA:\nLotofácil - concurso nº 3720;\nQuina - concurso nº 7000."
    assert parse_lotofacil_contest_ids(text) == (3720,)


def test_parse_lotofacil_contest_ids_does_not_treat_title_date_as_contest() -> None:
    assert parse_lotofacil_contest_ids("Loterias Caixa: Quina e Lotofácil 20/07/2020") == ()


def test_explicit_contest_and_date_produces_very_high_confidence_mapping() -> None:
    history = (_contest(3720, "2026-06-26"),)
    videos = (
        _video(
            "zucg_9k3Fy0",
            "Loterias CAIXA | 26/06/2026",
            "Lotofácil - concurso nº 3720; Lotomania - concurso nº 2942;",
        ),
    )

    index = build_video_index(history, videos, first_eligible_contest=3720)

    assert index.mapped_contests == 1
    assert index.accessible_contests == 1
    assert index.coverage_ratio == 1.0
    assert index.accessible_ratio == 1.0
    record = index.records[0]
    assert record.video_id == "zucg_9k3Fy0"
    assert record.candidate_video_ids == ("zucg_9k3Fy0",)
    assert record.confidence == "VERY_HIGH"
    assert "CANONICAL_CONTEST_ID_MATCH" in record.evidence_basis
    assert "CANONICAL_DATE_MATCH" in record.evidence_basis
    assert "OFFICIAL_CAIXA_CHANNEL" in record.evidence_basis


def test_missing_description_can_map_by_unique_official_title_date() -> None:
    history = (_contest(3780, "2026-09-15"),)
    videos = (_video("dOOqM_C9YMI", "Loterias CAIXA | 15/09/2026"),)

    index = build_video_index(history, videos, first_eligible_contest=3780)

    assert index.mapped_contests == 1
    assert index.unique_title_date_matches == 1
    record = index.records[0]
    assert record.mapping_status == "MAPPED"
    assert record.confidence == "MEDIUM_HIGH"
    assert record.explicit_contest_ids == ()


def test_verified_redetv_title_lotofacil_plus_exact_date_is_high_confidence() -> None:
    history = (_contest(1995, "2020-07-20"),)
    videos = (
        _video(
            "EP3b250owhA",
            "Loterias Caixa: Quina e Lotofácil 20/07/2020",
            channel="RedeTV",
        ),
    )

    index = build_video_index(history, videos, first_eligible_contest=1995)

    assert index.mapped_contests == 1
    assert index.trusted_broadcaster_verified_videos == 1
    record = index.records[0]
    assert record.video_id == "EP3b250owhA"
    assert record.confidence == "HIGH"
    assert "TRUSTED_HISTORICAL_REDETV_BROADCAST" in record.evidence_basis
    assert "HISTORICAL_BROADCAST_LOTOFACIL_TITLE_DATE_MATCH" in record.evidence_basis


def test_untrusted_channel_cannot_enter_from_title_and_date_alone() -> None:
    history = (_contest(1995, "2020-07-20"),)
    videos = (
        _video(
            "copy",
            "Loterias Caixa: Quina e Lotofácil 20/07/2020",
            channel="Random Channel",
        ),
    )

    index = build_video_index(history, videos, first_eligible_contest=1995)

    assert index.mapped_contests == 0
    assert index.accessible_contests == 0
    assert index.records[0].mapping_status == "MISSING"


def test_historical_broadcaster_wrong_date_fails_closed() -> None:
    history = (_contest(1995, "2020-07-20"),)
    videos = (
        _video(
            "wrong",
            "Loterias Caixa: Quina e Lotofácil 21/07/2020",
            "Lotofácil concurso nº 1995",
            channel="RedeTV",
        ),
    )

    index = build_video_index(history, videos, first_eligible_contest=1995)

    assert index.mapped_contests == 0
    assert index.conflicting_contests == 1
    assert index.records[0].mapping_status == "CONFLICT"


def test_explicit_contest_date_conflict_fails_closed() -> None:
    history = (_contest(3720, "2026-06-26"),)
    videos = (
        _video(
            "wrong-date",
            "Loterias CAIXA | 27/06/2026",
            "Lotofácil - concurso nº 3720;",
        ),
    )

    index = build_video_index(history, videos, first_eligible_contest=3720)

    assert index.mapped_contests == 0
    assert index.ambiguous_contests == 0
    assert index.conflicting_contests == 1
    assert index.accessible_contests == 0
    assert index.records[0].mapping_status == "CONFLICT"


def test_equal_rank_duplicate_videos_are_retained_for_phase_two() -> None:
    history = (_contest(3720, "2026-06-26"),)
    videos = (
        _video("a", "Loterias CAIXA | 26/06/2026", "Lotofácil - concurso nº 3720;"),
        _video("b", "Loterias CAIXA | 26/06/2026", "Lotofácil - concurso nº 3720;"),
    )

    index = build_video_index(history, videos, first_eligible_contest=3720)

    assert index.mapped_contests == 0
    assert index.ambiguous_contests == 1
    assert index.conflicting_contests == 0
    assert index.accessible_contests == 1
    assert index.accessible_ratio == 1.0
    record = index.records[0]
    assert record.mapping_status == "AMBIGUOUS"
    assert record.confidence == "CANDIDATE_SET_ONLY"
    assert record.candidate_video_ids == ("a", "b")
    assert len(record.candidate_video_urls) == 2
    assert "PHASE2_CONTENT_DISAMBIGUATION_REQUIRED" in record.evidence_basis


def test_missing_video_is_explicitly_preserved() -> None:
    history = (_contest(3720, "2026-06-26"), _contest(3721, "2026-06-27"))
    videos = (
        _video(
            "one",
            "Loterias CAIXA | 26/06/2026",
            "Lotofácil - concurso nº 3720;",
        ),
    )

    index = build_video_index(history, videos, first_eligible_contest=3720)

    assert index.mapped_contests == 1
    assert index.missing_contests == 1
    assert index.accessible_contests == 1
    assert index.accessible_ratio == 0.5
    assert [record.mapping_status for record in index.records] == ["MAPPED", "MISSING"]
