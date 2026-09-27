from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_p15_physical_video_index import _flat_discover_many, _flat_entry_to_public_video
from sare_lotofacil.physical.gap_recovery import (
    apply_gap_decisions,
    decide_remaining_gap,
    remaining_gap_searches,
)
from sare_lotofacil.physical.video_index import VideoMetadata


def _discover(
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
            playlist_end=5,
            timeout_seconds=timeout_seconds,
        )
        errors.extend(chunk_errors)
        for payload in entries:
            try:
                video = _flat_entry_to_public_video(payload)
            except ValueError:
                continue
            videos.setdefault(video.video_id, video)
    return tuple(videos[key] for key in sorted(videos)), tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description="Search remaining P15 video gaps with contest/date query variants.")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--diagnostics-out", type=Path, required=True)
    parser.add_argument("--yt-dlp-bin", default="yt-dlp")
    parser.add_argument("--timeout-seconds", type=int, default=360)
    parser.add_argument("--chunk-size", type=int, default=60)
    args = parser.parse_args()

    index_payload = json.loads(args.index.read_text(encoding="utf-8"))
    records = index_payload.get("records")
    if not isinstance(records, list):
        raise RuntimeError("P15_GAP_INDEX_RECORDS_MISSING")

    missing_records = [record for record in records if isinstance(record, dict) and record.get("mapping_status") == "MISSING"]
    searches = remaining_gap_searches(missing_records, results_per_query=5)
    videos, discovery_errors = _discover(
        yt_dlp_bin=args.yt_dlp_bin,
        searches=searches,
        timeout_seconds=args.timeout_seconds,
        chunk_size=max(1, args.chunk_size),
    )

    # Search result metadata is global; each missing contest is independently
    # scored under strict date/contest/channel rules. Query relevance alone is
    # never considered evidence.
    decisions = [decide_remaining_gap(record, videos) for record in missing_records]
    output = apply_gap_decisions(index_payload, decisions)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    recovered = sum(decision.status == "RECOVERED_STRICT" for decision in decisions)
    ambiguous = sum(decision.status == "GAP_AMBIGUOUS" for decision in decisions)
    diagnostics = {
        "status": "P15_REMAINING_GAP_RECOVERY_COMPLETE",
        "missing_before": len(missing_records),
        "queries": len(searches),
        "unique_videos_discovered": len(videos),
        "recovered_strict": recovered,
        "new_ambiguous": ambiguous,
        "still_missing": int(output.get("missing_contests") or 0),
        "mapped_after": int(output.get("mapped_contests") or 0),
        "ambiguous_after": int(output.get("ambiguous_contests") or 0),
        "discovery_error_count": len(discovery_errors),
        "decisions": [decision.to_dict() for decision in decisions],
        "predictive_evidence": "NOT_ESTABLISHED",
        "purchase_executed": False,
    }
    args.diagnostics_out.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in diagnostics.items() if key != "decisions"}, indent=2, sort_keys=True))

    if output.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("P15_GAP_PREDICTIVE_EVIDENCE_GUARD_BROKEN")
    if output.get("purchase_executed") is not False:
        raise RuntimeError("P15_GAP_PURCHASE_GUARD_BROKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
