from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import quote

from sare_lotofacil.physical.video_index import (
    LOTTERY_TITLE_RE,
    TITLE_DATE_RE,
    VideoMetadata,
    build_video_index,
    load_canonical_history,
    load_jsonl_metadata,
)

DEFAULT_CHANNEL_BASE_URL = "https://www.youtube.com/user/canalcaixa"
DEFAULT_CHANNEL_SEARCH_URL = f"{DEFAULT_CHANNEL_BASE_URL}/search?query=Loterias%20CAIXA"
DEFAULT_CHANNEL_VIDEOS_URL = f"{DEFAULT_CHANNEL_BASE_URL}/videos"
DEFAULT_CHANNEL_STREAMS_URL = f"{DEFAULT_CHANNEL_BASE_URL}/streams"


def _run(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        env=env,
    )


def _parse_flat_stdout(stdout: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("id"):
            entries.append(payload)
    return entries


def _flat_discover(
    yt_dlp_bin: str,
    source_url: str,
    *,
    playlist_end: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, object]], list[str]]:
    command = [
        yt_dlp_bin,
        "--ignore-errors",
        "--no-warnings",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(playlist_end),
        source_url,
    ]
    try:
        completed = _run(command, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return [], [f"FLAT_DISCOVERY_TIMEOUT:{source_url}:{exc.timeout}"]

    errors: list[str] = []
    if completed.returncode != 0:
        errors.append(f"FLAT_DISCOVERY_EXIT_{completed.returncode}:{source_url}:{completed.stderr[-2000:]}")
    return _parse_flat_stdout(completed.stdout), errors


def _flat_discover_many(
    yt_dlp_bin: str,
    source_urls: Sequence[str],
    *,
    playlist_end: int,
    timeout_seconds: int,
) -> tuple[list[dict[str, object]], list[str]]:
    if not source_urls:
        return [], []
    command = [
        yt_dlp_bin,
        "--ignore-errors",
        "--no-warnings",
        "--flat-playlist",
        "--dump-json",
        "--playlist-end",
        str(playlist_end),
        *source_urls,
    ]
    try:
        completed = _run(command, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired as exc:
        return [], [f"FLAT_SHARDED_DISCOVERY_TIMEOUT:{len(source_urls)}:{exc.timeout}"]

    errors: list[str] = []
    if completed.returncode != 0:
        errors.append(f"FLAT_SHARDED_DISCOVERY_EXIT_{completed.returncode}:{completed.stderr[-2000:]}")
    return _parse_flat_stdout(completed.stdout), errors


def _looks_like_lottery_video(payload: dict[str, object]) -> bool:
    title = str(payload.get("title") or "")
    return bool(LOTTERY_TITLE_RE.search(title) and TITLE_DATE_RE.search(title))


def _flat_entry_to_official_video(payload: dict[str, object]) -> VideoMetadata:
    enriched = dict(payload)
    enriched["channel"] = str(payload.get("channel") or "CAIXA")
    enriched["uploader"] = str(payload.get("uploader") or "CAIXA")
    video_id = str(payload.get("id") or "").strip()
    enriched["webpage_url"] = str(
        payload.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}"
    )
    return VideoMetadata.from_mapping(enriched)


def _month_floor(value: dt.date) -> dt.date:
    return value.replace(day=1)


def _next_month(value: dt.date) -> dt.date:
    if value.month == 12:
        return dt.date(value.year + 1, 1, 1)
    return dt.date(value.year, value.month + 1, 1)


def monthly_channel_search_urls(
    first_date: dt.date,
    last_date: dt.date,
    *,
    channel_base_url: str = DEFAULT_CHANNEL_BASE_URL,
) -> tuple[str, ...]:
    """Create bounded channel-search shards matching the dd/mm/yyyy title convention."""

    current = _month_floor(first_date)
    end = _month_floor(last_date)
    urls: list[str] = []
    while current <= end:
        query = quote(f"Loterias CAIXA {current.month:02d}/{current.year}")
        urls.append(f"{channel_base_url}/search?query={query}")
        current = _next_month(current)
    return tuple(urls)


def _hydrate_metadata(
    yt_dlp_bin: str,
    video_ids: Iterable[str],
    *,
    timeout_seconds: int,
) -> tuple[tuple[VideoMetadata, ...], list[str]]:
    ids = tuple(dict.fromkeys(str(value).strip() for value in video_ids if str(value).strip()))
    if not ids:
        return (), []

    errors: list[str] = []
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
        batch_path = Path(handle.name)
        for video_id in ids:
            handle.write(f"https://www.youtube.com/watch?v={video_id}\n")

    try:
        command = [
            yt_dlp_bin,
            "--ignore-errors",
            "--no-warnings",
            "--skip-download",
            "--dump-json",
            "--batch-file",
            str(batch_path),
        ]
        try:
            completed = _run(command, timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            return (), [f"HYDRATE_TIMEOUT:{exc.timeout}"]
    finally:
        batch_path.unlink(missing_ok=True)

    if completed.returncode != 0:
        errors.append(f"HYDRATE_EXIT_{completed.returncode}:{completed.stderr[-2000:]}")

    videos: list[VideoMetadata] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            if isinstance(payload, dict) and payload.get("id"):
                videos.append(VideoMetadata.from_mapping(payload))
        except Exception as exc:  # noqa: BLE001 - preserve discovery evidence
            errors.append(f"HYDRATE_PARSE_ERROR:{type(exc).__name__}:{exc}")
    return tuple(videos), errors


def discover_official_metadata(
    *,
    yt_dlp_bin: str,
    source_url: str,
    fallback_url: str,
    streams_url: str,
    shard_urls: Sequence[str] = (),
    playlist_end: int,
    timeout_seconds: int,
    hydrate_limit: int = 0,
) -> tuple[tuple[VideoMetadata, ...], tuple[str, ...]]:
    """Discover public lottery transmissions from all official-channel surfaces.

    Generic channel search and current ``videos``/``streams`` pagination can omit
    old public material. Month-scoped searches are therefore unioned with those
    surfaces. The archive remains deduplicated by YouTube video id.
    """

    all_entries: list[dict[str, object]] = []
    errors: list[str] = []
    for url in (source_url, fallback_url, streams_url):
        entries, source_errors = _flat_discover(
            yt_dlp_bin,
            url,
            playlist_end=playlist_end,
            timeout_seconds=timeout_seconds,
        )
        all_entries.extend(entries)
        errors.extend(source_errors)

    if shard_urls:
        shard_entries, shard_errors = _flat_discover_many(
            yt_dlp_bin,
            shard_urls,
            playlist_end=min(100, playlist_end),
            timeout_seconds=timeout_seconds,
        )
        all_entries.extend(shard_entries)
        errors.extend(shard_errors)

    combined: dict[str, dict[str, object]] = {}
    for entry in all_entries:
        if not _looks_like_lottery_video(entry):
            continue
        video_id = str(entry.get("id") or "").strip()
        if video_id:
            combined.setdefault(video_id, entry)

    if not combined:
        errors.append("OFFICIAL_CHANNEL_FLAT_DISCOVERY_EMPTY")
        return (), tuple(errors)

    flat_videos = {
        video_id: _flat_entry_to_official_video(entry)
        for video_id, entry in combined.items()
    }

    if hydrate_limit > 0:
        selected_ids = tuple(sorted(flat_videos))[:hydrate_limit]
        hydrated, hydrate_errors = _hydrate_metadata(
            yt_dlp_bin,
            selected_ids,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(hydrate_errors)
        for video in hydrated:
            flat_videos[video.video_id] = video

    return tuple(flat_videos[video_id] for video_id in sorted(flat_videos)), tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a keyless index from canonical Lotofácil contests to official CAIXA YouTube transmissions."
    )
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--metadata-jsonl", type=Path)
    parser.add_argument("--yt-dlp-bin", default="yt-dlp")
    parser.add_argument("--channel-url", default=DEFAULT_CHANNEL_SEARCH_URL)
    parser.add_argument("--fallback-channel-url", default=DEFAULT_CHANNEL_VIDEOS_URL)
    parser.add_argument("--streams-channel-url", default=DEFAULT_CHANNEL_STREAMS_URL)
    parser.add_argument("--channel-base-url", default=DEFAULT_CHANNEL_BASE_URL)
    parser.add_argument("--first-contest", type=int, default=1874)
    parser.add_argument("--playlist-end", type=int, default=10000)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--disable-month-shards", action="store_true")
    parser.add_argument(
        "--hydrate-limit",
        type=int,
        default=0,
        help="Optional bounded number of flat entries to enrich with full per-video metadata.",
    )
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--min-accessible-ratio", type=float, default=0.0)
    args = parser.parse_args()

    history = load_canonical_history(args.history)
    eligible_history = tuple(item for item in history if item.contest_id >= args.first_contest)
    if not eligible_history:
        raise RuntimeError("P15_PHYSICAL_NO_ELIGIBLE_HISTORY")

    if args.metadata_jsonl is not None:
        videos = load_jsonl_metadata(args.metadata_jsonl)
        errors: tuple[str, ...] = ()
        source_url = "FILE_SUPPLIED_METADATA"
    else:
        shard_urls = () if args.disable_month_shards else monthly_channel_search_urls(
            eligible_history[0].draw_date,
            eligible_history[-1].draw_date,
            channel_base_url=args.channel_base_url,
        )
        videos, errors = discover_official_metadata(
            yt_dlp_bin=args.yt_dlp_bin,
            source_url=args.channel_url,
            fallback_url=args.fallback_channel_url,
            streams_url=args.streams_channel_url,
            shard_urls=shard_urls,
            playlist_end=args.playlist_end,
            timeout_seconds=args.timeout_seconds,
            hydrate_limit=args.hydrate_limit,
        )
        source_url = args.channel_url

    index = build_video_index(
        history,
        videos,
        first_eligible_contest=args.first_contest,
        source_channel_url=source_url,
        discovery_errors=errors,
    )
    rendered = json.dumps(index.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.out.write_text(rendered, encoding="utf-8")

    summary = {
        "status": "P15_PHYSICAL_VIDEO_INDEX_COMPLETE",
        "eligible_contests": index.eligible_contests,
        "discovered_videos": index.discovered_videos,
        "mapped_contests": index.mapped_contests,
        "candidate_available_contests": index.candidate_available_contests,
        "accessible_contests": index.accessible_contests,
        "missing_contests": index.missing_contests,
        "ambiguous_contests": index.ambiguous_contests,
        "conflicting_contests": index.conflicting_contests,
        "coverage_ratio": index.coverage_ratio,
        "accessible_ratio": index.accessible_ratio,
        "exact_description_matches": index.exact_description_matches,
        "unique_title_date_matches": index.unique_title_date_matches,
        "official_channel_verified_videos": index.official_channel_verified_videos,
        "discovery_errors": list(index.discovery_errors),
        "predictive_evidence": index.predictive_evidence,
        "purchase_executed": index.purchase_executed,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))

    if index.coverage_ratio < args.min_coverage:
        print(
            f"P15_PHYSICAL_COVERAGE_BELOW_GATE:{index.coverage_ratio:.6f}<{args.min_coverage:.6f}",
            file=sys.stderr,
        )
        return 2
    if index.accessible_ratio < args.min_accessible_ratio:
        print(
            f"P15_PHYSICAL_ACCESSIBLE_BELOW_GATE:{index.accessible_ratio:.6f}<{args.min_accessible_ratio:.6f}",
            file=sys.stderr,
        )
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
