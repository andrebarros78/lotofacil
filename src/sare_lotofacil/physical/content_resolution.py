from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .content_features import ProcedureAssessment


@dataclass(frozen=True, slots=True)
class ContentResolutionDecision:
    contest_id: int
    status: str
    winner_video_id: str | None
    winner_score: int | None
    runner_up_score: int | None
    margin: int | None
    complete_candidates: tuple[str, ...]
    assessed_candidates: tuple[str, ...]
    evidence_basis: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "contest_id": self.contest_id,
            "status": self.status,
            "winner_video_id": self.winner_video_id,
            "winner_score": self.winner_score,
            "runner_up_score": self.runner_up_score,
            "margin": self.margin,
            "complete_candidates": list(self.complete_candidates),
            "assessed_candidates": list(self.assessed_candidates),
            "evidence_basis": list(self.evidence_basis),
        }


def decide_ambiguous_content(
    *,
    contest_id: int,
    candidate_video_ids: Sequence[str],
    assessments_by_video: Mapping[str, ProcedureAssessment],
    minimum_margin: int = 20,
) -> ContentResolutionDecision:
    """Resolve an ambiguous archive link using content evidence only.

    The decision never compares the drawn result. A candidate must independently
    show a complete Lotofácil procedure in timed content. Equal/weak evidence
    remains unresolved.
    """

    if minimum_margin < 1:
        raise ValueError("P15_CONTENT_MINIMUM_MARGIN_INVALID")

    assessed = [
        (video_id, assessments_by_video[video_id])
        for video_id in candidate_video_ids
        if video_id in assessments_by_video
    ]
    complete = [item for item in assessed if item[1].complete_procedure]
    complete.sort(key=lambda item: (-item[1].score, item[0]))

    if not complete:
        status = "UNRESOLVED_NO_COMPLETE_CONTENT"
        if not assessed:
            status = "UNRESOLVED_NO_CONTENT_ACCESS"
        return ContentResolutionDecision(
            contest_id=contest_id,
            status=status,
            winner_video_id=None,
            winner_score=None,
            runner_up_score=None,
            margin=None,
            complete_candidates=(),
            assessed_candidates=tuple(sorted(video_id for video_id, _ in assessed)),
            evidence_basis=("CONTENT_FAIL_CLOSED",),
        )

    winner_id, winner = complete[0]
    runner_up = complete[1][1].score if len(complete) > 1 else None
    margin = winner.score - runner_up if runner_up is not None else winner.score

    if len(complete) > 1 and margin < minimum_margin:
        return ContentResolutionDecision(
            contest_id=contest_id,
            status="UNRESOLVED_CONTENT_SCORE_TIE",
            winner_video_id=None,
            winner_score=winner.score,
            runner_up_score=runner_up,
            margin=margin,
            complete_candidates=tuple(video_id for video_id, _ in complete),
            assessed_candidates=tuple(sorted(video_id for video_id, _ in assessed)),
            evidence_basis=("MULTIPLE_COMPLETE_LOTOFACIL_PROCEDURES", "CONTENT_FAIL_CLOSED"),
        )

    basis = ["COMPLETE_LOTOFACIL_PROCEDURE_IN_TIMED_CONTENT"]
    if winner.contest_mentions:
        basis.append("CONTEST_ID_MENTION_IN_CONTENT")
    if winner.draw_sequence is not None:
        basis.append("DRAW_SEQUENCE_EXTRACTED_FROM_CONTENT")
    if runner_up is not None:
        basis.append("CONTENT_SCORE_MARGIN")

    return ContentResolutionDecision(
        contest_id=contest_id,
        status="RESOLVED_BY_CONTENT",
        winner_video_id=winner_id,
        winner_score=winner.score,
        runner_up_score=runner_up,
        margin=margin,
        complete_candidates=tuple(video_id for video_id, _ in complete),
        assessed_candidates=tuple(sorted(video_id for video_id, _ in assessed)),
        evidence_basis=tuple(basis),
    )


def apply_content_decisions(
    index_payload: dict[str, object],
    decisions: Sequence[ContentResolutionDecision],
) -> dict[str, object]:
    """Apply only explicit RESOLVED_BY_CONTENT decisions to a JSON index."""

    by_contest = {decision.contest_id: decision for decision in decisions}
    output = dict(index_payload)
    records = []
    resolved = 0

    raw_records = index_payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("P15_CONTENT_INDEX_RECORDS_MISSING")

    for raw in raw_records:
        if not isinstance(raw, dict):
            raise ValueError("P15_CONTENT_INDEX_RECORD_INVALID")
        record = dict(raw)
        contest_id = int(record["contest_id"])
        decision = by_contest.get(contest_id)
        if (
            record.get("mapping_status") == "AMBIGUOUS"
            and decision is not None
            and decision.status == "RESOLVED_BY_CONTENT"
            and decision.winner_video_id
        ):
            candidate_ids = [str(value) for value in record.get("candidate_video_ids") or []]
            candidate_urls = [str(value) for value in record.get("candidate_video_urls") or []]
            if decision.winner_video_id not in candidate_ids:
                raise ValueError(f"P15_CONTENT_WINNER_NOT_CANDIDATE:{contest_id}")
            position = candidate_ids.index(decision.winner_video_id)
            winner_url = candidate_urls[position] if position < len(candidate_urls) else None
            record["video_id"] = decision.winner_video_id
            record["video_url"] = winner_url
            record["mapping_status"] = "MAPPED"
            record["confidence"] = "HIGH_CONTENT_RESOLUTION"
            evidence = [str(value) for value in record.get("evidence_basis") or []]
            evidence.extend(decision.evidence_basis)
            evidence.append("PHASE2_CONTENT_RESOLUTION")
            record["evidence_basis"] = list(dict.fromkeys(evidence))
            resolved += 1
        records.append(record)

    eligible = int(index_payload.get("eligible_contests") or len(records))
    previous_mapped = int(index_payload.get("mapped_contests") or 0)
    previous_ambiguous = int(index_payload.get("ambiguous_contests") or 0)
    mapped = previous_mapped + resolved
    ambiguous = previous_ambiguous - resolved
    output["schema_version"] = max(5, int(index_payload.get("schema_version") or 0))
    output["mapped_contests"] = mapped
    output["ambiguous_contests"] = ambiguous
    output["accessible_contests"] = mapped + ambiguous
    output["candidate_available_contests"] = mapped + ambiguous
    output["coverage_ratio"] = mapped / eligible if eligible else 0.0
    output["accessible_ratio"] = (mapped + ambiguous) / eligible if eligible else 0.0
    output["records"] = records
    output["predictive_evidence"] = "NOT_ESTABLISHED"
    output["purchase_executed"] = False
    return output
