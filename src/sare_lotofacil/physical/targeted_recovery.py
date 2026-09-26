from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from .video_index import (
    LOTTERY_TITLE_RE,
    LOTOFACIL_TITLE_RE,
    PhysicalVideoIndex,
    VideoIndexRecord,
    VideoMetadata,
    is_official_caixa_video,
    is_trusted_historical_broadcast,
    parse_lotofacil_contest_ids,
    parse_title_date,
)


@dataclass(frozen=True, slots=True)
class RecoveryDiagnostics:
    targeted_records: int
    resolved_ambiguities: int
    unresolved_ambiguities: int


def targeted_searches(
    records: Sequence[VideoIndexRecord],
    *,
    statuses: frozenset[str],
    results_per_contest: int = 3,
) -> tuple[str, ...]:
    """Build exact contest+date YouTube searches only for unresolved records."""

    if results_per_contest < 1:
        raise ValueError("P15_TARGETED_RESULTS_PER_CONTEST_INVALID")
    searches: list[str] = []
    for record in records:
        if record.mapping_status not in statuses:
            continue
        draw_date = dt.date.fromisoformat(record.draw_date)
        date_text = draw_date.strftime("%d/%m/%Y")
        query = f"Lotofácil concurso {record.contest_id} {date_text} Loterias CAIXA"
        searches.append(f"ytsearch{results_per_contest}:{query}")
    return tuple(searches)


def _upload_date_matches(video: VideoMetadata, draw_date: dt.date) -> bool:
    value = (video.upload_date or "").strip()
    if len(value) != 8 or not value.isdigit():
        return False
    try:
        parsed = dt.datetime.strptime(value, "%Y%m%d").date()
    except ValueError:
        return False
    return parsed == draw_date


def _strict_score(
    record: VideoIndexRecord,
    video: VideoMetadata,
) -> tuple[int, tuple[str, ...], bool] | None:
    """Score only observable metadata; never uses the drawn numbers."""

    draw_date = dt.date.fromisoformat(record.draw_date)
    official = is_official_caixa_video(video)
    trusted = is_trusted_historical_broadcast(video)
    if not official and not trusted:
        return None

    title_date = parse_title_date(video.title)
    if title_date is not None and title_date != draw_date:
        return None

    title_ids = parse_lotofacil_contest_ids(video.title)
    description_ids = parse_lotofacil_contest_ids(video.description)
    explicit_ids = set(title_ids).union(description_ids)
    if explicit_ids and record.contest_id not in explicit_ids:
        return None

    score = 0
    evidence: list[str] = []
    strong = False

    if official:
        score += 100
        evidence.append("STRICT_OFFICIAL_CAIXA_CHANNEL")
    else:
        score += 30
        evidence.append("STRICT_TRUSTED_REDETV_CHANNEL")

    if title_date == draw_date:
        score += 40
        evidence.append("STRICT_TITLE_DATE_MATCH")

    if record.contest_id in title_ids:
        score += 55
        evidence.append("STRICT_CONTEST_ID_IN_TITLE")
        strong = True
    if record.contest_id in description_ids:
        score += 35
        evidence.append("STRICT_CONTEST_ID_IN_DESCRIPTION")
        strong = True

    if official and LOTTERY_TITLE_RE.search(video.title) and title_date == draw_date:
        score += 60
        evidence.append("STRICT_CANONICAL_CAIXA_BROADCAST_TITLE")
        strong = True
    elif trusted and LOTTERY_TITLE_RE.search(video.title) and title_date == draw_date:
        score += 35
        evidence.append("STRICT_DOCUMENTED_BROADCAST_TITLE")
        strong = True

    if LOTOFACIL_TITLE_RE.search(video.title):
        score += 10
        evidence.append("STRICT_LOTOFACIL_TITLE_MENTION")

    if _upload_date_matches(video, draw_date):
        score += 15
        evidence.append("STRICT_UPLOAD_DATE_MATCH")

    if video.duration is not None:
        if video.duration >= 1200:
            score += 20
            evidence.append("STRICT_FULL_LENGTH_DURATION")
        elif video.duration >= 600:
            score += 10
            evidence.append("STRICT_LONG_DURATION")
        elif video.duration < 300:
            score -= 30
            evidence.append("STRICT_SHORT_CLIP_PENALTY")

    return score, tuple(evidence), strong


def resolve_ambiguities_strict(
    index: PhysicalVideoIndex,
    videos_by_id: Mapping[str, VideoMetadata],
    *,
    minimum_margin: int = 15,
) -> tuple[PhysicalVideoIndex, RecoveryDiagnostics]:
    """Resolve only uniquely supported ambiguity; equal evidence remains ambiguous."""

    if minimum_margin < 1:
        raise ValueError("P15_STRICT_MINIMUM_MARGIN_INVALID")

    records: list[VideoIndexRecord] = []
    resolved = 0
    targeted = 0

    for record in index.records:
        if record.mapping_status != "AMBIGUOUS":
            records.append(record)
            continue
        targeted += 1

        scored: list[tuple[int, VideoMetadata, tuple[str, ...], bool]] = []
        for video_id in record.candidate_video_ids:
            video = videos_by_id.get(video_id)
            if video is None:
                continue
            result = _strict_score(record, video)
            if result is None:
                continue
            score, evidence, strong = result
            scored.append((score, video, evidence, strong))

        scored.sort(key=lambda item: (-item[0], item[1].video_id))
        if not scored or not scored[0][3]:
            records.append(record)
            continue

        runner_up = scored[1][0] if len(scored) > 1 else -10_000
        if scored[0][0] - runner_up < minimum_margin:
            records.append(record)
            continue

        _score, winner, strict_evidence, _strong = scored[0]
        title_date = parse_title_date(winner.title)
        explicit_ids = parse_lotofacil_contest_ids(f"{winner.title}\n{winner.description}")
        records.append(
            replace(
                record,
                video_id=winner.video_id,
                video_url=winner.webpage_url,
                video_title=winner.title,
                title_date=title_date.isoformat() if title_date else None,
                explicit_contest_ids=explicit_ids,
                channel=winner.channel or winner.uploader,
                channel_id=winner.channel_id,
                duration_seconds=winner.duration,
                mapping_status="MAPPED",
                confidence="HIGH_STRICT_METADATA_RESOLUTION",
                evidence_basis=tuple(
                    dict.fromkeys(
                        (
                            *record.evidence_basis,
                            *strict_evidence,
                            "PHASE2_STRICT_METADATA_DISAMBIGUATION",
                        )
                    )
                ),
            )
        )
        resolved += 1

    mapped = index.mapped_contests + resolved
    ambiguous = index.ambiguous_contests - resolved
    resolved_index = replace(
        index,
        schema_version=max(index.schema_version, 4),
        mapped_contests=mapped,
        ambiguous_contests=ambiguous,
        coverage_ratio=mapped / index.eligible_contests,
        records=tuple(records),
    )
    return resolved_index, RecoveryDiagnostics(
        targeted_records=targeted,
        resolved_ambiguities=resolved,
        unresolved_ambiguities=ambiguous,
    )
