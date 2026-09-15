from __future__ import annotations

import json
from pathlib import Path

from sare_lotofacil.analysis.calibration_rounds import run_calibration_error_rounds
from sare_lotofacil.analysis.capacity_audit import (
    run_parameter_training_audit,
    run_real_training_audit,
    run_synthetic_capacity_audit,
)
from sare_lotofacil.analysis.portfolio_audit import run_primary_tiebreak_audit
from sare_lotofacil.domain.rules import special_prize_ruleset_for_contest
from sare_lotofacil.persistence.repository import load_snapshot_records


def _special_3780_audit() -> dict[str, object]:
    rules = special_prize_ruleset_for_contest(3780)
    if rules is None:
        return {"status": "FAIL", "reason": "SPECIAL_RULESET_3780_MISSING"}
    expected = {
        "fixed_prize_cents_by_hits": [[11, 350], [12, 700], [13, 1750]],
        "variable_share_bps_by_hits": [[14, 1300], [15, 8700]],
        "non_accumulating": True,
    }
    actual = {
        "fixed_prize_cents_by_hits": [list(item) for item in rules.fixed_prize_cents_by_hits],
        "variable_share_bps_by_hits": [list(item) for item in rules.variable_share_bps_by_hits],
        "non_accumulating": rules.non_accumulating,
    }
    return {
        "status": "PASS" if actual == expected else "FAIL",
        "contest_id": rules.contest_id,
        "ruleset_id": rules.ruleset_id,
        "actual": actual,
        "expected": expected,
        "source_url": rules.source_url,
    }


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
    parameter_training = run_parameter_training_audit(draws)
    calibration_error_20_rounds = run_calibration_error_rounds(draws, rounds=20)
    primary_tiebreak = run_primary_tiebreak_audit(
        draws,
        evaluation_start=int(parameter_training["validation_end"]),
    )
    special_3780 = _special_3780_audit()
    gates_pass = (
        synthetic["status"] == "PASS"
        and special_3780["status"] == "PASS"
        and calibration_error_20_rounds["status"] == "PASS"
        and calibration_error_20_rounds["round_count"] == 20
    )
    result = {
        "status": "PASS" if gates_pass else "FAIL",
        "snapshot_id": snapshot_id,
        "history_source_status": history_report["status"],
        "last_contest": history_report["last_contest"],
        "synthetic_qualification": synthetic,
        "real_history_training": real_training,
        "parameter_training_60_20_20": parameter_training,
        "calibration_error_20_rounds": calibration_error_20_rounds,
        "primary_tiebreak_holdout": primary_tiebreak,
        "special_contest_3780_rules": special_3780,
        "predictive_evidence": "NOT_ESTABLISHED",
        "scientific_conclusion": "EVIDENCIA_PREDITIVA_INSUFICIENTE",
    }
    output = artifacts / "max_capacity_audit.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
