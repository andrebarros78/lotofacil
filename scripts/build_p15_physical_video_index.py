from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

from sare_lotofacil.physical.video_index import (
    LOTTERY_TITLE_RE,
    TITLE_DATE_RE,
    VideoMetadata,
    build_video_index,
    load_canonical_history,
    load_jsonl_metadata,
)

DEFAULT_CHANNEL_SEARCH_URL = "https://www.youtube.com/user/canalcaixa/search?query=Loterias%20CAIXA"
DEFAULT_CHANNEL_VIDEOS_URL = "https://www.youtube.com/user/canalcaixa/videos"


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
    completed = _run(command, timeout_seconds=timeout_seconds)
    errors: list[str] = []
    if completed.returncode != 0:
        errors.append(f"FLAT_DISCOVERY_EXIT_{completed.returncode}:{completed.stderr[-2000:]}")

    entries: list[dict[str, object]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("id"):
            entries.append(payload)
    return entries, errors


def _looks_like_lottery_video(payload: dict[str, object]) -> bool:
    title = str(payload.get("title") or "")
    return bool(LOTTERY_TITLE_RE.search(title) and TITLE_DATE_RE.search(title))


def _hydrate_metadata(
    yt_dlp_bin: str,
    video_ids: Iterable[str],
    *,
    timeout_seconds: int,
) -> tuple[tuple[VideoMetadata, ...], list[str]]:
    ids = tuple(dict.fromkeys(str(value).strip() for value in video_ids if str(value).strip()))
    if not ids:
        return (), ["NO_CANDIDATE_VIDEO_IDS"]

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
        completed = _run(command, timeout_seconds=timeout_seconds)
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
    playlist_end: int,
    timeout_seconds: int,
) -> tuple[tuple[VideoMetadata, ...], tuple[str, ...]]:
    flat_entries, errors = _flat_discover(
        yt_dlp_bin,
        source_url,
        playlist_end=playlist_end,
        timeout_seconds=timeout_seconds,
    )
    candidate_ids = [str(entry["id"]) for entry in flat_entries if _looks_like_lottery_video(entry)]

    # Some yt-dlp/YouTube combinations do not expose channel search pages. In that
    # case inspect the channel upload list and still hydrate only lottery videos.
    if not candidate_ids:
        errors.append("PRIMARY_CHANNEL_SEARCH_EMPTY_USING_CHANNEL_VIDEOS_FALLBACK")
        fallback_entries, fallback_errors = _flat_discover(
            yt_dlp_bin,
            fallback_url,
            playlist_end=playlist_end,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(fallback_errors)
        candidate_ids = [
            str(entry["id"]) for entry in fallback_entries if _looks_like_lottery_video(entry)
        ]

    videos, hydrate_errors = _hydrate_metadata(
        yt_dlp_bin,
        candidate_ids,
        timeout_seconds=timeout_seconds,
    )
    errors.extend(hydrate_errors)
    return videos, tuple(errors)


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
    parser.add_argument("--first-contest", type=int, default=1874)
    parser.add_argument("--playlist-end", type=int, default=10000)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--min-coverage", type=float, default=0.0)
    args = parser.parse_args()

    history = load_canonical_history(args.history)
    if args.metadata_jsonl is not None:
        videos = load_jsonl_metadata(args.metadata_jsonl)
        errors: tuple[str, ...] = ()
        source_url = "FILE_SUPPLIED_METADATA"
    else:
        videos, errors = discover_official_metadata(
            yt_dlp_bin=args.yt_dlp_bin,
            source_url=args.channel_url,
            fallback_url=args.fallback_channel_url,
            playlist_end=args.playlist_end,
            timeout_seconds=args.timeout_seconds,
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
        "missing_contests": index.missing_contests,
        "conflicting_contests": index.conflicting_contests,
        "coverage_ratio": index.coverage_ratio,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
