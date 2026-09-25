from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

from sare_lotofacil.analysis.learning_ledger import build_learning_ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", default="operations")
    args = parser.parse_args()
    state_dir = Path(args.state_dir)
    reports = json.loads((state_dir / "post_contest_reports.json").read_text(encoding="utf-8"))
    ledger = build_learning_ledger(reports)

    # A post-contest report may intentionally have no hit count when no frozen
    # primary card existed before that draw. Such a report is still part of the
    # audit trail, but it is not an evaluable learning observation and the
    # learning ledger correctly skips it. Coverage must therefore be checked
    # against evaluable reports rather than against the total audit report count.
    evaluable_report_count = sum(
        1
        for report in reports.get("reports", [])
        if isinstance(report, Mapping) and isinstance(report.get("hits"), int)
    )
    if ledger["entry_count"] != evaluable_report_count:
        raise RuntimeError("LEARNING_LEDGER_REPORT_COVERAGE_MISMATCH")

    latest_report = next(
        (
            report
            for report in reversed(reports.get("reports", []))
            if isinstance(report, Mapping) and isinstance(report.get("hits"), int)
        ),
        None,
    )
    latest_evaluable_contest = int(latest_report["contest_number"]) if latest_report is not None else None
    latest_entry = ledger.get("latest_entry")
    if latest_evaluable_contest is not None and (
        not latest_entry or int(latest_entry["contest_number"]) != latest_evaluable_contest
    ):
        raise RuntimeError("LEARNING_LEDGER_LATEST_CONTEST_MISMATCH")

    (state_dir / "learning_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "LEARNING_LEDGER_PASS",
        "entry_count": ledger["entry_count"],
        "evaluable_report_count": evaluable_report_count,
        "latest_contest": latest_entry["contest_number"] if latest_entry else None,
        "latest_gap_to_15": latest_entry["gap_to_15"] if latest_entry else None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
