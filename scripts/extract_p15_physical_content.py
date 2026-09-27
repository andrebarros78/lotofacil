from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Iterable

from sare_lotofacil.physical.content_features import (
    PhysicalObservation,
    ProcedureAssessment,
    assess_procedure,
    observation_from_assessment,
    parse_webvtt,
)
from sare_lotofacil.physical.content_resolution import (
    ContentResolutionDecision,
    apply_content_decisions,
    decide_ambiguous_content,
)
from sare_lotofacil.physical.frame_features import average_hash_gray


class ProbeResult:
    __slots__ = ("video_id", "status", "cues", "error_code")

    def __init__(self, video_id: str, status: str, cues=(), error_code: str | None = None):
        self.video_id = video_id
        self.status = status
        self.cues = tuple(cues)
        self.error_code = error_code


def _run(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        timeout=timeout_seconds,
        env=env,
    )


def _error_code(stderr: bytes, *, timed_out: bool = False) -> str:
    if timed_out:
        return "TIMEOUT"
    text = stderr.decode("utf-8", errors="replace").lower()
    if "confirm you're not a bot" in text or "confirm you’re not a bot" in text:
        return "YOUTUBE_BOT_GATE"
    if "video unavailable" in text or "not available" in text:
        return "VIDEO_UNAVAILABLE"
    if "subtitles" in text and "not available" in text:
        return "SUBTITLES_UNAVAILABLE"
    if "http error 429" in text or "too many requests" in text:
        return "RATE_LIMIT"
    return "PUBLIC_CONTENT_UNAVAILABLE"


def _probe_timed_text(
    *,
    video_id: str,
    video_url: str,
    yt_dlp_bin: str,
    timeout_seconds: int,
) -> ProbeResult:
    with tempfile.TemporaryDirectory(prefix="p15-vtt-") as temp_dir:
        out_template = str(Path(temp_dir) / "%(id)s.%(ext)s")
        command = [
            yt_dlp_bin,
            "--ignore-errors",
            "--no-warnings",
            "--socket-timeout",
            "10",
            "--retries",
            "1",
            "--extractor-retries",
            "1",
            "--skip-download",
            "--write-subs",
            "--write-auto-subs",
            "--sub-langs",
            "pt.*,pt-BR,pt,en.*",
            "--sub-format",
            "vtt",
            "--output",
            out_template,
            video_url,
        ]
        try:
            completed = _run(command, timeout_seconds=timeout_seconds)
        except subprocess.TimeoutExpired:
            return ProbeResult(video_id, "CONTENT_UNAVAILABLE", error_code="TIMEOUT")

        vtt_files = sorted(Path(temp_dir).glob(f"{video_id}*.vtt"))
        best_cues = ()
        for path in vtt_files:
            try:
                cues = parse_webvtt(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if len(cues) > len(best_cues):
                best_cues = cues
        if best_cues:
            return ProbeResult(video_id, "TIMED_TEXT_AVAILABLE", cues=best_cues)
        return ProbeResult(
            video_id,
            "CONTENT_UNAVAILABLE",
            error_code=_error_code(completed.stderr),
        )


def _select_jobs(index_payload: dict[str, object], *, mapped_limit: int) -> tuple[dict[str, str], list[dict[str, object]]]:
    raw_records = index_payload.get("records")
    if not isinstance(raw_records, list):
        raise RuntimeError("P15_CONTENT_INDEX_RECORDS_MISSING")

    urls: dict[str, str] = {}
    mapped: list[dict[str, object]] = []
    for raw in raw_records:
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("mapping_status") or "")
        if status == "AMBIGUOUS":
            ids = [str(value) for value in raw.get("candidate_video_ids") or []]
            candidate_urls = [str(value) for value in raw.get("candidate_video_urls") or []]
            for position, video_id in enumerate(ids):
                if position < len(candidate_urls) and candidate_urls[position]:
                    urls.setdefault(video_id, candidate_urls[position])
        elif status == "MAPPED" and raw.get("video_id") and raw.get("video_url"):
            mapped.append(raw)

    mapped.sort(key=lambda item: int(item.get("contest_id") or 0), reverse=True)
    if mapped_limit >= 0:
        mapped = mapped[:mapped_limit]
    for raw in mapped:
        urls.setdefault(str(raw["video_id"]), str(raw["video_url"]))
    return urls, mapped


def _probe_many(
    urls: dict[str, str],
    *,
    yt_dlp_bin: str,
    timeout_seconds: int,
    max_workers: int,
) -> dict[str, ProbeResult]:
    results: dict[str, ProbeResult] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _probe_timed_text,
                video_id=video_id,
                video_url=url,
                yt_dlp_bin=yt_dlp_bin,
                timeout_seconds=timeout_seconds,
            ): video_id
            for video_id, url in urls.items()
        }
        for future in concurrent.futures.as_completed(futures):
            video_id = futures[future]
            try:
                results[video_id] = future.result()
            except Exception:  # noqa: BLE001 - evidence records failure without leaking raw process text
                results[video_id] = ProbeResult(video_id, "CONTENT_UNAVAILABLE", error_code="PROBE_EXCEPTION")
    return results


def _content_decisions(
    index_payload: dict[str, object],
    probes: dict[str, ProbeResult],
) -> tuple[list[ContentResolutionDecision], dict[tuple[int, str], ProcedureAssessment]]:
    assessments: dict[tuple[int, str], ProcedureAssessment] = {}
    decisions: list[ContentResolutionDecision] = []
    raw_records = index_payload.get("records")
    assert isinstance(raw_records, list)
    for raw in raw_records:
        if not isinstance(raw, dict) or raw.get("mapping_status") != "AMBIGUOUS":
            continue
        contest_id = int(raw["contest_id"])
        by_video: dict[str, ProcedureAssessment] = {}
        for video_id in [str(value) for value in raw.get("candidate_video_ids") or []]:
            probe = probes.get(video_id)
            if probe is None or not probe.cues:
                continue
            assessment = assess_procedure(probe.cues, contest_id=contest_id, expected_numbers=None)
            assessments[(contest_id, video_id)] = assessment
            by_video[video_id] = assessment
        decisions.append(
            decide_ambiguous_content(
                contest_id=contest_id,
                candidate_video_ids=[str(value) for value in raw.get("candidate_video_ids") or []],
                assessments_by_video=by_video,
                minimum_margin=20,
            )
        )
    return decisions, assessments


def _record_by_contest(index_payload: dict[str, object]) -> dict[int, dict[str, object]]:
    raw_records = index_payload.get("records")
    assert isinstance(raw_records, list)
    return {
        int(raw["contest_id"]): raw
        for raw in raw_records
        if isinstance(raw, dict)
    }


def _build_observations(
    resolved_index: dict[str, object],
    original_mapped: Iterable[dict[str, object]],
    probes: dict[str, ProbeResult],
    decisions: Iterable[ContentResolutionDecision],
) -> list[PhysicalObservation]:
    selected_contests = {int(raw["contest_id"]) for raw in original_mapped}
    selected_contests.update(
        decision.contest_id
        for decision in decisions
        if decision.status == "RESOLVED_BY_CONTENT"
    )
    by_contest = _record_by_contest(resolved_index)
    observations: list[PhysicalObservation] = []
    for contest_id in sorted(selected_contests):
        record = by_contest.get(contest_id)
        if not record or record.get("mapping_status") != "MAPPED" or not record.get("video_id"):
            continue
        video_id = str(record["video_id"])
        probe = probes.get(video_id)
        if probe is None or not probe.cues:
            observations.append(
                PhysicalObservation(
                    contest_id=contest_id,
                    video_id=video_id,
                    content_status=(probe.error_code if probe else "NOT_PROBED"),
                    complete_procedure=False,
                    segment_start_seconds=None,
                    segment_end_seconds=None,
                    segment_duration_seconds=None,
                    case_open_seconds=None,
                    ball_check_seconds=None,
                    globe_load_seconds=None,
                    mixing_start_seconds=None,
                    draw_start_seconds=None,
                    draw_end_seconds=None,
                    globe_empty_seconds=None,
                    case_close_seconds=None,
                    mixing_duration_seconds=None,
                    draw_duration_seconds=None,
                    draw_sequence=None,
                    draw_sequence_status="NOT_EXTRACTED",
                    intervention_flags=(),
                    procedure_markers=(),
                    visual_feature_status="CONTENT_NOT_AVAILABLE_FOR_FRAME_TARGETING",
                )
            )
            continue
        expected = [int(value) for value in record.get("numbers") or []]
        assessment = assess_procedure(
            probe.cues,
            contest_id=contest_id,
            expected_numbers=expected,
        )
        observations.append(
            observation_from_assessment(
                contest_id=contest_id,
                video_id=video_id,
                assessment=assessment,
            )
        )
    return observations


def _extract_gray_frame(
    *,
    ffmpeg_bin: str,
    clip_path: Path,
    offset_seconds: float,
    timeout_seconds: int,
) -> bytes | None:
    command = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{max(0.0, offset_seconds):.3f}",
        "-i",
        str(clip_path),
        "-frames:v",
        "1",
        "-vf",
        "scale=16:16,format=gray",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "gray",
        "pipe:1",
    ]
    try:
        completed = _run(command, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0 or len(completed.stdout) != 256:
        return None
    return completed.stdout


def _download_segment(
    *,
    yt_dlp_bin: str,
    video_url: str,
    start_seconds: float,
    end_seconds: float,
    output_dir: Path,
    timeout_seconds: int,
) -> Path | None:
    section_end = max(start_seconds + 20.0, min(end_seconds, start_seconds + 900.0))
    template = str(output_dir / "segment.%(ext)s")
    command = [
        yt_dlp_bin,
        "--ignore-errors",
        "--no-warnings",
        "--socket-timeout",
        "10",
        "--retries",
        "1",
        "--extractor-retries",
        "1",
        "--download-sections",
        f"*{start_seconds:.3f}-{section_end:.3f}",
        "-f",
        "worst[height<=360]/worst",
        "--output",
        template,
        video_url,
    ]
    try:
        completed = _run(command, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired:
        return None
    if completed.returncode != 0:
        return None
    files = [path for path in output_dir.glob("segment.*") if path.is_file()]
    return max(files, key=lambda path: path.stat().st_size) if files else None


def _add_visual_fingerprints(
    observations: list[PhysicalObservation],
    resolved_index: dict[str, object],
    *,
    yt_dlp_bin: str,
    ffmpeg_bin: str,
    limit: int,
    timeout_seconds: int,
) -> tuple[list[PhysicalObservation], int]:
    if limit <= 0 or shutil.which(ffmpeg_bin) is None:
        return observations, 0
    records = _record_by_contest(resolved_index)
    output: list[PhysicalObservation] = []
    sampled = 0
    for observation in observations:
        if (
            sampled >= limit
            or not observation.complete_procedure
            or observation.segment_start_seconds is None
            or observation.segment_end_seconds is None
        ):
            output.append(observation)
            continue
        record = records[observation.contest_id]
        video_url = str(record.get("video_url") or "")
        if not video_url:
            output.append(observation)
            continue
        with tempfile.TemporaryDirectory(prefix="p15-clip-") as temp_dir:
            clip = _download_segment(
                yt_dlp_bin=yt_dlp_bin,
                video_url=video_url,
                start_seconds=observation.segment_start_seconds,
                end_seconds=observation.segment_end_seconds,
                output_dir=Path(temp_dir),
                timeout_seconds=timeout_seconds,
            )
            if clip is None:
                output.append(replace(observation, visual_feature_status="VIDEO_SEGMENT_UNAVAILABLE"))
                continue

            def fingerprint_at(absolute_time: float | None) -> str | None:
                if absolute_time is None:
                    return None
                relative = absolute_time - observation.segment_start_seconds
                raw = _extract_gray_frame(
                    ffmpeg_bin=ffmpeg_bin,
                    clip_path=clip,
                    offset_seconds=relative,
                    timeout_seconds=30,
                )
                return average_hash_gray(raw).average_hash_hex if raw is not None else None

            case_hash = fingerprint_at(observation.case_open_seconds or observation.ball_check_seconds)
            ball_hash = fingerprint_at(observation.ball_check_seconds)
            globe_hash = fingerprint_at(observation.globe_load_seconds or observation.mixing_start_seconds)
            status = "VISUAL_CONTEXT_FINGERPRINTS_EXTRACTED" if any((case_hash, ball_hash, globe_hash)) else "FRAME_TARGETS_NOT_EXTRACTED"
            output.append(
                replace(
                    observation,
                    visual_case_fingerprint=case_hash,
                    visual_ball_set_fingerprint=ball_hash,
                    visual_globe_fingerprint=globe_hash,
                    visual_feature_status=status,
                )
            )
            sampled += 1
    return output, sampled


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve P15 video ambiguity by timed content and extract physical observations.")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--resolved-index-out", type=Path, required=True)
    parser.add_argument("--observations-out", type=Path, required=True)
    parser.add_argument("--diagnostics-out", type=Path, required=True)
    parser.add_argument("--yt-dlp-bin", default="yt-dlp")
    parser.add_argument("--ffmpeg-bin", default="ffmpeg")
    parser.add_argument("--per-video-timeout-seconds", type=int, default=45)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--mapped-limit", type=int, default=20)
    parser.add_argument("--visual-sample-limit", type=int, default=5)
    parser.add_argument("--visual-timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    index_payload = json.loads(args.index.read_text(encoding="utf-8"))
    if index_payload.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("P15_CONTENT_PREDICTIVE_EVIDENCE_GUARD_BROKEN")

    urls, mapped_sample = _select_jobs(index_payload, mapped_limit=args.mapped_limit)
    probes = _probe_many(
        urls,
        yt_dlp_bin=args.yt_dlp_bin,
        timeout_seconds=args.per_video_timeout_seconds,
        max_workers=max(1, args.max_workers),
    )
    decisions, _resolution_assessments = _content_decisions(index_payload, probes)
    resolved_index = apply_content_decisions(index_payload, decisions)
    observations = _build_observations(resolved_index, mapped_sample, probes, decisions)
    observations, visually_sampled = _add_visual_fingerprints(
        observations,
        resolved_index,
        yt_dlp_bin=args.yt_dlp_bin,
        ffmpeg_bin=args.ffmpeg_bin,
        limit=args.visual_sample_limit,
        timeout_seconds=args.visual_timeout_seconds,
    )

    args.resolved_index_out.write_text(
        json.dumps(resolved_index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    args.observations_out.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "program_id": "SARE-P15-PHYSICAL-CONTENT-V2",
                "observations": [item.to_dict() for item in observations],
                "predictive_evidence": "NOT_ESTABLISHED",
                "purchase_executed": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    error_counts: dict[str, int] = {}
    for probe in probes.values():
        if probe.error_code:
            error_counts[probe.error_code] = error_counts.get(probe.error_code, 0) + 1
    resolved_decisions = [item for item in decisions if item.status == "RESOLVED_BY_CONTENT"]
    diagnostics = {
        "status": "P15_PHYSICAL_CONTENT_EXTRACTION_COMPLETE",
        "candidate_and_sample_videos_probed": len(probes),
        "timed_text_available": sum(bool(item.cues) for item in probes.values()),
        "content_access_errors": error_counts,
        "ambiguous_before": int(index_payload.get("ambiguous_contests") or 0),
        "content_resolved": len(resolved_decisions),
        "ambiguous_after": int(resolved_index.get("ambiguous_contests") or 0),
        "mapped_sample_requested": args.mapped_limit,
        "observations_emitted": len(observations),
        "complete_procedure_observations": sum(item.complete_procedure for item in observations),
        "sequences_extracted": sum(item.draw_sequence is not None for item in observations),
        "intervention_flagged_observations": sum(bool(item.intervention_flags) for item in observations),
        "visual_segments_attempted": visually_sampled,
        "visual_fingerprints_emitted": sum(
            item.visual_feature_status == "VISUAL_CONTEXT_FINGERPRINTS_EXTRACTED"
            for item in observations
        ),
        "predictive_evidence": "NOT_ESTABLISHED",
        "purchase_executed": False,
        "decisions": [item.to_dict() for item in decisions],
    }
    args.diagnostics_out.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in diagnostics.items() if key != "decisions"}, indent=2, sort_keys=True))

    if resolved_index.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("P15_CONTENT_PREDICTIVE_EVIDENCE_MUTATED")
    if resolved_index.get("purchase_executed") is not False:
        raise RuntimeError("P15_CONTENT_PURCHASE_GUARD_BROKEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
