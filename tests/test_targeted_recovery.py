from __future__ import annotations

import datetime as dt

from sare_lotofacil.physical.targeted_recovery import (
    resolve_ambiguities_strict,
    targeted_searches,
)
from sare_lotofacil.physical.video_index import (
    CanonicalContest,
    VideoMetadata,
    build_video_index,
)


def _contest(contest_id: int = 3720, date_text: str = "2026-06-26") -> CanonicalContest:
    return CanonicalContest(contest_id, dt.date.fromisoformat(date_text), tuple(range(1, 16)))


def _video(video_id: str, *, duration: float) -> VideoMetadata:
    return VideoMetadata(
        video_id=video_id,
        title="Loterias CAIXA | 26/06/2026",
        description="Lotofácil - concurso nº 3720;",
        webpage_url=f"https://www.youtube.com/watch?v={video_id}",
        channel="CAIXA",
        uploader="CAIXA",
        duration=duration,
    )


def test_targeted_searches_only_unresolved_records_and_embeds_contest_date() -> None:
    history = (_contest(), _contest(3721, "2026-06-27"))
    videos = (_video("mapped", duration=3600.0),)
    index = build_video_index(history, videos, first_eligible_contest=3720)

    searches = targeted_searches(
        index.records,
        statuses=frozenset({"MISSING"}),
        results_per_contest=3,
    )

    assert len(searches) == 1
    assert "3721" in searches[0]
    assert "27/06/2026" in searches[0]
    assert "ytsearch3:" in searches[0]


def test_strict_resolver_prefers_full_length_canonical_broadcast() -> None:
    history = (_contest(),)
    long_video = _video("long", duration=3600.0)
    short_video = _video("short", duration=90.0)
    index = build_video_index(history, (long_video, short_video), first_eligible_contest=3720)
    assert index.ambiguous_contests == 1

    resolved, diagnostics = resolve_ambiguities_strict(
        index,
        {"long": long_video, "short": short_video},
    )

    assert diagnostics.resolved_ambiguities == 1
    assert resolved.mapped_contests == 1
    assert resolved.ambiguous_contests == 0
    assert resolved.records[0].video_id == "long"
    assert resolved.records[0].confidence == "HIGH_STRICT_METADATA_RESOLUTION"
    assert "PHASE2_STRICT_METADATA_DISAMBIGUATION" in resolved.records[0].evidence_basis


def test_strict_resolver_keeps_true_tie_ambiguous() -> None:
    history = (_contest(),)
    video_a = _video("a", duration=3600.0)
    video_b = _video("b", duration=3600.0)
    index = build_video_index(history, (video_a, video_b), first_eligible_contest=3720)

    resolved, diagnostics = resolve_ambiguities_strict(
        index,
        {"a": video_a, "b": video_b},
    )

    assert diagnostics.resolved_ambiguities == 0
    assert resolved.mapped_contests == 0
    assert resolved.ambiguous_contests == 1
    assert resolved.records[0].mapping_status == "AMBIGUOUS"
