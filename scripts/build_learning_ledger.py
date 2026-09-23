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
    if ledger["entry_count"] != reports.get("report_count"):
        raise RuntimeError("LEARNING_LEDGER_REPORT_COVERAGE_MISMATCH")
    latest_report = reports.get("latest_contest")
    latest_entry = ledger.get("latest_entry")
    if latest_report is not None and (not latest_entry or int(latest_entry["contest_number"]) != int(latest_report)):
        raise RuntimeError("LEARNING_LEDGER_LATEST_CONTEST_MISMATCH")
    (state_dir / "learning_ledger.json").write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": "LEARNING_LEDGER_PASS",
        "entry_count": ledger["entry_count"],
        "latest_contest": latest_entry["contest_number"] if latest_entry else None,
        "latest_gap_to_15": latest_entry["gap_to_15"] if latest_entry else None,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
