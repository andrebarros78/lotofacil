from __future__ import annotations

import argparse
import json
from pathlib import Path

from sare_lotofacil.analysis.learning_ledger import build_learning_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    args = parser.parse_args()
    state_dir = Path(args.state_dir)
    reports = json.loads((state_dir / "post_contest_reports.json").read_text(encoding="utf-8"))
    ledger = build_learning_ledger(reports)

    # A learning entry requires an actually frozen/evaluated card and therefore
    # integer hits. Process-gap reports (for example, no prospectively frozen
    # primary card) remain auditable inputs but cannot produce hit-based learning.
    evaluable_reports = [
        report
        for report in reports.get("reports", [])
        if isinstance(report, dict) and isinstance(report.get("hits"), int)
    ]
    if ledger["entry_count"] != len(evaluable_reports):
        raise RuntimeError("LEARNING_LEDGER_EVALUABLE_REPORT_COVERAGE_MISMATCH")

    latest_evaluable = evaluable_reports[-1] if evaluable_reports else None
    latest_entry = ledger.get("latest_entry")
    if latest_evaluable is not None and (
        not latest_entry
        or int(latest_entry["contest_number"]) != int(latest_evaluable["contest_number"])
    ):
        raise RuntimeError("LEARNING_LEDGER_LATEST_EVALUABLE_CONTEST_MISMATCH")

    (state_dir / "learning_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "LEARNING_LEDGER_PASS",
        "entry_count": ledger["entry_count"],
        "source_report_count": reports.get("report_count"),
        "evaluable_report_count": len(evaluable_reports),
        "latest_contest": latest_entry["contest_number"] if latest_entry else None,
        "latest_gap_to_15": latest_entry["gap_to_15"] if latest_entry else None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
