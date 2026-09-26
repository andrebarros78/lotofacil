from __future__ import annotations

from sare_lotofacil.physical.content_features import ProcedureAssessment
from sare_lotofacil.physical.content_resolution import apply_content_decisions, decide_ambiguous_content


def _assessment(score: int, *, complete: bool = True, contest_mentions: int = 1) -> ProcedureAssessment:
    return ProcedureAssessment(
        status="COMPLETE_PROCEDURE_EVIDENCE" if complete else "PARTIAL_LOTOFACIL_CONTENT",
        complete_procedure=complete,
        score=score,
        lotofacil_mentions=1,
        contest_mentions=contest_mentions,
        procedure_markers=("CASE", "GLOBE", "DRAW", "BALL") if complete else ("DRAW",),
        start_seconds=10.0,
        end_seconds=100.0,
        duration_seconds=90.0,
        event_times={},
        intervention_flags=(),
        draw_sequence=None,
        draw_sequence_status="NOT_EXTRACTED",
        cue_count=10,
    )


def _index() -> dict[str, object]:
    return {
        "schema_version": 4,
        "eligible_contests": 1,
        "mapped_contests": 0,
        "ambiguous_contests": 1,
        "missing_contests": 0,
        "accessible_contests": 1,
        "candidate_available_contests": 1,
        "coverage_ratio": 0.0,
        "accessible_ratio": 1.0,
        "predictive_evidence": "NOT_ESTABLISHED",
        "purchase_executed": False,
        "records": [
            {
                "contest_id": 3790,
                "mapping_status": "AMBIGUOUS",
                "confidence": "CANDIDATE_SET_ONLY",
                "candidate_video_ids": ["a", "b"],
                "candidate_video_urls": ["https://www.youtube.com/watch?v=a", "https://www.youtube.com/watch?v=b"],
                "evidence_basis": ["MULTIPLE_EQUAL_RANK_VIDEOS"],
                "video_id": None,
                "video_url": None,
            }
        ],
    }


def test_unique_complete_content_resolves_ambiguity() -> None:
    decision = decide_ambiguous_content(
        contest_id=3790,
        candidate_video_ids=("a", "b"),
        assessments_by_video={"a": _assessment(95), "b": _assessment(25, complete=False)},
    )
    assert decision.status == "RESOLVED_BY_CONTENT"
    assert decision.winner_video_id == "a"

    output = apply_content_decisions(_index(), (decision,))
    assert output["mapped_contests"] == 1
    assert output["ambiguous_contests"] == 0
    assert output["records"][0]["video_id"] == "a"
    assert output["predictive_evidence"] == "NOT_ESTABLISHED"


def test_two_complete_candidates_with_small_margin_remain_ambiguous() -> None:
    decision = decide_ambiguous_content(
        contest_id=3790,
        candidate_video_ids=("a", "b"),
        assessments_by_video={"a": _assessment(100), "b": _assessment(90)},
        minimum_margin=20,
    )
    assert decision.status == "UNRESOLVED_CONTENT_SCORE_TIE"
    assert decision.winner_video_id is None


def test_no_content_access_fails_closed() -> None:
    decision = decide_ambiguous_content(
        contest_id=3790,
        candidate_video_ids=("a", "b"),
        assessments_by_video={},
    )
    assert decision.status == "UNRESOLVED_NO_CONTENT_ACCESS"
    output = apply_content_decisions(_index(), (decision,))
    assert output["mapped_contests"] == 0
    assert output["ambiguous_contests"] == 1
