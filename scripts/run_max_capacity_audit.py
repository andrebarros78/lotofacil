from __future__ import annotations

import json
from pathlib import Path

from sare_lotofacil.analysis.capacity_audit import (
    run_real_training_audit,
    run_synthetic_capacity_audit,
)
from sare_lotofacil.persistence.repository import load_snapshot_records


def main() -> int:
    artifacts = Path("artifacts")
    history_report_path = artifacts / "third_party_history_report.json"
    db_path = artifacts / "real_history.db"
    if not history_report_path.exists() or not db_path.exists():
        raise RuntimeError("MAX_CAPACITY_AUDIT_REQUIRES_REAL_HISTORY_ARTIFACTS")

    history_report = json.loads(history_report_path.read_text(encoding="utf-8"))
    snapshot_id = str(history_report["snapshot_id"])
    records = load_snapshot_records(db_path, snapshot_id)
    draws = tuple(record.numbers for record in records)

    synthetic = run_synthetic_capacity_audit()
    real_training = run_real_training_audit(draws)
    result = {
        "status": "PASS" if synthetic["status"] == "PASS" else "FAIL",
        "snapshot_id": snapshot_id,
        "history_source_status": history_report["status"],
        "last_contest": history_report["last_contest"],
        "synthetic_qualification": synthetic,
        "real_history_training": real_training,
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": "EVIDENCIA_PREDITIVA_INSUFICIENTE",
    }
    output = artifacts / "max_capacity_audit.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
