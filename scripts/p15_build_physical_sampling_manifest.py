from __future__ import annotations

import argparse
import json
from pathlib import Path

KEY_MARKERS = (
    "procedure",
    "maleta",
    "lacre",
    "auditor",
    "balls_25",
    "loading",
    "globo",
    "empty_globe",
)


def canonical_candidate(record: dict) -> dict:
    vid = record.get("canonical_video_id")
    for cand in record.get("candidates", []):
        if cand.get("video_id") == vid:
            return cand
    raise ValueError(f"canonical candidate not found for contest {record.get('contest_id')}: {vid}")


def clip_ms(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, int(value)))


def unique_samples(points: list[tuple[int, str]], min_gap_ms: int = 1200) -> list[dict]:
    points = sorted((max(0, int(ms)), reason) for ms, reason in points)
    out: list[dict] = []
    for ms, reason in points:
        if out and abs(ms - out[-1]["timestamp_ms"]) < min_gap_ms:
            if reason not in out[-1]["reasons"]:
                out[-1]["reasons"].append(reason)
            continue
        out.append({"timestamp_ms": ms, "reasons": [reason]})
    return out


def build_record(record: dict, pre_ms: int, post_ms: int) -> dict:
    cand = canonical_candidate(record)
    duration_ms = max(0, int(float(cand.get("duration_seconds") or 0) * 1000))
    markers = {
        key: int(value)
        for key, value in (cand.get("procedure_markers_ms") or {}).items()
        if value is not None
    }
    anchor = cand.get("contest_anchor_ms")
    relevant = list(markers.values())
    if anchor is not None:
        relevant.append(int(anchor))
    if not relevant:
        start_ms, end_ms = 0, duration_ms
    else:
        start_ms = clip_ms(min(relevant) - pre_ms, 0, duration_ms)
        end_ms = clip_ms(max(relevant) + post_ms, 0, duration_ms)
        if end_ms <= start_ms:
            end_ms = min(duration_ms, start_ms + 120_000)

    samples: list[tuple[int, str]] = [
        (start_ms, "TARGET_WINDOW_START"),
        (end_ms, "TARGET_WINDOW_END"),
    ]
    if anchor is not None:
        samples.extend([
            (clip_ms(int(anchor) - 3000, start_ms, end_ms), "CONTEST_ANCHOR_PRE_3S"),
            (clip_ms(int(anchor), start_ms, end_ms), "CONTEST_ANCHOR"),
            (clip_ms(int(anchor) + 3000, start_ms, end_ms), "CONTEST_ANCHOR_POST_3S"),
        ])
    for key in KEY_MARKERS:
        if key not in markers:
            continue
        ms = markers[key]
        samples.extend([
            (clip_ms(ms - 2500, start_ms, end_ms), f"{key.upper()}_PRE_2_5S"),
            (clip_ms(ms, start_ms, end_ms), key.upper()),
            (clip_ms(ms + 2500, start_ms, end_ms), f"{key.upper()}_POST_2_5S"),
        ])

    # Coverage points prevent a long gap between markers from being visually invisible.
    cursor = start_ms + 30_000
    while cursor < end_ms:
        samples.append((cursor, "WINDOW_COVERAGE_30S"))
        cursor += 30_000

    sampling = unique_samples(samples)
    return {
        "contest_id": record["contest_id"],
        "draw_date": record.get("draw_date"),
        "canonical_video_id": record.get("canonical_video_id"),
        "canonical_url": cand.get("url") or f"https://www.youtube.com/watch?v={record.get('canonical_video_id')}",
        "resolution_status": record.get("resolution_status"),
        "resolution_source": record.get("resolution_source"),
        "source_channel": cand.get("channel"),
        "source_title": cand.get("title"),
        "upload_date": cand.get("upload_date"),
        "duration_ms": duration_ms,
        "contest_anchor_ms": int(anchor) if anchor is not None else None,
        "procedure_markers_ms": markers,
        "target_window": {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_ms": max(0, end_ms - start_ms),
        },
        "sampling_points": sampling,
        "physical_features": {
            "procedure_start_ms": markers.get("procedure"),
            "maleta_event_ms": markers.get("maleta"),
            "lacre_event_ms": markers.get("lacre"),
            "auditor_event_ms": markers.get("auditor"),
            "balls_25_event_ms": markers.get("balls_25"),
            "loading_event_ms": markers.get("loading"),
            "globe_event_ms": markers.get("globo"),
            "empty_globe_event_ms": markers.get("empty_globe"),
            "globe_number": None,
            "case_or_maleta_id": None,
            "ball_set_id": None,
            "loading_sequence": None,
            "draw_sequence": None,
            "interventions": None,
            "visual_fingerprint": None,
            "status": "TARGET_WINDOW_READY_VISUAL_EXTRACTION_PENDING",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--features-out", required=True)
    ap.add_argument("--sampling-out", required=True)
    ap.add_argument("--pre-seconds", type=float, default=45.0)
    ap.add_argument("--post-seconds", type=float, default=90.0)
    args = ap.parse_args()

    source = json.loads(Path(args.input).read_text(encoding="utf-8"))
    records = source.get("records", [])
    built = [
        build_record(rec, int(args.pre_seconds * 1000), int(args.post_seconds * 1000))
        for rec in records
    ]

    full_ms = sum(r["duration_ms"] for r in built)
    target_ms = sum(r["target_window"]["duration_ms"] for r in built)
    samples = sum(len(r["sampling_points"]) for r in built)
    reduction = (1.0 - (target_ms / full_ms)) if full_ms else 0.0

    common = {
        "schema_version": 1,
        "program_id": "P15_PHYSICAL_FEATURE_SAMPLING_MANIFEST_V1",
        "records_total": len(built),
        "full_video_seconds_total": round(full_ms / 1000.0, 3),
        "target_window_seconds_total": round(target_ms / 1000.0, 3),
        "time_reduction_ratio": round(reduction, 6),
        "sampling_points_total": samples,
        "predictive_evidence": "NOT_ESTABLISHED",
        "purchase_executed": False,
    }

    features_payload = dict(common)
    features_payload["records"] = built
    Path(args.features_out).write_text(
        json.dumps(features_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    sampling_payload = dict(common)
    sampling_payload["records"] = [
        {
            "contest_id": r["contest_id"],
            "draw_date": r["draw_date"],
            "canonical_video_id": r["canonical_video_id"],
            "canonical_url": r["canonical_url"],
            "target_window": r["target_window"],
            "sampling_points": r["sampling_points"],
        }
        for r in built
    ]
    Path(args.sampling_out).write_text(
        json.dumps(sampling_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print(json.dumps(common, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
