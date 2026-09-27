from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = r"C:\Users\andre\P15Tools\ChromeP15CDPV3"
PORT = 9225


def wait_port(seconds: int = 20) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2):
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("CDP did not start")


def atomic_write(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def resolve(record: dict, candidates: list[dict]) -> dict:
    ok = [c for c in candidates if c.get("status") == "OK"]
    complete = [c for c in ok if c.get("complete_procedure")]
    result = {
        "contest_id": record["contest_id"],
        "draw_date": record.get("draw_date"),
        "input_candidate_count": len(record.get("candidate_video_ids", [])),
        "resolution_status": "NEEDS_VISUAL",
        "canonical_video_id": None,
        "supporting_complete_video_ids": [],
        "candidates": sorted(candidates, key=lambda c: (-c.get("score", -1), c.get("duration_seconds") or 10**9, c["video_id"])),
    }
    if complete:
        complete = sorted(complete, key=lambda c: (c.get("duration_seconds") or 10**9, -c.get("score", 0), c["video_id"]))
        result["canonical_video_id"] = complete[0]["video_id"]
        result["supporting_complete_video_ids"] = [c["video_id"] for c in complete]
        result["resolution_status"] = "RESOLVED_COMPLETE" if len(complete) == 1 else "RESOLVED_MULTIPLE_COMPLETE_CANONICAL_MINIMAL"
    else:
        strong = [c for c in ok if c.get("caption_contest") and c.get("caption_modality")]
        if len(strong) == 1:
            result["canonical_video_id"] = strong[0]["video_id"]
            result["resolution_status"] = "IDENTITY_RESOLVED_PROCEDURE_INCOMPLETE"
        elif not ok:
            result["resolution_status"] = "CONTENT_UNAVAILABLE"
    return result


def counts(records: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in records:
        s = r["resolution_status"]
        out[s] = out.get(s, 0) + 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--prior", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--helper", required=True)
    ap.add_argument("--timeout-seconds", type=int, default=50)
    ap.add_argument("--pause-seconds", type=float, default=3.0)
    args = ap.parse_args()

    queue = json.loads(Path(args.queue).read_text(encoding="utf-8"))
    prior = json.loads(Path(args.prior).read_text(encoding="utf-8"))
    prior_by = {r["contest_id"]: r for r in prior["records"]}
    pending_ids = {cid for cid, r in prior_by.items() if not r["resolution_status"].startswith("RESOLVED")}
    records = [r for r in queue["records"] if r["contest_id"] in pending_ids]

    out_path = Path(args.out)
    progress_path = out_path.with_suffix(out_path.suffix + ".progress")
    partial_path = out_path.with_suffix(out_path.suffix + ".partial")
    cache: dict[str, dict] = {}
    if progress_path.exists():
        try:
            cache = (json.loads(progress_path.read_text(encoding="utf-8")) or {}).get("candidates", {})
        except Exception:
            cache = {}

    chrome = subprocess.Popen([
        CHROME,
        "--headless=new",
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-debugging-address=127.0.0.1",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--user-data-dir={PROFILE}",
        "about:blank",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    completed_records: list[dict] = []
    started = time.time()
    try:
        wait_port()
        for rec in records:
            candidate_results: list[dict] = []
            for vid in rec.get("candidate_video_ids", []):
                key = f"{rec['contest_id']}:{vid}"
                if key in cache:
                    result = cache[key]
                else:
                    cmd = [
                        sys.executable,
                        args.helper,
                        str(PORT),
                        str(rec["contest_id"]),
                        rec.get("draw_date") or "",
                        vid,
                    ]
                    try:
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout_seconds)
                        lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
                        if lines:
                            result = json.loads(lines[-1])
                        else:
                            result = {
                                "contest_id": rec["contest_id"],
                                "draw_date": rec.get("draw_date"),
                                "video_id": vid,
                                "status": "ERROR",
                                "error": f"NO_JSON_OUTPUT rc={proc.returncode} stderr={proc.stderr[-800:]}",
                            }
                    except subprocess.TimeoutExpired:
                        result = {
                            "contest_id": rec["contest_id"],
                            "draw_date": rec.get("draw_date"),
                            "video_id": vid,
                            "status": "TIMEOUT",
                            "error": f"candidate exceeded {args.timeout_seconds}s",
                        }
                    except Exception as exc:
                        result = {
                            "contest_id": rec["contest_id"],
                            "draw_date": rec.get("draw_date"),
                            "video_id": vid,
                            "status": "ERROR",
                            "error": f"{type(exc).__name__}: {exc}"[:1000],
                        }
                    cache[key] = result
                    atomic_write(progress_path, {
                        "schema_version": 3,
                        "program_id": "P15_B2_CDP_PROGRESS_V3",
                        "candidates_completed": len(cache),
                        "candidates": cache,
                    })
                candidate_results.append(result)
                print(json.dumps({
                    "contest_id": rec["contest_id"],
                    "video_id": vid,
                    "status": result.get("status"),
                    "complete": result.get("complete_procedure"),
                    "score": result.get("score"),
                    "caption_format": result.get("caption_format"),
                    "error": result.get("error"),
                    "cached": key in cache,
                }, ensure_ascii=False), flush=True)
                time.sleep(max(0.2, args.pause_seconds))

            completed_records.append(resolve(rec, candidate_results))
            partial_payload = {
                "schema_version": 3,
                "program_id": "P15_B2_CDP_PENDING_RESOLVER_V3",
                "records_total": len(records),
                "records_completed": len(completed_records),
                "candidate_results_cached": len(cache),
                "resolution_counts": counts(completed_records),
                "predictive_evidence": "NOT_ESTABLISHED",
                "purchase_executed": False,
                "records": completed_records,
            }
            atomic_write(partial_path, partial_payload)
            print(json.dumps({
                "checkpoint": True,
                "records_completed": len(completed_records),
                "records_total": len(records),
                "resolution_counts": counts(completed_records),
            }, ensure_ascii=False), flush=True)

        final = {
            "schema_version": 3,
            "program_id": "P15_B2_CDP_PENDING_RESOLVER_V3",
            "records_total": len(records),
            "records_completed": len(completed_records),
            "candidate_results_cached": len(cache),
            "elapsed_seconds": round(time.time() - started, 3),
            "resolution_counts": counts(completed_records),
            "predictive_evidence": "NOT_ESTABLISHED",
            "purchase_executed": False,
            "records": completed_records,
        }
        atomic_write(out_path, final)
        print(json.dumps({
            "FINAL": True,
            "records_total": len(records),
            "candidate_results_cached": len(cache),
            "elapsed_seconds": final["elapsed_seconds"],
            "resolution_counts": final["resolution_counts"],
            "predictive_evidence": final["predictive_evidence"],
            "purchase_executed": final["purchase_executed"],
        }, ensure_ascii=False, indent=2), flush=True)
        return 0
    finally:
        try:
            chrome.terminate()
            chrome.wait(timeout=8)
        except Exception:
            try:
                chrome.kill()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
