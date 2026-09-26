from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_p15_physical_video_index import (
    DEFAULT_CHANNEL_SEARCH_URL,
    DEFAULT_CHANNEL_STREAMS_URL,
    DEFAULT_CHANNEL_VIDEOS_URL,
    DEFAULT_CHANNEL_BASE_URL,
    _flat_discover_many,
    _flat_entry_to_public_video,
    discover_public_broadcast_metadata,
    monthly_channel_search_urls,
    monthly_historical_broadcast_searches,
    monthly_public_archive_searches,
)
from sare_lotofacil.physical.targeted_recovery import (
    resolve_ambiguities_strict,
    targeted_searches,
)
from sare_lotofacil.physical.video_index import (
    LOTTERY_TITLE_RE,
    LOTOFACIL_TITLE_RE,
    VideoMetadata,
    build_video_index,
    load_canonical_history,
)


def _merge_videos(*groups: tuple[VideoMetadata, ...]) -> tuple[VideoMetadata, ...]:
    by_id: dict[str, VideoMetadata] = {}
    for group in groups:
        for video in group:
            previous = by_id.get(video.video_id)
            if previous is None:
                by_id[video.video_id] = video
                continue
            prev_richness = (bool(previous.description), bool(previous.duration), len(previous.title))
            new_richness = (bool(video.description), bool(video.duration), len(video.title))
            if new_richness > prev_richness:
                by_id[video.video_id] = video
    return tuple(by_id[key] for key in sorted(by_id))


def _targeted_discover(
    *,
    yt_dlp_bin: str,
    searches: tuple[str, ...],
    timeout_seconds: int,
    chunk_size: int,
) -> tuple[tuple[VideoMetadata, ...], tuple[str, ...]]:
    videos: dict[str, VideoMetadata] = {}
    errors: list[str] = []
    for start in range(0, len(searches), chunk_size):
        chunk = searches[start : start + chunk_size]
        entries, chunk_errors = _flat_discover_many(
            yt_dlp_bin,
            chunk,
            playlist_end=3,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(chunk_errors)
        for payload in entries:
            title = str(payload.get("title") or "")
            if not (LOTTERY_TITLE_RE.search(title) or LOTOFACIL_TITLE_RE.search(title)):
                continue
            try:
                video = _flat_entry_to_public_video(payload)
            except ValueError:
                continue
            videos.setdefault(video.video_id, video)
    return tuple(videos[key] for key in sorted(videos)), tuple(errors)


def _summary(index, *, stages: dict[str, object]) -> dict[str, object]:
    return {
        "status": "P15_PHYSICAL_TARGETED_RECOVERY_COMPLETE",
        "eligible_contests": index.eligible_contests,
        "discovered_videos": index.discovered_videos,
        "mapped_contests": index.mapped_contests,
        "accessible_contests": index.accessible_contests,
        "missing_contests": index.missing_contests,
        "ambiguous_contests": index.ambiguous_contests,
        "conflicting_contests": index.conflicting_contests,
        "coverage_ratio": index.coverage_ratio,
        "accessible_ratio": index.accessible_ratio,
        "predictive_evidence": index.predictive_evidence,
        "purchase_executed": index.purchase_executed,
        "stages": stages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover P15 physical archive gaps by exact contest+date searches.")
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--diagnostics-out", type=Path, required=True)
    parser.add_argument("--yt-dlp-bin", default="yt-dlp")
    parser.add_argument("--first-contest", type=int, default=1874)
    parser.add_argument("--playlist-end", type=int, default=12000)
    parser.add_argument("--timeout-seconds", type=int, default=1200)
    parser.add_argument("--targeted-timeout-seconds", type=int, default=360)
    parser.add_argument("--targeted-chunk-size", type=int, default=80)
    args = parser.parse_args()

    history = load_canonical_history(args.history)
    eligible = tuple(item for item in history if item.contest_id >= args.first_contest)
    if not eligible:
        raise RuntimeError("P15_PHYSICAL_NO_ELIGIBLE_HISTORY")

    first_date = eligible[0].draw_date
    last_date = eligible[-1].draw_date
    broad_videos, broad_errors = discover_public_broadcast_metadata(
        yt_dlp_bin=args.yt_dlp_bin,
        source_url=DEFAULT_CHANNEL_SEARCH_URL,
        fallback_url=DEFAULT_CHANNEL_VIDEOS_URL,
        streams_url=DEFAULT_CHANNEL_STREAMS_URL,
        shard_urls=monthly_channel_search_urls(first_date, last_date, channel_base_url=DEFAULT_CHANNEL_BASE_URL),
        public_searches=monthly_public_archive_searches(first_date, last_date),
        historical_searches=monthly_historical_broadcast_searches(first_date, last_date),
        playlist_end=args.playlist_end,
        timeout_seconds=args.timeout_seconds,
        hydrate_limit=0,
    )

    first_index = build_video_index(
        history,
        broad_videos,
        first_eligible_contest=args.first_contest,
        source_channel_url=DEFAULT_CHANNEL_SEARCH_URL,
        discovery_errors=broad_errors,
    )

    missing_searches = targeted_searches(
        first_index.records,
        statuses=frozenset({"MISSING"}),
        results_per_contest=3,
    )
    missing_videos, missing_errors = _targeted_discover(
        yt_dlp_bin=args.yt_dlp_bin,
        searches=missing_searches,
        timeout_seconds=args.targeted_timeout_seconds,
        chunk_size=args.targeted_chunk_size,
    )
    after_missing_videos = _merge_videos(broad_videos, missing_videos)
    after_missing_index = build_video_index(
        history,
        after_missing_videos,
        first_eligible_contest=args.first_contest,
        source_channel_url=DEFAULT_CHANNEL_SEARCH_URL,
        discovery_errors=(*broad_errors, *missing_errors),
    )

    ambiguity_searches = targeted_searches(
        after_missing_index.records,
        statuses=frozenset({"AMBIGUOUS"}),
        results_per_contest=3,
    )
    ambiguity_videos, ambiguity_errors = _targeted_discover(
        yt_dlp_bin=args.yt_dlp_bin,
        searches=ambiguity_searches,
        timeout_seconds=args.targeted_timeout_seconds,
        chunk_size=args.targeted_chunk_size,
    )
    all_videos = _merge_videos(after_missing_videos, ambiguity_videos)
    before_strict = build_video_index(
        history,
        all_videos,
        first_eligible_contest=args.first_contest,
        source_channel_url=DEFAULT_CHANNEL_SEARCH_URL,
        discovery_errors=(*broad_errors, *missing_errors, *ambiguity_errors),
    )
    final_index, strict_diag = resolve_ambiguities_strict(
        before_strict,
        {video.video_id: video for video in all_videos},
    )

    stages = {
        "first_pass": {
            "mapped": first_index.mapped_contests,
            "missing": first_index.missing_contests,
            "ambiguous": first_index.ambiguous_contests,
            "accessible": first_index.accessible_contests,
        },
        "missing_directed_pass": {
            "queries": len(missing_searches),
            "new_videos": len(missing_videos),
            "mapped": after_missing_index.mapped_contests,
            "missing": after_missing_index.missing_contests,
            "ambiguous": after_missing_index.ambiguous_contests,
        },
        "ambiguity_directed_pass": {
            "queries": len(ambiguity_searches),
            "new_videos": len(ambiguity_videos),
            "mapped_before_strict": before_strict.mapped_contests,
            "ambiguous_before_strict": before_strict.ambiguous_contests,
        },
        "strict_metadata_resolution": {
            "targeted_records": strict_diag.targeted_records,
            "resolved": strict_diag.resolved_ambiguities,
            "unresolved": strict_diag.unresolved_ambiguities,
        },
    }

    args.out.write_text(
        json.dumps(final_index.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    diagnostics = _summary(final_index, stages=stages)
    args.diagnostics_out.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True))

    if final_index.predictive_evidence != "NOT_ESTABLISHED":
        raise RuntimeError("P15_PHYSICAL_PREDICTIVE_EVIDENCE_GUARD_BROKEN")
    if final_index.purchase_executed:
        raise RuntimeError("P15_PHYSICAL_PURCHASE_GUARD_BROKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
