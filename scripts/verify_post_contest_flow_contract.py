from __future__ import annotations

import argparse
import json
from pathlib import Path


def verify_contract(state_dir: Path) -> dict[str, object]:
    latest = json.loads((state_dir / "latest.json").read_text(encoding="utf-8"))
    reports = json.loads((state_dir / "post_contest_reports.json").read_text(encoding="utf-8"))
    latest_report = json.loads((state_dir / "latest_post_contest_report.json").read_text(encoding="utf-8"))
    ledger = json.loads((state_dir / "prospective_ledger.json").read_text(encoding="utf-8"))
    markdown = (state_dir / "latest_post_contest_report.md").read_text(encoding="utf-8")

    official = int(latest["official_latest_contest"])
    report_contest = int(latest_report["contest_number"])
    if report_contest != official:
        raise RuntimeError(f"POST_CONTEST_FLOW_REPORT_NOT_LATEST:{report_contest}!={official}")
    if int(reports.get("latest_contest", 0)) != official:
        raise RuntimeError("POST_CONTEST_FLOW_REPORT_INDEX_NOT_LATEST")

    prediction = next(
        (item for item in ledger.get("predictions", []) if int(item.get("target_contest", 0)) == official),
        None,
    )
    if not isinstance(prediction, dict):
        raise RuntimeError("POST_CONTEST_FLOW_FROZEN_PREDICTION_MISSING")
    if not isinstance(prediction.get("evaluation"), dict):
        raise RuntimeError("POST_CONTEST_FLOW_AUDIT_MISSING")

    analysis = latest_report.get("self_analysis")
    if not isinstance(analysis, dict):
        raise RuntimeError("POST_CONTEST_FLOW_ANALYSIS_MISSING")
    required = ("process_findings", "corrections_required", "adjustments_suggested", "implementations_suggested")
    for field in required:
        value = analysis.get(field)
        if not isinstance(value, list) or not value:
            raise RuntimeError(f"POST_CONTEST_FLOW_{field.upper()}_MISSING")

    if f"Concurso Número: {official}" not in markdown:
        raise RuntimeError("POST_CONTEST_FLOW_DELIVERY_MARKDOWN_MISMATCH")

    emitted = latest.get("post_contest_report", {}).get("emitted_for_contests", [])
    inserted = latest.get("inserted_official_contests", [])
    missing_emission = sorted(set(int(x) for x in inserted) - set(int(x) for x in emitted))
    if missing_emission:
        raise RuntimeError(f"POST_CONTEST_FLOW_INSERTED_WITHOUT_REPORT:{missing_emission}")

    return {
        "status": "POST_CONTEST_FLOW_CONTRACT_PASS",
        "official_latest_contest": official,
        "audited": True,
        "report_persisted": True,
        "report_deliverable": True,
        "analysis_present": True,
        "improvement_suggestions_present": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = verify_contract(Path(args.state_dir))
    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
