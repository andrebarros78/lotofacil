from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Sequence

from .video_index import (
    LOTTERY_TITLE_RE,
    LOTOFACIL_TITLE_RE,
    VideoMetadata,
    is_official_caixa_video,
    is_trusted_historical_broadcast,
    parse_lotofacil_contest_ids,
    parse_title_date,
)


@dataclass(frozen=True, slots=True)
class GapRecoveryDecision:
    contest_id: int
    status: str
    winner_video_id: str | None
    winner_url: str | None
    candidate_video_ids: tuple[str, ...]
    candidate_urls: tuple[str, ...]
    score: int | None
    evidence_basis: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "contest_id": self.contest_id,
            "status": self.status,
            "winner_video_id": self.winner_video_id,
            "winner_url": self.winner_url,
            "candidate_video_ids": list(self.candidate_video_ids),
            "candidate_urls": list(self.candidate_urls),
            "score": self.score,
            "evidence_basis": list(self.evidence_basis),
        }


def remaining_gap_searches(
    records: Sequence[dict[str, object]],
    *,
    results_per_query: int = 5,
) -> tuple[str, ...]:
    if results_per_query < 1:
        raise ValueError("P15_GAP_RESULTS_PER_QUERY_INVALID")
    searches: list[str] = []
    for record in records:
        if record.get("mapping_status") != "MISSING":
            continue
        contest_id = int(record["contest_id"])
        draw_date = dt.date.fromisoformat(str(record["draw_date"]))
        date = draw_date.strftime("%d/%m/%Y")
        variants = (
            f'Lotofácil concurso {contest_id} "{date}"',
            f'Lotofácil {contest_id} Loterias CAIXA {date}',
            f'Loterias CAIXA "{date}" Lotofácil',
            f'Loterias Caixa Sorteios de {date} Lotofácil',
        )
        searches.extend(f"ytsearch{results_per_query}:{query}" for query in variants)
    return tuple(searches)


def _score_candidate(record: dict[str, object], video: VideoMetadata) -> tuple[int, tuple[str, ...]] | None:
    contest_id = int(record["contest_id"])
    draw_date = dt.date.fromisoformat(str(record["draw_date"]))
    official = is_official_caixa_video(video)
    trusted = is_trusted_historical_broadcast(video)
    if not official and not trusted:
        return None

    title_date = parse_title_date(video.title)
    explicit = set(parse_lotofacil_contest_ids(f"{video.title}\n{video.description}"))
    if title_date is not None and title_date != draw_date:
        return None
    if explicit and contest_id not in explicit:
        return None

    score = 0
    evidence: list[str] = []
    if official:
        score += 100
        evidence.append("GAP_OFFICIAL_CAIXA_CHANNEL")
    else:
        score += 30
        evidence.append("GAP_TRUSTED_REDETV_CHANNEL")

    if title_date == draw_date:
        score += 80
        evidence.append("GAP_EXACT_TITLE_DATE")
    if contest_id in explicit:
        score += 100
        evidence.append("GAP_EXPLICIT_CONTEST_ID")
    if LOTOFACIL_TITLE_RE.search(video.title):
        score += 20
        evidence.append("GAP_LOTOFACIL_TITLE")
    if LOTTERY_TITLE_RE.search(video.title):
        score += 15
        evidence.append("GAP_LOTERIAS_CAIXA_TITLE")

    # Fail closed: query relevance alone can never map a contest.
    if official:
        strong = (title_date == draw_date and bool(LOTTERY_TITLE_RE.search(video.title))) or (
            contest_id in explicit and title_date == draw_date
        )
    else:
        strong = contest_id in explicit and title_date == draw_date
    if not strong:
        return None
    return score, tuple(evidence)


def decide_remaining_gap(
    record: dict[str, object],
    candidates: Sequence[VideoMetadata],
    *,
    minimum_margin: int = 10,
) -> GapRecoveryDecision:
    scored: list[tuple[int, VideoMetadata, tuple[str, ...]]] = []
    seen: set[str] = set()
    for video in candidates:
        if video.video_id in seen:
            continue
        seen.add(video.video_id)
        result = _score_candidate(record, video)
        if result is None:
            continue
        score, evidence = result
        scored.append((score, video, evidence))
    scored.sort(key=lambda item: (-item[0], item[1].video_id))

    contest_id = int(record["contest_id"])
    ids = tuple(item[1].video_id for item in scored)
    urls = tuple(item[1].webpage_url for item in scored)
    if not scored:
        return GapRecoveryDecision(contest_id, "STILL_MISSING", None, None, (), (), None, ("GAP_FAIL_CLOSED",))

    if len(scored) > 1 and scored[0][0] - scored[1][0] < minimum_margin:
        return GapRecoveryDecision(
            contest_id,
            "GAP_AMBIGUOUS",
            None,
            None,
            ids,
            urls,
            scored[0][0],
            ("MULTIPLE_STRONG_GAP_CANDIDATES", "GAP_FAIL_CLOSED"),
        )

    score, winner, evidence = scored[0]
    return GapRecoveryDecision(
        contest_id,
        "RECOVERED_STRICT",
        winner.video_id,
        winner.webpage_url,
        ids,
        urls,
        score,
        (*evidence, "PHASE2_REMAINING_GAP_RECOVERY"),
    )


def apply_gap_decisions(
    index_payload: dict[str, object],
    decisions: Sequence[GapRecoveryDecision],
) -> dict[str, object]:
    by_contest = {decision.contest_id: decision for decision in decisions}
    output = dict(index_payload)
    raw_records = index_payload.get("records")
    if not isinstance(raw_records, list):
        raise ValueError("P15_GAP_INDEX_RECORDS_MISSING")

    mapped_gain = 0
    ambiguous_gain = 0
    records: list[dict[str, object]] = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        record = dict(raw)
        if record.get("mapping_status") != "MISSING":
            records.append(record)
            continue
        contest_id = int(record["contest_id"])
        decision = by_contest.get(contest_id)
        if decision is None or decision.status == "STILL_MISSING":
            records.append(record)
            continue
        if decision.status == "RECOVERED_STRICT" and decision.winner_video_id:
            record["mapping_status"] = "MAPPED"
            record["confidence"] = "HIGH_GAP_RECOVERY"
            record["video_id"] = decision.winner_video_id
            record["video_url"] = decision.winner_url
            record["candidate_video_ids"] = list(decision.candidate_video_ids)
            record["candidate_video_urls"] = list(decision.candidate_urls)
            record["evidence_basis"] = list(decision.evidence_basis)
            mapped_gain += 1
        elif decision.status == "GAP_AMBIGUOUS":
            record["mapping_status"] = "AMBIGUOUS"
            record["confidence"] = "CANDIDATE_SET_ONLY"
            record["candidate_video_ids"] = list(decision.candidate_video_ids)
            record["candidate_video_urls"] = list(decision.candidate_urls)
            record["evidence_basis"] = list(decision.evidence_basis)
            ambiguous_gain += 1
        records.append(record)

    eligible = int(index_payload.get("eligible_contests") or len(records))
    mapped = int(index_payload.get("mapped_contests") or 0) + mapped_gain
    ambiguous = int(index_payload.get("ambiguous_contests") or 0) + ambiguous_gain
    missing = int(index_payload.get("missing_contests") or 0) - mapped_gain - ambiguous_gain
    output["schema_version"] = max(5, int(index_payload.get("schema_version") or 0))
    output["mapped_contests"] = mapped
    output["ambiguous_contests"] = ambiguous
    output["missing_contests"] = missing
    output["accessible_contests"] = mapped + ambiguous
    output["candidate_available_contests"] = mapped + ambiguous
    output["coverage_ratio"] = mapped / eligible if eligible else 0.0
    output["accessible_ratio"] = (mapped + ambiguous) / eligible if eligible else 0.0
    output["records"] = records
    output["predictive_evidence"] = "NOT_ESTABLISHED"
    output["purchase_executed"] = False
    return output
