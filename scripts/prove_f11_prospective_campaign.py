from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EXPECTED_PROTOCOL = {
    "protocol_version": "prospective-m1-v1",
    "cohort_size": 100,
    "delta_min": 0.0005,
    "primary_metric": "paired_delta_brier_vs_M0",
    "primary_model": "M1_frequency_regularized_lambda_100",
    "secondary_model": "M2_exponential_alpha_0.05",
    "uniform_brier": 0.24,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prove(state_dir: Path) -> dict[str, object]:
    ledger_path = state_dir / "prospective_ledger.json"
    latest_path = state_dir / "latest.json"
    commit_path = state_dir / "state_commit.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    commit = json.loads(commit_path.read_text(encoding="utf-8"))

    protocol = ledger.get("protocol", {})
    for key, expected in EXPECTED_PROTOCOL.items():
        if protocol.get(key) != expected:
            raise RuntimeError(f"F11_PROTOCOL_DRIFT:{key}")

    predictions = ledger.get("predictions", [])
    if not predictions:
        raise RuntimeError("F11_REQUIRES_EXISTING_PROSPECTIVE_LEDGER")
    hashes = {p.get("protocol_hash") for p in predictions}
    if hashes != {protocol.get("protocol_hash")}:
        raise RuntimeError("F11_PREDICTION_PROTOCOL_HASH_DRIFT")
    for p in predictions:
        if int(p["training_last_contest"]) >= int(p["target_contest"]):
            raise RuntimeError("F11_TEMPORAL_LEAKAGE")
        if not p.get("prediction_sha256"):
            raise RuntimeError("F11_UNSEALED_PREDICTION")

    summary = ledger.get("summary", {})
    if summary.get("predictive_evidence") != "NOT_ESTABLISHED":
        raise RuntimeError("F11_SCIENTIFIC_STATE_REGRESSION")
    if summary.get("replication_criteria_met") is not False:
        raise RuntimeError("F11_REPLICATION_STATE_UNEXPECTED")
    if summary.get("prospective_state") != "UNDER_TEST_COHORT_A":
        raise RuntimeError("F11_EXPECTS_ACTIVE_COHORT_A")

    official_latest = int(latest["official_latest_contest"])
    next_target = int(latest["next_prediction_target"])
    if next_target != official_latest + 1:
        raise RuntimeError("F11_NEXT_TARGET_DISCONTINUITY")

    files = commit.get("files", {})
    expected_ledger_hash = files.get("prospective_ledger.json")
    if expected_ledger_hash != sha256(ledger_path):
        raise RuntimeError("F11_STATE_COMMIT_LEDGER_HASH_MISMATCH")

    evaluated = sum(p.get("evaluation") is not None for p in predictions)
    pending = sum(p.get("evaluation") is None for p in predictions)
    if evaluated != summary.get("evaluated_predictions") or pending != summary.get("pending_predictions"):
        raise RuntimeError("F11_LEDGER_SUMMARY_MISMATCH")

    return {
        "schema": "f11-prospective-evidence-campaign-v1",
        "phase": "F11_PROSPECTIVE_EVIDENCE_CAMPAIGN",
        "status": "F11_PROSPECTIVE_EVIDENCE_CAMPAIGN_PROOF_PASS",
        "protocol_version": protocol["protocol_version"],
        "protocol_hash": protocol["protocol_hash"],
        "evaluated_predictions": evaluated,
        "pending_predictions": pending,
        "prospective_state": summary["prospective_state"],
        "official_latest_contest": official_latest,
        "next_prediction_target": next_target,
        "state_generation_id": commit.get("generation_id"),
        "prospective_ledger_sha256": expected_ledger_hash,
        "replication_criteria_met": False,
        "automatic_promotion_allowed": False,
        "predictive_evidence": "NOT_ESTABLISHED",
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--state-dir", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    result = prove(Path(a.state_dir))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
