from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

OFFICIAL_CHANNEL_NAMES = {"CAIXA", "CAIXA ECONÔMICA FEDERAL"}
TRUSTED_HISTORICAL_BROADCASTER_NAMES = {"REDETV", "REDETV!", "REDE TV", "REDE TV!"}
LOTTERY_TITLE_RE = re.compile(r"\bLOTERIAS?\s+CAIXA\b", re.IGNORECASE)
LOTOFACIL_TITLE_RE = re.compile(r"\bloto\s*f[aá]cil\b", re.IGNORECASE)
TITLE_DATE_RE = re.compile(r"\b(?P<day>0?[1-9]|[12]\d|3[01])/(?P<month>0?[1-9]|1[0-2])/(?P<year>20\d{2})\b")
LOTOFACIL_CONTEST_RE = re.compile(
    r"\bloto\s*f[aá]cil\b[^\n\r]{0,60}?"
    r"(?:concurso\s*(?:n(?:[º°o]|\.)?\s*)?|n(?:[º°o]|\.)?\s*)"
    r"(?P<contest>\d{3,5})\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class CanonicalContest:
    contest_id: int
    draw_date: dt.date
    numbers: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    video_id: str
    title: str
    description: str
    webpage_url: str
    channel: str | None = None
    channel_id: str | None = None
    uploader: str | None = None
    upload_date: str | None = None
    timestamp: int | None = None
    duration: float | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "VideoMetadata":
        video_id = str(payload.get("id") or "").strip()
        if not video_id:
            raise ValueError("VIDEO_ID_MISSING")
        url = str(payload.get("webpage_url") or payload.get("url") or "").strip()
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={video_id}"
        return cls(
            video_id=video_id,
            title=str(payload.get("title") or "").strip(),
            description=str(payload.get("description") or ""),
            webpage_url=url,
            channel=_optional_text(payload.get("channel")),
            channel_id=_optional_text(payload.get("channel_id")),
            uploader=_optional_text(payload.get("uploader")),
            upload_date=_optional_text(payload.get("upload_date")),
            timestamp=_optional_int(payload.get("timestamp")),
            duration=_optional_float(payload.get("duration")),
        )


@dataclass(frozen=True, slots=True)
class VideoIndexRecord:
    contest_id: int
    draw_date: str
    numbers: tuple[int, ...]
    video_id: str | None
    video_url: str | None
    video_title: str | None
    title_date: str | None
    explicit_contest_ids: tuple[int, ...]
    channel: str | None
    channel_id: str | None
    duration_seconds: float | None
    mapping_status: str
    confidence: str
    evidence_basis: tuple[str, ...]
    candidate_video_ids: tuple[str, ...] = ()
    candidate_video_urls: tuple[str, ...] = ()
    start_seconds: float | None = None
    end_seconds: float | None = None
    sequence_extracted_from_video: tuple[int, ...] | None = None
    physical_features_status: str = "NOT_EXTRACTED"


@dataclass(frozen=True, slots=True)
class PhysicalVideoIndex:
    schema_version: int
    program_id: str
    source: str
    source_channel_url: str
    first_eligible_contest: int
    latest_contest: int
    eligible_contests: int
    discovered_videos: int
    mapped_contests: int
    candidate_available_contests: int
    accessible_contests: int
    missing_contests: int
    ambiguous_contests: int
    conflicting_contests: int
    coverage_ratio: float
    accessible_ratio: float
    exact_description_matches: int
    unique_title_date_matches: int
    official_channel_verified_videos: int
    trusted_broadcaster_verified_videos: int
    records: tuple[VideoIndexRecord, ...]
    discovery_errors: tuple[str, ...]
    predictive_evidence: str = "NOT_ESTABLISHED"
    purchase_executed: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_channel_name(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def _video_channel_names(video: VideoMetadata) -> set[str]:
    return {normalize_channel_name(video.channel), normalize_channel_name(video.uploader)}


def is_official_caixa_video(video: VideoMetadata) -> bool:
    return bool(_video_channel_names(video).intersection(OFFICIAL_CHANNEL_NAMES))


def is_trusted_historical_broadcast(video: VideoMetadata) -> bool:
    return bool(_video_channel_names(video).intersection(TRUSTED_HISTORICAL_BROADCASTER_NAMES))


def parse_title_date(title: str) -> dt.date | None:
    match = TITLE_DATE_RE.search(title or "")
    if not match:
        return None
    try:
        return dt.date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None


def parse_lotofacil_contest_ids(text: str) -> tuple[int, ...]:
    values = {int(match.group("contest")) for match in LOTOFACIL_CONTEST_RE.finditer(text or "")}
    return tuple(sorted(values))


def load_canonical_history(path: Path) -> tuple[CanonicalContest, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        raise RuntimeError("PHYSICAL_HISTORY_RECORDS_MISSING")

    contests: list[CanonicalContest] = []
    seen: set[int] = set()
    for raw in records:
        if not isinstance(raw, dict):
            raise RuntimeError("PHYSICAL_HISTORY_RECORD_INVALID")
        contest_id = int(raw["contest_id"])
        if contest_id in seen:
            raise RuntimeError(f"PHYSICAL_HISTORY_DUPLICATE_CONTEST:{contest_id}")
        seen.add(contest_id)
        draw_date = dt.date.fromisoformat(str(raw["draw_date"]))
        numbers = tuple(sorted(int(number) for number in raw["numbers"]))
        if len(numbers) != 15 or len(set(numbers)) != 15 or min(numbers) < 1 or max(numbers) > 25:
            raise RuntimeError(f"PHYSICAL_HISTORY_INVALID_NUMBERS:{contest_id}")
        contests.append(CanonicalContest(contest_id, draw_date, numbers))
    contests.sort(key=lambda item: item.contest_id)
    return tuple(contests)


def load_jsonl_metadata(path: Path) -> tuple[VideoMetadata, ...]:
    videos: list[VideoMetadata] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise TypeError("metadata line must be an object")
            video = VideoMetadata.from_mapping(payload)
        except Exception as exc:  # noqa: BLE001 - discovery evidence must preserve malformed inputs
            raise RuntimeError(f"PHYSICAL_VIDEO_METADATA_INVALID_LINE:{line_number}:{exc}") from exc
        if video.video_id in seen:
            continue
        seen.add(video.video_id)
        videos.append(video)
    return tuple(videos)


def _video_evidence(video: VideoMetadata) -> tuple[dt.date | None, tuple[int, ...], tuple[str, ...]]:
    title_date = parse_title_date(video.title)
    explicit_ids = parse_lotofacil_contest_ids(f"{video.title}\n{video.description}")
    basis: list[str] = []
    if LOTTERY_TITLE_RE.search(video.title):
        basis.append("LOTERIAS_CAIXA_TITLE")
    if LOTOFACIL_TITLE_RE.search(video.title):
        basis.append("LOTOFACIL_TITLE_MENTION")
    if title_date is not None:
        basis.append("TITLE_DATE")
    if explicit_ids:
        basis.append("EXPLICIT_LOTOFACIL_CONTEST")
    if is_official_caixa_video(video):
        basis.append("OFFICIAL_CAIXA_CHANNEL")
    if is_trusted_historical_broadcast(video):
        basis.append("TRUSTED_HISTORICAL_REDETV_BROADCAST")
    return title_date, explicit_ids, tuple(basis)


def _candidate_ids_and_urls(
    candidates: Sequence[tuple[int, VideoMetadata, tuple[str, ...], dt.date | None, tuple[int, ...]]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    by_id = {candidate[1].video_id: candidate[1].webpage_url for candidate in candidates}
    ids = tuple(sorted(by_id))
    return ids, tuple(by_id[video_id] for video_id in ids)


def build_video_index(
    canonical_history: Sequence[CanonicalContest],
    videos: Sequence[VideoMetadata],
    *,
    first_eligible_contest: int = 1874,
    source_channel_url: str = "https://www.youtube.com/user/canalcaixa",
    discovery_errors: Iterable[str] = (),
) -> PhysicalVideoIndex:
    eligible = tuple(item for item in canonical_history if item.contest_id >= first_eligible_contest)
    if not eligible:
        raise ValueError("PHYSICAL_NO_ELIGIBLE_CONTESTS")

    by_id = {item.contest_id: item for item in eligible}
    by_date: dict[dt.date, list[CanonicalContest]] = {}
    for item in eligible:
        by_date.setdefault(item.draw_date, []).append(item)

    candidate_map: dict[int, list[tuple[int, VideoMetadata, tuple[str, ...], dt.date | None, tuple[int, ...]]]] = {}
    conflicts: set[int] = set()
    exact_description_matches: set[int] = set()
    unique_title_matches: set[int] = set()
    official_verified: set[str] = set()
    trusted_broadcaster_verified: set[str] = set()

    for video in videos:
        title_date, explicit_ids, basis = _video_evidence(video)
        official = is_official_caixa_video(video)
        historical_broadcaster = is_trusted_historical_broadcast(video)
        if official:
            official_verified.add(video.video_id)
        if historical_broadcaster:
            trusted_broadcaster_verified.add(video.video_id)

        if not official and not historical_broadcaster:
            continue

        for contest_id in explicit_ids:
            contest = by_id.get(contest_id)
            if contest is None:
                continue
            if title_date is not None and title_date != contest.draw_date:
                conflicts.add(contest_id)
                continue
            if historical_broadcaster and not official and title_date != contest.draw_date:
                continue

            rank = 300
            evidence = list(basis)
            evidence.append("CANONICAL_CONTEST_ID_MATCH")
            if title_date == contest.draw_date:
                rank += 20
                evidence.append("CANONICAL_DATE_MATCH")
            if official:
                rank += 20
            elif historical_broadcaster:
                rank += 5
            candidate_map.setdefault(contest_id, []).append(
                (rank, video, tuple(dict.fromkeys(evidence)), title_date, explicit_ids)
            )
            exact_description_matches.add(contest_id)

        if title_date is None or title_date not in by_date or len(by_date[title_date]) != 1:
            continue
        contest = by_date[title_date][0]
        if explicit_ids and contest.contest_id not in explicit_ids:
            continue

        if official:
            rank = 220
            evidence = list(basis)
            evidence.extend(("UNIQUE_CANONICAL_DRAW_DATE", "CANONICAL_DATE_MATCH"))
            candidate_map.setdefault(contest.contest_id, []).append(
                (rank, video, tuple(dict.fromkeys(evidence)), title_date, explicit_ids)
            )
            if not explicit_ids:
                unique_title_matches.add(contest.contest_id)

        elif historical_broadcaster and "LOTOFACIL_TITLE_MENTION" in basis:
            rank = 215
            evidence = list(basis)
            evidence.extend(
                (
                    "UNIQUE_CANONICAL_DRAW_DATE",
                    "CANONICAL_DATE_MATCH",
                    "HISTORICAL_BROADCAST_LOTOFACIL_TITLE_DATE_MATCH",
                )
            )
            candidate_map.setdefault(contest.contest_id, []).append(
                (rank, video, tuple(dict.fromkeys(evidence)), title_date, explicit_ids)
            )
            unique_title_matches.add(contest.contest_id)

    records: list[VideoIndexRecord] = []
    mapped = 0
    missing = 0
    ambiguous = 0
    conflict_count = 0
    candidate_available = 0

    for contest in eligible:
        candidates = candidate_map.get(contest.contest_id, [])
        candidates.sort(key=lambda item: (-item[0], item[1].video_id))
        all_candidate_ids, all_candidate_urls = _candidate_ids_and_urls(candidates)

        if contest.contest_id in conflicts and not candidates:
            records.append(
                VideoIndexRecord(
                    contest_id=contest.contest_id,
                    draw_date=contest.draw_date.isoformat(),
                    numbers=contest.numbers,
                    video_id=None,
                    video_url=None,
                    video_title=None,
                    title_date=None,
                    explicit_contest_ids=(),
                    channel=None,
                    channel_id=None,
                    duration_seconds=None,
                    mapping_status="CONFLICT",
                    confidence="NONE",
                    evidence_basis=("DATE_CONFLICT",),
                )
            )
            conflict_count += 1
            continue

        if not candidates:
            records.append(
                VideoIndexRecord(
                    contest_id=contest.contest_id,
                    draw_date=contest.draw_date.isoformat(),
                    numbers=contest.numbers,
                    video_id=None,
                    video_url=None,
                    video_title=None,
                    title_date=None,
                    explicit_contest_ids=(),
                    channel=None,
                    channel_id=None,
                    duration_seconds=None,
                    mapping_status="MISSING",
                    confidence="NONE",
                    evidence_basis=(),
                )
            )
            missing += 1
            continue

        best_rank = candidates[0][0]
        best = [candidate for candidate in candidates if candidate[0] == best_rank]
        best_ids, best_urls = _candidate_ids_and_urls(best)
        if len(best_ids) > 1:
            channels = {candidate[1].channel or candidate[1].uploader for candidate in best}
            records.append(
                VideoIndexRecord(
                    contest_id=contest.contest_id,
                    draw_date=contest.draw_date.isoformat(),
                    numbers=contest.numbers,
                    video_id=None,
                    video_url=None,
                    video_title=None,
                    title_date=contest.draw_date.isoformat(),
                    explicit_contest_ids=(),
                    channel=next(iter(channels)) if len(channels) == 1 else None,
                    channel_id=None,
                    duration_seconds=None,
                    mapping_status="AMBIGUOUS",
                    confidence="CANDIDATE_SET_ONLY",
                    evidence_basis=("MULTIPLE_EQUAL_RANK_VIDEOS", "PHASE2_CONTENT_DISAMBIGUATION_REQUIRED"),
                    candidate_video_ids=best_ids,
                    candidate_video_urls=best_urls,
                )
            )
            ambiguous += 1
            candidate_available += 1
            continue

        _rank, video, evidence, title_date, explicit_ids = candidates[0]
        if "OFFICIAL_CAIXA_CHANNEL" in evidence and "CANONICAL_CONTEST_ID_MATCH" in evidence and "CANONICAL_DATE_MATCH" in evidence:
            confidence = "VERY_HIGH"
        elif "CANONICAL_CONTEST_ID_MATCH" in evidence and "CANONICAL_DATE_MATCH" in evidence:
            confidence = "HIGH"
        elif "HISTORICAL_BROADCAST_LOTOFACIL_TITLE_DATE_MATCH" in evidence:
            confidence = "HIGH"
        elif "CANONICAL_CONTEST_ID_MATCH" in evidence:
            confidence = "HIGH"
        elif "OFFICIAL_CAIXA_CHANNEL" in evidence:
            confidence = "MEDIUM_HIGH"
        else:
            confidence = "MEDIUM"
        records.append(
            VideoIndexRecord(
                contest_id=contest.contest_id,
                draw_date=contest.draw_date.isoformat(),
                numbers=contest.numbers,
                video_id=video.video_id,
                video_url=video.webpage_url,
                video_title=video.title,
                title_date=title_date.isoformat() if title_date else None,
                explicit_contest_ids=explicit_ids,
                channel=video.channel or video.uploader,
                channel_id=video.channel_id,
                duration_seconds=video.duration,
                mapping_status="MAPPED",
                confidence=confidence,
                evidence_basis=evidence,
                candidate_video_ids=all_candidate_ids,
                candidate_video_urls=all_candidate_urls,
            )
        )
        mapped += 1
        candidate_available += 1

    eligible_count = len(eligible)
    accessible = mapped + ambiguous
    return PhysicalVideoIndex(
        schema_version=3,
        program_id="SARE-P15-PHYSICAL-OBSERVATION-V1",
        source="CAIXA_OFFICIAL_PLUS_VERIFIED_HISTORICAL_BROADCAST_ARCHIVES",
        source_channel_url=source_channel_url,
        first_eligible_contest=first_eligible_contest,
        latest_contest=eligible[-1].contest_id,
        eligible_contests=eligible_count,
        discovered_videos=len(videos),
        mapped_contests=mapped,
        candidate_available_contests=candidate_available,
        accessible_contests=accessible,
        missing_contests=missing,
        ambiguous_contests=ambiguous,
        conflicting_contests=conflict_count,
        coverage_ratio=mapped / eligible_count,
        accessible_ratio=accessible / eligible_count,
        exact_description_matches=len(exact_description_matches),
        unique_title_date_matches=len(unique_title_matches),
        official_channel_verified_videos=len(official_verified),
        trusted_broadcaster_verified_videos=len(trusted_broadcaster_verified),
        records=tuple(records),
        discovery_errors=tuple(str(item) for item in discovery_errors),
    )
